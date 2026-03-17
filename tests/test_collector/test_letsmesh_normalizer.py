"""Tests for LetsMesh normalizer _normalize_hash_list method."""

from meshcore_hub.collector.letsmesh_normalizer import LetsMeshNormalizer


class TestNormalizeHashList:
    """Tests for _normalize_hash_list with variable-length hex strings."""

    def test_single_byte_hashes_accepted_and_uppercased(self) -> None:
        """Single-byte (2-char) hex hashes are accepted and uppercased."""
        result = LetsMeshNormalizer._normalize_hash_list(["4a", "b3", "fa"])
        assert result == ["4A", "B3", "FA"]

    def test_multibyte_hashes_accepted_and_uppercased(self) -> None:
        """Multibyte (4-char) hex hashes are accepted and uppercased."""
        result = LetsMeshNormalizer._normalize_hash_list(["4a2b", "b3fa"])
        assert result == ["4A2B", "B3FA"]

    def test_mixed_length_hashes_all_accepted(self) -> None:
        """Mixed-length hashes (2-char and 4-char) are all accepted."""
        result = LetsMeshNormalizer._normalize_hash_list(["4a", "b3fa", "02"])
        assert result == ["4A", "B3FA", "02"]

    def test_odd_length_strings_filtered_out(self) -> None:
        """Odd-length hex strings are filtered out."""
        result = LetsMeshNormalizer._normalize_hash_list(["4a", "b3f", "02"])
        assert result == ["4A", "02"]

    def test_invalid_hex_characters_filtered_out(self) -> None:
        """Strings with non-hex characters are filtered out."""
        result = LetsMeshNormalizer._normalize_hash_list(["4a", "zz", "02"])
        assert result == ["4A", "02"]

    def test_empty_list_returns_none(self) -> None:
        """Empty list returns None."""
        result = LetsMeshNormalizer._normalize_hash_list([])
        assert result is None

    def test_non_string_items_filtered_out(self) -> None:
        """Non-string items are filtered out, valid strings kept."""
        result = LetsMeshNormalizer._normalize_hash_list([42, "4a"])
        assert result == ["4A"]

    def test_non_list_input_returns_none(self) -> None:
        """Non-list input returns None."""
        assert LetsMeshNormalizer._normalize_hash_list(None) is None
        assert LetsMeshNormalizer._normalize_hash_list("4a") is None
        assert LetsMeshNormalizer._normalize_hash_list(42) is None

    def test_all_invalid_items_returns_none(self) -> None:
        """List where all items are invalid returns None."""
        result = LetsMeshNormalizer._normalize_hash_list(["z", "b3f", 42])
        assert result is None

    def test_six_char_hashes_accepted(self) -> None:
        """Six-character (3-byte) hex strings are accepted."""
        result = LetsMeshNormalizer._normalize_hash_list(["ab12cd", "ef34ab"])
        assert result == ["AB12CD", "EF34AB"]

    def test_whitespace_stripped_before_validation(self) -> None:
        """Leading/trailing whitespace is stripped before validation."""
        result = LetsMeshNormalizer._normalize_hash_list([" 4a ", " b3fa"])
        assert result == ["4A", "B3FA"]

    def test_single_char_string_rejected(self) -> None:
        """Single-character strings are rejected (minimum is 2)."""
        result = LetsMeshNormalizer._normalize_hash_list(["a", "4a"])
        assert result == ["4A"]
