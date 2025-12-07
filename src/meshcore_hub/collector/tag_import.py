"""Import node tags from YAML file."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, func, select

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node, NodeTag

logger = logging.getLogger(__name__)


class TagValue(BaseModel):
    """Schema for a tag value with type."""

    value: str | None = None
    type: str = Field(default="string", pattern=r"^(string|number|boolean|coordinate)$")


class NodeTags(BaseModel):
    """Schema for tags associated with a node.

    Each key in the model is a tag name, value is TagValue.
    """

    model_config = {"extra": "allow"}

    @model_validator(mode="before")
    @classmethod
    def validate_tags(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Validate that all values are valid tag entries."""
        if not isinstance(data, dict):
            raise ValueError("Node tags must be a dictionary")

        validated = {}
        for key, value in data.items():
            if isinstance(value, dict):
                # Full format: {"value": "...", "type": "..."}
                validated[key] = value
            elif isinstance(value, str):
                # Shorthand: just a string value
                validated[key] = {"value": value, "type": "string"}
            elif value is None:
                validated[key] = {"value": None, "type": "string"}
            else:
                # Convert other types to string
                validated[key] = {"value": str(value), "type": "string"}

        return validated


def validate_public_key(public_key: str) -> str:
    """Validate that public_key is a valid 64-char hex string."""
    if len(public_key) != 64:
        raise ValueError(f"public_key must be 64 characters, got {len(public_key)}")
    if not all(c in "0123456789abcdefABCDEF" for c in public_key):
        raise ValueError("public_key must be a valid hex string")
    return public_key.lower()


def load_tags_file(file_path: str | Path) -> dict[str, dict[str, Any]]:
    """Load and validate tags from a YAML file.

    YAML format - dictionary keyed by public_key:

        0123456789abcdef...:
          friendly_name: My Node
          location:
            value: "52.0,1.0"
            type: coordinate
          altitude:
            value: "150"
            type: number

    Shorthand is allowed - string values are auto-converted:

        0123456789abcdef...:
          friendly_name: My Node

    Args:
        file_path: Path to the tags YAML file

    Returns:
        Dictionary mapping public_key to tag dictionary

    Raises:
        FileNotFoundError: If file does not exist
        yaml.YAMLError: If file is not valid YAML
        ValueError: If file content is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Tags file not found: {file_path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Tags file must contain a YAML mapping")

    # Validate each entry
    validated: dict[str, dict[str, Any]] = {}
    for public_key, tags in data.items():
        # Validate public key
        validated_key = validate_public_key(public_key)

        # Validate tags
        if not isinstance(tags, dict):
            raise ValueError(f"Tags for {public_key[:12]}... must be a dictionary")

        validated_tags: dict[str, Any] = {}
        for tag_key, tag_value in tags.items():
            if isinstance(tag_value, dict):
                # Full format with value and type
                raw_value = tag_value.get("value")
                # Convert value to string if it's not None
                str_value = str(raw_value) if raw_value is not None else None
                validated_tags[tag_key] = {
                    "value": str_value,
                    "type": tag_value.get("type", "string"),
                }
            elif isinstance(tag_value, bool):
                # YAML boolean - must check before int since bool is subclass of int
                validated_tags[tag_key] = {
                    "value": str(tag_value).lower(),
                    "type": "boolean",
                }
            elif isinstance(tag_value, (int, float)):
                # YAML number (int or float)
                validated_tags[tag_key] = {"value": str(tag_value), "type": "number"}
            elif isinstance(tag_value, str):
                # String value
                validated_tags[tag_key] = {"value": tag_value, "type": "string"}
            elif tag_value is None:
                validated_tags[tag_key] = {"value": None, "type": "string"}
            else:
                # Convert other types to string
                validated_tags[tag_key] = {"value": str(tag_value), "type": "string"}

        validated[validated_key] = validated_tags

    return validated


def import_tags(
    file_path: str | Path,
    db: DatabaseManager,
    create_nodes: bool = True,
    clear_existing: bool = False,
) -> dict[str, Any]:
    """Import tags from a YAML file into the database.

    Performs upsert operations - existing tags are updated, new tags are created.
    Optionally clears all existing tags before import.

    Args:
        file_path: Path to the tags YAML file
        db: Database manager instance
        create_nodes: If True, create nodes that don't exist. If False, skip tags
                     for non-existent nodes.
        clear_existing: If True, delete all existing tags before importing.

    Returns:
        Dictionary with import statistics:
        - total: Total number of tags in file
        - created: Number of new tags created
        - updated: Number of existing tags updated
        - skipped: Number of tags skipped (node not found and create_nodes=False)
        - nodes_created: Number of new nodes created
        - deleted: Number of existing tags deleted (if clear_existing=True)
        - errors: List of error messages
    """
    stats: dict[str, Any] = {
        "total": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "nodes_created": 0,
        "deleted": 0,
        "errors": [],
    }

    # Load and validate file
    try:
        tags_data = load_tags_file(file_path)
    except Exception as e:
        stats["errors"].append(f"Failed to load tags file: {e}")
        return stats

    # Count total tags
    for tags in tags_data.values():
        stats["total"] += len(tags)

    now = datetime.now(timezone.utc)

    with db.session_scope() as session:
        # Clear all existing tags if requested
        if clear_existing:
            delete_count = (
                session.execute(select(func.count()).select_from(NodeTag)).scalar() or 0
            )
            session.execute(delete(NodeTag))
            stats["deleted"] = delete_count
            logger.info(f"Deleted {delete_count} existing tags")

        # Cache nodes by public_key to reduce queries
        node_cache: dict[str, Node] = {}

        for public_key, tags in tags_data.items():
            try:
                # Get or create node
                node = node_cache.get(public_key)
                if node is None:
                    query = select(Node).where(Node.public_key == public_key)
                    node = session.execute(query).scalar_one_or_none()

                    if node is None:
                        if create_nodes:
                            node = Node(
                                public_key=public_key,
                                first_seen=now,
                                # last_seen is intentionally left unset (None)
                                # It will be set when the node is actually seen via events
                            )
                            session.add(node)
                            session.flush()
                            stats["nodes_created"] += 1
                            logger.debug(f"Created node for {public_key[:12]}...")
                        else:
                            stats["skipped"] += len(tags)
                            logger.debug(
                                f"Skipped {len(tags)} tags for unknown node {public_key[:12]}..."
                            )
                            continue

                    node_cache[public_key] = node

                # Process each tag
                for tag_key, tag_data in tags.items():
                    try:
                        tag_value = tag_data.get("value")
                        tag_type = tag_data.get("type", "string")

                        if clear_existing:
                            # When clearing, always create new tags
                            new_tag = NodeTag(
                                node_id=node.id,
                                key=tag_key,
                                value=tag_value,
                                value_type=tag_type,
                            )
                            session.add(new_tag)
                            stats["created"] += 1
                            logger.debug(
                                f"Created tag {tag_key}={tag_value} "
                                f"for {public_key[:12]}..."
                            )
                        else:
                            # Find or create tag
                            tag_query = select(NodeTag).where(
                                NodeTag.node_id == node.id,
                                NodeTag.key == tag_key,
                            )
                            existing_tag = session.execute(
                                tag_query
                            ).scalar_one_or_none()

                            if existing_tag:
                                # Update existing tag
                                existing_tag.value = tag_value
                                existing_tag.value_type = tag_type
                                stats["updated"] += 1
                                logger.debug(
                                    f"Updated tag {tag_key}={tag_value} "
                                    f"for {public_key[:12]}..."
                                )
                            else:
                                # Create new tag
                                new_tag = NodeTag(
                                    node_id=node.id,
                                    key=tag_key,
                                    value=tag_value,
                                    value_type=tag_type,
                                )
                                session.add(new_tag)
                                stats["created"] += 1
                                logger.debug(
                                    f"Created tag {tag_key}={tag_value} "
                                    f"for {public_key[:12]}..."
                                )

                    except Exception as e:
                        error_msg = f"Error processing tag {tag_key} for {public_key[:12]}...: {e}"
                        stats["errors"].append(error_msg)
                        logger.error(error_msg)

            except Exception as e:
                error_msg = f"Error processing node {public_key[:12]}...: {e}"
                stats["errors"].append(error_msg)
                logger.error(error_msg)

    return stats
