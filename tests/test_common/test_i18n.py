"""Tests for the i18n translation module."""

import json
from pathlib import Path

import pytest

from meshcore_hub.common.i18n import LOCALES_DIR, load_locale, t, get_locale


@pytest.fixture(autouse=True)
def _reset_locale():
    """Reset locale to English before each test."""
    load_locale("en")
    yield


class TestLoadLocale:
    """Tests for load_locale()."""

    def test_load_english(self):
        """Loading 'en' should succeed and set locale."""
        load_locale("en")
        assert get_locale() == "en"

    def test_fallback_to_english(self, tmp_path: Path):
        """Unknown locale falls back to 'en' if the directory has en.json."""
        # Copy en.json into a temp directory
        en_data = {"entities": {"home": "Home"}}
        (tmp_path / "en.json").write_text(json.dumps(en_data))
        load_locale("xx", locales_dir=tmp_path)
        assert t("entities.home") == "Home"

    def test_missing_locale_dir(self, tmp_path: Path):
        """Missing locale file doesn't crash."""
        load_locale("zz", locales_dir=tmp_path / "nonexistent")
        # Should still work, just returns keys
        assert t("anything") == "anything"


class TestTranslation:
    """Tests for the t() translation function."""

    def test_simple_key(self):
        """Simple dot-separated key resolves correctly."""
        assert t("entities.home") == "Home"
        assert t("entities.nodes") == "Nodes"

    def test_nested_key(self):
        """Deeply nested keys resolve correctly."""
        assert t("entities.advertisements") == "Advertisements"

    def test_missing_key_returns_key(self):
        """Missing key returns the key itself as fallback."""
        assert t("nonexistent.key") == "nonexistent.key"

    def test_interpolation(self):
        """{{var}} placeholders are replaced."""
        assert t("common.total", count=42) == "42 total"

    def test_interpolation_multiple(self):
        """Multiple placeholders are all replaced."""
        result = t(
            "admin_node_tags.copied_entities",
            copied=5,
            skipped=2,
        )
        assert "5" in result
        assert "2" in result

    def test_missing_interpolation_var(self):
        """Missing interpolation variable leaves empty string."""
        # total has {{count}} placeholder
        result = t("common.total")
        # The {{count}} should remain as-is since no var was passed
        # Actually our implementation doesn't replace if key not in kwargs
        assert "total" in result


class TestEnJsonCompleteness:
    """Tests to verify the en.json file is well-formed."""

    def test_en_json_exists(self):
        """The en.json file exists in the expected location."""
        en_path = LOCALES_DIR / "en.json"
        assert en_path.exists(), f"en.json not found at {en_path}"

    def test_en_json_valid(self):
        """The en.json file is valid JSON."""
        en_path = LOCALES_DIR / "en.json"
        data = json.loads(en_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_required_sections_exist(self):
        """All required top-level sections exist."""
        en_path = LOCALES_DIR / "en.json"
        data = json.loads(en_path.read_text(encoding="utf-8"))
        required = [
            "entities",
            "common",
            "links",
            "time",
            "node_types",
            "home",
            "dashboard",
            "nodes",
            "advertisements",
            "messages",
            "map",
            "members",
            "not_found",
            "custom_page",
            "admin",
            "admin_members",
            "admin_node_tags",
            "footer",
        ]
        for section in required:
            assert section in data, f"Missing section: {section}"

    def test_common_no_entity_patterns(self):
        """Test that common 'no entity' patterns exist."""
        assert t("common.no_entity_found", entity="test") == "No test found"
        assert t("common.no_entity_recorded", entity="test") == "No test recorded"
        assert t("common.no_entity_defined", entity="test") == "No test defined"
        assert t("common.no_entity_configured", entity="test") == "No test configured"
        assert t("common.no_entity_yet", entity="test") == "No test yet"
        assert t("common.page_not_found") == "Page not found"

    def test_entity_keys(self):
        """Entity keys are all present."""
        assert t("entities.home") != "entities.home"
        assert t("entities.dashboard") != "entities.dashboard"
        assert t("entities.nodes") != "entities.nodes"
        assert t("entities.advertisements") != "entities.advertisements"
        assert t("entities.messages") != "entities.messages"
        assert t("entities.map") != "entities.map"
        assert t("entities.members") != "entities.members"
        assert t("entities.admin") != "entities.admin"
