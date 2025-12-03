"""Tests for tag import functionality."""

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from meshcore_hub.collector.tag_import import (
    TagEntry,
    TagsFile,
    import_tags,
    load_tags_file,
)
from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node, NodeTag


class TestTagEntry:
    """Tests for TagEntry model."""

    def test_valid_tag_entry(self):
        """Test creating a valid tag entry."""
        entry = TagEntry(
            public_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            key="location",
            value="San Francisco",
            value_type="string",
        )
        assert (
            entry.public_key
            == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )
        assert entry.key == "location"
        assert entry.value == "San Francisco"
        assert entry.value_type == "string"

    def test_public_key_lowercase(self):
        """Test that public key is normalized to lowercase."""
        entry = TagEntry(
            public_key="0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF",
            key="test",
        )
        assert (
            entry.public_key
            == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )

    def test_default_value_type(self):
        """Test default value_type is string."""
        entry = TagEntry(
            public_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            key="test",
        )
        assert entry.value_type == "string"

    def test_invalid_public_key_length(self):
        """Test that short public key is rejected."""
        with pytest.raises(ValidationError):
            TagEntry(
                public_key="0123456789abcdef",
                key="test",
            )

    def test_invalid_public_key_chars(self):
        """Test that non-hex public key is rejected."""
        with pytest.raises(ValidationError):
            TagEntry(
                public_key="zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
                key="test",
            )

    def test_invalid_value_type(self):
        """Test that invalid value_type is rejected."""
        with pytest.raises(ValidationError):
            TagEntry(
                public_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                key="test",
                value_type="invalid",
            )

    def test_valid_value_types(self):
        """Test all valid value types."""
        for vt in ["string", "number", "boolean", "coordinate"]:
            entry = TagEntry(
                public_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                key="test",
                value_type=vt,
            )
            assert entry.value_type == vt


class TestTagsFile:
    """Tests for TagsFile model."""

    def test_valid_tags_file(self):
        """Test creating a valid tags file."""
        tags_file = TagsFile(
            tags=[
                TagEntry(
                    public_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    key="location",
                    value="SF",
                ),
                TagEntry(
                    public_key="fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
                    key="role",
                    value="gateway",
                ),
            ]
        )
        assert len(tags_file.tags) == 2

    def test_empty_tags(self):
        """Test tags file with empty tags list."""
        tags_file = TagsFile(tags=[])
        assert len(tags_file.tags) == 0


class TestLoadTagsFile:
    """Tests for load_tags_file function."""

    def test_load_valid_file(self):
        """Test loading a valid tags file."""
        data = {
            "tags": [
                {
                    "public_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "key": "location",
                    "value": "San Francisco",
                    "value_type": "string",
                }
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            result = load_tags_file(f.name)
            assert len(result.tags) == 1
            assert result.tags[0].key == "location"

        Path(f.name).unlink()

    def test_file_not_found(self):
        """Test loading non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_tags_file("/nonexistent/path/tags.json")

    def test_invalid_json(self):
        """Test loading invalid JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json {{{")
            f.flush()

            with pytest.raises(json.JSONDecodeError):
                load_tags_file(f.name)

        Path(f.name).unlink()

    def test_invalid_schema(self):
        """Test loading file with invalid schema."""
        data: dict[str, list[str]] = {"not_tags": []}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            with pytest.raises(ValidationError):
                load_tags_file(f.name)

        Path(f.name).unlink()


class TestImportTags:
    """Tests for import_tags function."""

    @pytest.fixture
    def db_manager(self):
        """Create an in-memory database manager for testing."""
        manager = DatabaseManager("sqlite:///:memory:")
        manager.create_tables()
        yield manager
        manager.dispose()

    @pytest.fixture
    def sample_tags_file(self):
        """Create a sample tags file."""
        data = {
            "tags": [
                {
                    "public_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "key": "location",
                    "value": "San Francisco",
                    "value_type": "string",
                },
                {
                    "public_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "key": "role",
                    "value": "gateway",
                    "value_type": "string",
                },
                {
                    "public_key": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
                    "key": "altitude",
                    "value": "100",
                    "value_type": "number",
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            yield f.name

        Path(f.name).unlink()

    def test_import_creates_nodes_and_tags(self, db_manager, sample_tags_file):
        """Test that import creates nodes and tags."""
        stats = import_tags(sample_tags_file, db_manager, create_nodes=True)

        assert stats["total"] == 3
        assert stats["created"] == 3
        assert stats["updated"] == 0
        assert stats["skipped"] == 0
        assert stats["nodes_created"] == 2
        assert len(stats["errors"]) == 0

        # Verify in database
        with db_manager.session_scope() as session:
            nodes = session.execute(select(Node)).scalars().all()
            assert len(nodes) == 2

            tags = session.execute(select(NodeTag)).scalars().all()
            assert len(tags) == 3

    def test_import_updates_existing_tags(self, db_manager, sample_tags_file):
        """Test that import updates existing tags."""
        # First import
        stats1 = import_tags(sample_tags_file, db_manager, create_nodes=True)
        assert stats1["created"] == 3
        assert stats1["updated"] == 0

        # Second import
        stats2 = import_tags(sample_tags_file, db_manager, create_nodes=True)
        assert stats2["created"] == 0
        assert stats2["updated"] == 3
        assert stats2["nodes_created"] == 0

    def test_import_skips_unknown_nodes(self, db_manager, sample_tags_file):
        """Test that import skips tags for unknown nodes when create_nodes=False."""
        stats = import_tags(sample_tags_file, db_manager, create_nodes=False)

        assert stats["total"] == 3
        assert stats["created"] == 0
        assert stats["skipped"] == 3
        assert stats["nodes_created"] == 0

        # Verify no nodes or tags in database
        with db_manager.session_scope() as session:
            nodes = session.execute(select(Node)).scalars().all()
            assert len(nodes) == 0

            tags = session.execute(select(NodeTag)).scalars().all()
            assert len(tags) == 0

    def test_import_with_existing_nodes(self, db_manager, sample_tags_file):
        """Test import when nodes already exist."""
        # Create a node first
        with db_manager.session_scope() as session:
            node = Node(
                public_key="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            )
            session.add(node)

        # Import with create_nodes=False
        stats = import_tags(sample_tags_file, db_manager, create_nodes=False)

        # Only 2 tags for the existing node should be created
        assert stats["created"] == 2
        assert stats["skipped"] == 1  # One tag for the non-existent node
        assert stats["nodes_created"] == 0

    def test_import_nonexistent_file(self, db_manager):
        """Test import with non-existent file."""
        stats = import_tags("/nonexistent/tags.json", db_manager)

        assert stats["total"] == 0
        assert len(stats["errors"]) == 1
        assert "Failed to load" in stats["errors"][0]

    def test_import_empty_file(self, db_manager):
        """Test import with empty tags list."""
        data: dict[str, list[str]] = {"tags": []}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            stats = import_tags(f.name, db_manager)

        assert stats["total"] == 0
        assert stats["created"] == 0

        Path(f.name).unlink()

    def test_import_preserves_value_type(self, db_manager):
        """Test that import preserves value_type correctly."""
        data = {
            "tags": [
                {
                    "public_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "key": "count",
                    "value": "42",
                    "value_type": "number",
                },
                {
                    "public_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                    "key": "active",
                    "value": "true",
                    "value_type": "boolean",
                },
            ]
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()

            import_tags(f.name, db_manager, create_nodes=True)

        with db_manager.session_scope() as session:
            tags = session.execute(select(NodeTag)).scalars().all()
            tag_dict = {t.key: t for t in tags}

            assert tag_dict["count"].value_type == "number"
            assert tag_dict["active"].value_type == "boolean"

        Path(f.name).unlink()
