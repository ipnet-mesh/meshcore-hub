"""Tests for LetsMesh packet decoder integration."""

from unittest.mock import MagicMock, patch

from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder


def test_decode_payload_returns_none_without_raw() -> None:
    """Decoder returns None when packet has no raw hex."""
    decoder = LetsMeshPacketDecoder()
    assert decoder.decode_payload({"packet_type": 5}) is None


def test_decode_payload_rejects_non_hex_raw_without_invoking_decoder() -> None:
    """Decoder returns None and does not call MeshCoreDecoder for invalid hex."""
    decoder = LetsMeshPacketDecoder()

    with patch("meshcore_hub.collector.letsmesh_decoder.MeshCoreDecoder") as mock_lib:
        assert decoder.decode_payload({"raw": "ZZ-not-hex"}) is None

    mock_lib.decode.assert_not_called()


def test_decode_payload_calls_native_decoder() -> None:
    """Decoder calls MeshCoreDecoder.decode and returns dict output."""
    decoder = LetsMeshPacketDecoder(
        channel_keys=["0xABCDEF", "name=012345", "abcDEF"],
    )

    mock_result = MagicMock()
    mock_result.is_valid = True
    mock_result.to_dict.return_value = {
        "payloadType": 5,
        "pathLength": 2,
        "payload": {
            "decoded": {
                "channelHash": "11",
                "decrypted": {"message": "hello"},
            }
        },
    }

    with patch(
        "meshcore_hub.collector.letsmesh_decoder.MeshCoreDecoder.decode",
        return_value=mock_result,
    ) as mock_decode:
        decoded = decoder.decode_payload({"raw": "A1B2C3"})

    assert isinstance(decoded, dict)
    assert decoded["payload"]["decoded"]["decrypted"]["message"] == "hello"
    mock_decode.assert_called_once()

    args, kwargs = mock_decode.call_args
    assert args[0] == "A1B2C3"
    assert kwargs.get("options") is not None or len(args) > 1


def test_decode_payload_returns_none_for_decoder_error() -> None:
    """Decoder returns None when native decoder raises an exception."""
    decoder = LetsMeshPacketDecoder()

    with patch(
        "meshcore_hub.collector.letsmesh_decoder.MeshCoreDecoder.decode",
        side_effect=ValueError("bad packet"),
    ):
        assert decoder.decode_payload({"raw": "A1B2C3"}) is None


def test_decode_payload_returns_none_for_invalid_result() -> None:
    """Decoder returns None when native decoder returns invalid result."""
    decoder = LetsMeshPacketDecoder()

    mock_result = MagicMock()
    mock_result.is_valid = False
    mock_result.errors = ["unsupported packet"]

    with patch(
        "meshcore_hub.collector.letsmesh_decoder.MeshCoreDecoder.decode",
        return_value=mock_result,
    ):
        assert decoder.decode_payload({"raw": "A1B2C3"}) is None


def test_builtin_channel_keys_present_by_default() -> None:
    """Public and #test keys are always present even without .env keys."""
    decoder = LetsMeshPacketDecoder()
    assert decoder._channel_keys == [
        "8B3387E9C5CDEA6AC9E5EDBAA115CD72",
        "9CD8FCF22A47333B591D96A2B848B73F",
    ]


def test_channel_name_lookup_from_decoded_hash() -> None:
    """Decoder resolves channel names from configured label=key entries."""
    key_hex = "EB50A1BCB3E4E5D7BF69A57C9DADA211"
    decoder = LetsMeshPacketDecoder(channel_keys=[f"#bot={key_hex}"])
    channel_hash = decoder._compute_channel_hash(key_hex)
    decoded_packet = {
        "payload": {
            "decoded": {
                "channelHash": channel_hash,
            }
        }
    }

    assert decoder.channel_name_from_decoded(decoded_packet) == "bot"


def test_channel_labels_by_index_includes_labeled_entries() -> None:
    """Channel labels map includes built-ins and label=key env entries."""
    decoder = LetsMeshPacketDecoder(
        channel_keys=[
            "bot=EB50A1BCB3E4E5D7BF69A57C9DADA211",
            "chat=D0BDD6D71538138ED979EEC00D98AD97",
        ],
    )

    labels = decoder.channel_labels_by_index()

    assert labels[17] == "Public"
    assert labels[217] == "test"
    assert labels[202] == "bot"
    assert labels[184] == "chat"


def test_decode_payload_caches_results() -> None:
    """Repeated decode calls for same hex use cached result."""
    decoder = LetsMeshPacketDecoder()

    mock_result = MagicMock()
    mock_result.is_valid = True
    mock_result.to_dict.return_value = {"payloadType": 4}

    with patch(
        "meshcore_hub.collector.letsmesh_decoder.MeshCoreDecoder.decode",
        return_value=mock_result,
    ) as mock_decode:
        first = decoder.decode_payload({"raw": "AABBCC"})
        second = decoder.decode_payload({"raw": "AABBCC"})

    assert first is second
    mock_decode.assert_called_once()


def test_flatten_control_parsed_merges_parsed_into_decoded() -> None:
    """Control payload parsed fields are flattened into decoded dict."""
    decoded_dict = {
        "payload": {
            "decoded": {
                "type": 11,
                "subType": 144,
                "flags": 1,
                "parsed": {
                    "publicKey": "AA" * 32,
                    "nodeType": 2,
                },
            }
        }
    }
    LetsMeshPacketDecoder._flatten_control_parsed(decoded_dict)
    decoded = decoded_dict["payload"]["decoded"]
    assert decoded["publicKey"] == "AA" * 32
    assert decoded["nodeType"] == 2
    assert "parsed" in decoded


def test_flatten_control_parsed_does_not_overwrite_existing() -> None:
    """Flattening uses setdefault so existing keys are preserved."""
    decoded_dict = {
        "payload": {
            "decoded": {
                "subType": 144,
                "parsed": {
                    "subType": 999,
                    "extra": "value",
                },
            }
        }
    }
    LetsMeshPacketDecoder._flatten_control_parsed(decoded_dict)
    decoded = decoded_dict["payload"]["decoded"]
    assert decoded["subType"] == 144
    assert decoded["extra"] == "value"


def test_decode_payload_returns_none_for_empty_raw() -> None:
    """Decoder returns None for empty raw string."""
    decoder = LetsMeshPacketDecoder()
    assert decoder.decode_payload({"raw": ""}) is None
    assert decoder.decode_payload({"raw": "  "}) is None


def test_decode_payload_returns_none_for_non_string_raw() -> None:
    """Decoder returns None when raw is not a string."""
    decoder = LetsMeshPacketDecoder()
    assert decoder.decode_payload({"raw": 12345}) is None
    assert decoder.decode_payload({"raw": None}) is None
