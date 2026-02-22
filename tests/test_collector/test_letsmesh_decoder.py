"""Tests for LetsMesh packet decoder integration."""

import subprocess
from unittest.mock import patch

from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder


def test_decode_payload_returns_none_without_raw() -> None:
    """Decoder returns None when packet has no raw hex."""
    decoder = LetsMeshPacketDecoder(enabled=True)
    assert decoder.decode_payload({"packet_type": 5}) is None


def test_decode_payload_invokes_decoder_with_keys() -> None:
    """Decoder command includes channel keys and returns parsed JSON."""
    decoder = LetsMeshPacketDecoder(
        enabled=True,
        command="meshcore-decoder",
        channel_keys=["0xABCDEF", "name=012345", "abcDEF"],
        timeout_seconds=1.5,
    )
    completed = subprocess.CompletedProcess(
        args=["meshcore-decoder"],
        returncode=0,
        stdout='{"payload":{"decoded":{"decrypted":{"message":"hello"}}}}',
        stderr="",
    )

    with (
        patch("meshcore_hub.collector.letsmesh_decoder.shutil.which", return_value="1"),
        patch(
            "meshcore_hub.collector.letsmesh_decoder.subprocess.run",
            return_value=completed,
        ) as mock_run,
    ):
        decoded = decoder.decode_payload({"raw": "A1B2C3"})

    assert isinstance(decoded, dict)
    payload = decoded.get("payload")
    assert isinstance(payload, dict)
    decoded_payload = payload.get("decoded")
    assert isinstance(decoded_payload, dict)
    decrypted = decoded_payload.get("decrypted")
    assert isinstance(decrypted, dict)
    assert decrypted.get("message") == "hello"
    command = mock_run.call_args.args[0]
    assert command == [
        "meshcore-decoder",
        "decode",
        "A1B2C3",
        "--json",
        "--key",
        "8B3387E9C5CDEA6AC9E5EDBAA115CD72",
        "9CD8FCF22A47333B591D96A2B848B73F",
        "ABCDEF",
        "012345",
    ]
    assert mock_run.call_args.kwargs["timeout"] == 1.5


def test_decode_payload_returns_none_for_decoder_error() -> None:
    """Decoder returns None when decoder exits with failure."""
    decoder = LetsMeshPacketDecoder(enabled=True, command="meshcore-decoder")
    completed = subprocess.CompletedProcess(
        args=["meshcore-decoder"],
        returncode=1,
        stdout="",
        stderr="decode error",
    )

    with (
        patch("meshcore_hub.collector.letsmesh_decoder.shutil.which", return_value="1"),
        patch(
            "meshcore_hub.collector.letsmesh_decoder.subprocess.run",
            return_value=completed,
        ),
    ):
        assert decoder.decode_payload({"raw": "A1B2C3"}) is None


def test_builtin_channel_keys_present_by_default() -> None:
    """Public and #test keys are always present even without .env keys."""
    decoder = LetsMeshPacketDecoder(enabled=True, command="meshcore-decoder")
    assert decoder._channel_keys == [
        "8B3387E9C5CDEA6AC9E5EDBAA115CD72",
        "9CD8FCF22A47333B591D96A2B848B73F",
    ]


def test_channel_name_lookup_from_decoded_hash() -> None:
    """Decoder resolves channel names from configured label=key entries."""
    key_hex = "EB50A1BCB3E4E5D7BF69A57C9DADA211"
    decoder = LetsMeshPacketDecoder(
        enabled=False,
        channel_keys=[f"#bot={key_hex}"],
    )
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
        enabled=False,
        channel_keys=[
            "bot=EB50A1BCB3E4E5D7BF69A57C9DADA211",
            "chat=D0BDD6D71538138ED979EEC00D98AD97",
        ],
    )

    labels = decoder.channel_labels_by_index()

    assert labels[17] == "Public"
    assert labels[217] == "#test"
    assert labels[202] == "#bot"
    assert labels[184] == "#chat"
