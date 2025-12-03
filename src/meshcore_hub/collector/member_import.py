"""Import members from JSON file."""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Member

logger = logging.getLogger(__name__)


class MemberData(BaseModel):
    """Schema for a member entry in the import file."""

    name: str = Field(..., min_length=1, max_length=255)
    callsign: Optional[str] = Field(default=None, max_length=20)
    role: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None)
    contact: Optional[str] = Field(default=None, max_length=255)
    public_key: Optional[str] = Field(default=None)

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize public key if provided."""
        if v is None:
            return None
        if len(v) != 64:
            raise ValueError(f"public_key must be 64 characters, got {len(v)}")
        if not all(c in "0123456789abcdefABCDEF" for c in v):
            raise ValueError("public_key must be a valid hex string")
        return v.lower()


def load_members_file(file_path: str | Path) -> list[dict[str, Any]]:
    """Load and validate members from a JSON file.

    Supports two formats:
    1. List of member objects:
       [{"name": "Member 1", ...}, {"name": "Member 2", ...}]

    2. Object with "members" key:
       {"members": [{"name": "Member 1", ...}, ...]}

    Args:
        file_path: Path to the members JSON file

    Returns:
        List of validated member dictionaries

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file is not valid JSON
        ValueError: If file content is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Members file not found: {file_path}")

    with open(path, "r") as f:
        data = json.load(f)

    # Handle both formats
    if isinstance(data, list):
        members_list = data
    elif isinstance(data, dict) and "members" in data:
        members_list = data["members"]
        if not isinstance(members_list, list):
            raise ValueError("'members' key must contain a list")
    else:
        raise ValueError(
            "Members file must be a list or an object with 'members' key"
        )

    # Validate each member
    validated: list[dict[str, Any]] = []
    for i, member in enumerate(members_list):
        if not isinstance(member, dict):
            raise ValueError(f"Member at index {i} must be an object")
        if "name" not in member:
            raise ValueError(f"Member at index {i} must have a 'name' field")

        # Validate using Pydantic model
        try:
            validated_member = MemberData.model_validate(member)
            validated.append(validated_member.model_dump())
        except Exception as e:
            raise ValueError(f"Invalid member at index {i}: {e}")

    return validated


def import_members(
    file_path: str | Path,
    db: DatabaseManager,
) -> dict[str, Any]:
    """Import members from a JSON file into the database.

    Performs upsert operations based on name - existing members are updated,
    new members are created.

    Args:
        file_path: Path to the members JSON file
        db: Database manager instance

    Returns:
        Dictionary with import statistics:
        - total: Total number of members in file
        - created: Number of new members created
        - updated: Number of existing members updated
        - errors: List of error messages
    """
    stats: dict[str, Any] = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "errors": [],
    }

    # Load and validate file
    try:
        members_data = load_members_file(file_path)
    except Exception as e:
        stats["errors"].append(f"Failed to load members file: {e}")
        return stats

    stats["total"] = len(members_data)

    with db.session_scope() as session:
        for member_data in members_data:
            try:
                name = member_data["name"]

                # Find existing member by name
                query = select(Member).where(Member.name == name)
                existing = session.execute(query).scalar_one_or_none()

                if existing:
                    # Update existing member
                    if member_data.get("callsign") is not None:
                        existing.callsign = member_data["callsign"]
                    if member_data.get("role") is not None:
                        existing.role = member_data["role"]
                    if member_data.get("description") is not None:
                        existing.description = member_data["description"]
                    if member_data.get("contact") is not None:
                        existing.contact = member_data["contact"]
                    if member_data.get("public_key") is not None:
                        existing.public_key = member_data["public_key"]

                    stats["updated"] += 1
                    logger.debug(f"Updated member: {name}")
                else:
                    # Create new member
                    new_member = Member(
                        name=name,
                        callsign=member_data.get("callsign"),
                        role=member_data.get("role"),
                        description=member_data.get("description"),
                        contact=member_data.get("contact"),
                        public_key=member_data.get("public_key"),
                    )
                    session.add(new_member)
                    stats["created"] += 1
                    logger.debug(f"Created member: {name}")

            except Exception as e:
                error_msg = f"Error processing member '{member_data.get('name', 'unknown')}': {e}"
                stats["errors"].append(error_msg)
                logger.error(error_msg)

    return stats
