"""Import node tags from JSON file."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node, NodeTag

logger = logging.getLogger(__name__)


class TagEntry(BaseModel):
    """Schema for a tag entry in the import file."""

    public_key: str = Field(..., min_length=64, max_length=64)
    key: str = Field(..., min_length=1, max_length=100)
    value: str | None = None
    value_type: str = Field(
        default="string", pattern=r"^(string|number|boolean|coordinate)$"
    )

    @field_validator("public_key")
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        """Validate that public_key is a valid hex string."""
        if not all(c in "0123456789abcdefABCDEF" for c in v):
            raise ValueError("public_key must be a valid hex string")
        return v.lower()


class TagsFile(BaseModel):
    """Schema for the tags JSON file."""

    tags: list[TagEntry]


def load_tags_file(file_path: str | Path) -> TagsFile:
    """Load and validate tags from a JSON file.

    Args:
        file_path: Path to the tags JSON file

    Returns:
        Validated TagsFile instance

    Raises:
        FileNotFoundError: If file does not exist
        json.JSONDecodeError: If file is not valid JSON
        pydantic.ValidationError: If file content is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Tags file not found: {file_path}")

    with open(path, "r") as f:
        data = json.load(f)

    return TagsFile.model_validate(data)


def import_tags(
    file_path: str | Path,
    db: DatabaseManager,
    create_nodes: bool = True,
) -> dict[str, Any]:
    """Import tags from a JSON file into the database.

    Performs upsert operations - existing tags are updated, new tags are created.

    Args:
        file_path: Path to the tags JSON file
        db: Database manager instance
        create_nodes: If True, create nodes that don't exist. If False, skip tags
                     for non-existent nodes.

    Returns:
        Dictionary with import statistics:
        - total: Total number of tags in file
        - created: Number of new tags created
        - updated: Number of existing tags updated
        - skipped: Number of tags skipped (node not found and create_nodes=False)
        - nodes_created: Number of new nodes created
        - errors: List of error messages
    """
    stats: dict[str, Any] = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "nodes_created": 0,
        "errors": [],
    }

    # Load and validate file
    try:
        tags_file = load_tags_file(file_path)
    except Exception as e:
        stats["errors"].append(f"Failed to load tags file: {e}")
        return stats

    stats["total"] = len(tags_file.tags)
    now = datetime.now(timezone.utc)

    with db.session_scope() as session:
        # Cache nodes by public_key to reduce queries
        node_cache: dict[str, Node] = {}

        for tag_entry in tags_file.tags:
            try:
                # Get or create node
                node = node_cache.get(tag_entry.public_key)
                if node is None:
                    query = select(Node).where(Node.public_key == tag_entry.public_key)
                    node = session.execute(query).scalar_one_or_none()

                    if node is None:
                        if create_nodes:
                            node = Node(
                                public_key=tag_entry.public_key,
                                first_seen=now,
                                last_seen=now,
                            )
                            session.add(node)
                            session.flush()
                            stats["nodes_created"] += 1
                            logger.debug(
                                f"Created node for {tag_entry.public_key[:12]}..."
                            )
                        else:
                            stats["skipped"] += 1
                            logger.debug(
                                f"Skipped tag for unknown node {tag_entry.public_key[:12]}..."
                            )
                            continue

                    node_cache[tag_entry.public_key] = node

                # Find or create tag
                tag_query = select(NodeTag).where(
                    NodeTag.node_id == node.id,
                    NodeTag.key == tag_entry.key,
                )
                existing_tag = session.execute(tag_query).scalar_one_or_none()

                if existing_tag:
                    # Update existing tag
                    existing_tag.value = tag_entry.value
                    existing_tag.value_type = tag_entry.value_type
                    stats["updated"] += 1
                    logger.debug(
                        f"Updated tag {tag_entry.key}={tag_entry.value} "
                        f"for {tag_entry.public_key[:12]}..."
                    )
                else:
                    # Create new tag
                    new_tag = NodeTag(
                        node_id=node.id,
                        key=tag_entry.key,
                        value=tag_entry.value,
                        value_type=tag_entry.value_type,
                    )
                    session.add(new_tag)
                    stats["created"] += 1
                    logger.debug(
                        f"Created tag {tag_entry.key}={tag_entry.value} "
                        f"for {tag_entry.public_key[:12]}..."
                    )

            except Exception as e:
                error_msg = f"Error processing tag {tag_entry.key} for {tag_entry.public_key[:12]}...: {e}"
                stats["errors"].append(error_msg)
                logger.error(error_msg)

    return stats
