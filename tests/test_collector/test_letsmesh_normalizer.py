"""Tests for LetsMesh normalizer."""

from unittest.mock import MagicMock

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


class TestAdvertisementSnrAndPath:
    """Tests for SNR and path_len extraction in advertisement payloads."""

    def _make_normalizer(self) -> LetsMeshNormalizer:
        norm = LetsMeshNormalizer()
        norm._letsmesh_decoder = MagicMock()
        norm._include_test_channel = False
        return norm

    def _make_decoded_type4(self) -> dict:
        return {
            "payloadType": 4,
            "payload": {
                "decoded": {
                    "publicKey": "b" * 64,
                },
            },
        }

    def test_advertisement_extracts_snr_from_uppercase_key(self) -> None:
        """Advertisement payload with uppercase SNR normalizes to lowercase snr."""
        norm = self._make_normalizer()
        result = norm._build_letsmesh_advertisement_payload(
            {"SNR": 12.5, "path": "91CBC3"},
            decoded_packet=self._make_decoded_type4(),
        )
        assert result is not None
        assert result["snr"] == 12.5

    def test_advertisement_extracts_snr_from_lowercase_key(self) -> None:
        """Advertisement payload with lowercase snr extracts it."""
        norm = self._make_normalizer()
        result = norm._build_letsmesh_advertisement_payload(
            {"snr": 9.0},
            decoded_packet=self._make_decoded_type4(),
        )
        assert result is not None
        assert result["snr"] == 9.0

    def test_advertisement_extracts_path_len(self) -> None:
        """Advertisement payload with path extracts path_len."""
        norm = self._make_normalizer()
        result = norm._build_letsmesh_advertisement_payload(
            {"path": "91CBC3"},
            decoded_packet=self._make_decoded_type4(),
        )
        assert result is not None
        assert result.get("path_len") is not None

    def test_output_has_lowercase_snr_key_only(self) -> None:
        """Output contains lowercase snr key, never uppercase SNR."""
        norm = self._make_normalizer()
        result = norm._build_letsmesh_advertisement_payload(
            {"SNR": 8.0},
            decoded_packet=self._make_decoded_type4(),
        )
        assert result is not None
        assert "snr" in result
        assert "SNR" not in result


class TestMessageSnrCasing:
    """Tests for message payload SNR casing (lowercase output)."""

    def _make_normalizer(self) -> LetsMeshNormalizer:
        norm = LetsMeshNormalizer()
        norm._letsmesh_decoder = MagicMock()
        norm._include_test_channel = True
        return norm

    def _make_decoded_type5(self) -> dict:
        return {
            "payloadType": 5,
            "payload": {
                "decoded": {
                    "text": "hello channel",
                    "channel": {"hash": "A" * 24},
                },
            },
        }

    def test_message_outputs_lowercase_snr(self) -> None:
        """Message payload outputs lowercase snr key, not uppercase SNR."""
        norm = self._make_normalizer()
        result = norm._build_letsmesh_message_payload(
            {
                "packet_type": "5",
                "hash": "ABCDEF1234",
                "SNR": "12.5",
                "path": "91CBC3",
            },
            decoded_packet=self._make_decoded_type5(),
        )
        assert result is not None
        _, payload = result
        assert "snr" in payload
        assert "SNR" not in payload
