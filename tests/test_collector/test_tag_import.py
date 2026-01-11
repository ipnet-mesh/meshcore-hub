"""Tests for tag import functionality."""

import tempfile
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from meshcore_hub.collector.tag_import import (
    import_tags,
    load_tags_file,
    validate_public_key,
)
from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import Node, NodeTag


class TestValidatePublicKey:
    """Tests for validate_public_key function."""

    def test_valid_public_key(self):
        """Test valid public key is returned lowercase."""
        result = validate_public_key(
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )
        assert (
            result == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )

    def test_public_key_lowercase(self):
        """Test that public key is normalized to lowercase."""
        result = validate_public_key(
            "0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF"
        )
        assert (
            result == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        )

    def test_invalid_public_key_length(self):
        """Test that short public key is rejected."""
        with pytest.raises(ValueError, match="must be 64 characters"):
            validate_public_key("0123456789abcdef")

    def test_invalid_public_key_chars(self):
        """Test that non-hex public key is rejected."""
        with pytest.raises(ValueError, match="valid hex string"):
            validate_public_key(
                "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"
            )


class TestLoadTagsFile:
    """Tests for load_tags_file function."""

    def test_load_valid_file(self):
        """Test loading a valid tags file with new format."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "location": "San Francisco",
                "role": {"value": "gateway", "type": "string"},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            result = load_tags_file(f.name)
            assert len(result) == 1
            key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
            assert key in result
            assert result[key]["location"]["value"] == "San Francisco"
            assert result[key]["location"]["type"] == "string"
            assert result[key]["role"]["value"] == "gateway"

        Path(f.name).unlink()

    def test_load_shorthand_format(self):
        """Test loading file with shorthand string values."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "friendly_name": "My Node",
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            result = load_tags_file(f.name)
            key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
            assert result[key]["friendly_name"]["value"] == "My Node"
            assert result[key]["friendly_name"]["type"] == "string"

        Path(f.name).unlink()

    def test_load_full_format(self):
        """Test loading file with full format (value and type)."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "is_active": {"value": "true", "type": "boolean"},
                "altitude": {"value": "150", "type": "number"},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            result = load_tags_file(f.name)
            key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
            assert result[key]["is_active"]["type"] == "boolean"
            assert result[key]["altitude"]["type"] == "number"

        Path(f.name).unlink()

    def test_file_not_found(self):
        """Test loading non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_tags_file("/nonexistent/path/tags.yaml")

    def test_invalid_yaml(self):
        """Test loading invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [unclosed")
            f.flush()

            with pytest.raises(yaml.YAMLError):
                load_tags_file(f.name)

        Path(f.name).unlink()

    def test_invalid_schema_not_dict(self):
        """Test loading file with invalid schema (not a dict)."""
        data = [{"public_key": "abc"}]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            with pytest.raises(ValueError, match="must contain a YAML mapping"):
                load_tags_file(f.name)

        Path(f.name).unlink()

    def test_invalid_public_key(self):
        """Test loading file with invalid public key."""
        data = {"invalid_key": {"tag": "value"}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            with pytest.raises(ValueError, match="must be 64 characters"):
                load_tags_file(f.name)

        Path(f.name).unlink()

    def test_load_empty_file(self):
        """Test loading empty tags file."""
        data: dict[str, dict[str, str]] = {}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            result = load_tags_file(f.name)
            assert len(result) == 0

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
        """Create a sample tags file with new format."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "location": "San Francisco",
                "role": {"value": "gateway", "type": "string"},
            },
            "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210": {
                "altitude": {"value": "100", "type": "number"},
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
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
        stats = import_tags("/nonexistent/tags.yaml", db_manager)

        assert stats["total"] == 0
        assert len(stats["errors"]) == 1
        assert "Failed to load" in stats["errors"][0]

    def test_import_empty_file(self, db_manager):
        """Test import with empty tags object."""
        data: dict[str, dict[str, str]] = {}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            stats = import_tags(f.name, db_manager)

        assert stats["total"] == 0
        assert stats["created"] == 0

        Path(f.name).unlink()

    def test_import_preserves_value_type(self, db_manager):
        """Test that import preserves value_type correctly."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "count": {"value": "42", "type": "number"},
                "active": {"value": "true", "type": "boolean"},
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            import_tags(f.name, db_manager, create_nodes=True)

        with db_manager.session_scope() as session:
            tags = session.execute(select(NodeTag)).scalars().all()
            tag_dict = {t.key: t for t in tags}

            assert tag_dict["count"].value_type == "number"
            assert tag_dict["active"].value_type == "boolean"

        Path(f.name).unlink()

    def test_import_null_value(self, db_manager):
        """Test that null values are handled correctly."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "empty_tag": None,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            stats = import_tags(f.name, db_manager, create_nodes=True)

        assert stats["created"] == 1

        with db_manager.session_scope() as session:
            tag = session.execute(select(NodeTag)).scalar_one()
            assert tag.key == "empty_tag"
            assert tag.value is None
            assert tag.value_type == "string"

        Path(f.name).unlink()

    def test_import_numeric_value_detected(self, db_manager):
        """Test that YAML numeric values are detected and stored with number type."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "num_val": 42,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            stats = import_tags(f.name, db_manager, create_nodes=True)

        assert stats["created"] == 1

        with db_manager.session_scope() as session:
            tag = session.execute(select(NodeTag)).scalar_one()
            assert tag.key == "num_val"
            assert tag.value == "42"
            assert tag.value_type == "number"

        Path(f.name).unlink()

    def test_import_boolean_value_detected(self, db_manager):
        """Test that YAML boolean values are detected and stored with boolean type."""
        data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "is_active": True,
                "is_disabled": False,
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()

            stats = import_tags(f.name, db_manager, create_nodes=True)

        assert stats["created"] == 2

        with db_manager.session_scope() as session:
            tags = session.execute(select(NodeTag)).scalars().all()
            tag_dict = {t.key: t for t in tags}

            assert tag_dict["is_active"].value == "true"
            assert tag_dict["is_active"].value_type == "boolean"
            assert tag_dict["is_disabled"].value == "false"
            assert tag_dict["is_disabled"].value_type == "boolean"

        Path(f.name).unlink()

    def test_import_with_clear_existing(self, db_manager):
        """Test that clear_existing deletes all tags before importing."""
        # Create initial tags
        initial_data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "old_tag": "old_value",
                "shared_tag": "old_value",
            },
            "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef": {
                "another_old_tag": "value",
            },
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(initial_data, f)
            f.flush()
            initial_file = f.name

        stats1 = import_tags(initial_file, db_manager, create_nodes=True)
        assert stats1["created"] == 3
        assert stats1["deleted"] == 0

        # Verify initial tags exist
        with db_manager.session_scope() as session:
            tags = session.execute(select(NodeTag)).scalars().all()
            assert len(tags) == 3

        # Import new tags with clear_existing=True
        new_data = {
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef": {
                "new_tag": "new_value",
                "shared_tag": "new_value",
            }
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(new_data, f)
            f.flush()
            new_file = f.name

        stats2 = import_tags(
            new_file, db_manager, create_nodes=True, clear_existing=True
        )
        assert stats2["deleted"] == 3  # All 3 old tags deleted
        assert stats2["created"] == 2  # 2 new tags created
        assert stats2["updated"] == 0  # No updates when clearing

        # Verify only new tags exist
        with db_manager.session_scope() as session:
            tags = session.execute(select(NodeTag)).scalars().all()
            tag_dict = {t.key: t for t in tags}
            assert len(tags) == 2
            assert "new_tag" in tag_dict
            assert "shared_tag" in tag_dict
            assert tag_dict["shared_tag"].value == "new_value"
            assert "old_tag" not in tag_dict
            assert "another_old_tag" not in tag_dict

        Path(initial_file).unlink()
        Path(new_file).unlink()
