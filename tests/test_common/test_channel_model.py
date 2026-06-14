"""Tests for Channel model and channel Pydantic schemas."""

import hashlib

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from meshcore_hub.common.models import Base, Channel, ChannelVisibility
from meshcore_hub.common.schemas.channels import ChannelCreate, ChannelUpdate


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


class TestChannelModel:
    """Tests for Channel SQLAlchemy model."""

    def test_create_channel(self, db_session) -> None:
        """Test creating a channel in the database."""
        key_hex = "AABBCCDDEEFF00112233445566778899"
        channel = Channel(
            name="TestCh",
            key_hex=key_hex,
            channel_hash=Channel.compute_channel_hash(key_hex),
            visibility="community",
            enabled=True,
        )
        db_session.add(channel)
        db_session.commit()

        assert channel.id is not None
        assert channel.name == "TestCh"
        assert channel.key_hex == key_hex
        assert channel.visibility == "community"
        assert channel.enabled is True

    def test_channel_repr(self, db_session) -> None:
        """Test channel string representation."""
        channel = Channel(
            name="MyChannel",
            key_hex="AA" * 16,
            channel_hash="AB",
            visibility="member",
        )
        assert repr(channel) == "<Channel(name=MyChannel, hash=AB, visibility=member)>"

    def test_compute_channel_hash_aes128(self) -> None:
        """Test channel hash computation for AES-128 key (32 hex chars)."""
        key_hex = "8B3387E9C5CDEA6AC9E5EDBAA115CD72"
        expected = hashlib.sha256(bytes.fromhex(key_hex)).digest()[:1].hex().upper()
        result = Channel.compute_channel_hash(key_hex)
        assert result == expected
        assert len(result) == 2

    def test_compute_channel_hash_aes256(self) -> None:
        """Test channel hash computation for AES-256 key (64 hex chars)."""
        key_hex = "A" * 64
        expected = hashlib.sha256(bytes.fromhex(key_hex)).digest()[:1].hex().upper()
        result = Channel.compute_channel_hash(key_hex)
        assert result == expected
        assert len(result) == 2

    def test_masked_key_normal(self) -> None:
        """Test masked key shows first/last 4 chars for long keys."""
        channel = Channel(
            name="Ch",
            key_hex="AABBCCDDEEFF00112233445566778899",
            channel_hash="AB",
        )
        assert channel.masked_key == "AABB...8899"

    def test_masked_key_short(self) -> None:
        """Test masked key returns full key when <= 8 chars."""
        channel = Channel(
            name="Ch",
            key_hex="AABBCCDD",
            channel_hash="AB",
        )
        assert channel.masked_key == "AABBCCDD"

    def test_channel_visibility_enum(self) -> None:
        """Test ChannelVisibility enum values."""
        assert ChannelVisibility.COMMUNITY.value == "community"
        assert ChannelVisibility.MEMBER.value == "member"
        assert ChannelVisibility.OPERATOR.value == "operator"
        assert ChannelVisibility.ADMIN.value == "admin"

    def test_channel_unique_name_constraint(self, db_session) -> None:
        """Test that duplicate channel names raise an error."""
        key1 = "AABBCCDDEEFF00112233445566778899"
        key2 = "11223344556677889900AABBCCDDEEFF"
        ch1 = Channel(
            name="Unique",
            key_hex=key1,
            channel_hash=Channel.compute_channel_hash(key1),
        )
        ch2 = Channel(
            name="Unique",
            key_hex=key2,
            channel_hash=Channel.compute_channel_hash(key2),
        )
        db_session.add(ch1)
        db_session.commit()
        db_session.add(ch2)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_channel_default_values(self, db_session) -> None:
        """Test channel default visibility and enabled."""
        key_hex = "AABBCCDDEEFF00112233445566778899"
        channel = Channel(
            name="Defaults",
            key_hex=key_hex,
            channel_hash=Channel.compute_channel_hash(key_hex),
        )
        db_session.add(channel)
        db_session.commit()

        assert channel.visibility == "community"
        assert channel.enabled is True


class TestChannelCreateSchema:
    """Tests for ChannelCreate Pydantic schema."""

    def test_valid_32_char_key(self) -> None:
        """Test valid AES-128 key (32 hex chars)."""
        schema = ChannelCreate(
            name="Test",
            key_hex="aabbccddeeff00112233445566778899",
        )
        assert schema.key_hex == "AABBCCDDEEFF00112233445566778899"

    def test_valid_64_char_key(self) -> None:
        """Test valid AES-256 key (64 hex chars)."""
        key = "A" * 64
        schema = ChannelCreate(name="Test", key_hex=key)
        assert schema.key_hex == key

    def test_key_hex_uppercases(self) -> None:
        """Test that key_hex is normalized to uppercase."""
        schema = ChannelCreate(
            name="Test",
            key_hex="aabbccddeeff00112233445566778899",
        )
        assert schema.key_hex == "AABBCCDDEEFF00112233445566778899"

    def test_key_hex_strips_whitespace(self) -> None:
        """Test that key_hex strips whitespace."""
        schema = ChannelCreate(
            name="Test",
            key_hex="  AABBCCDDEEFF00112233445566778899  ",
        )
        assert schema.key_hex == "AABBCCDDEEFF00112233445566778899"

    def test_invalid_key_non_hex(self) -> None:
        """Test that non-hex characters are rejected."""
        with pytest.raises(ValidationError, match="hexadecimal"):
            ChannelCreate(name="Test", key_hex="G" * 32)

    def test_invalid_key_wrong_length(self) -> None:
        """Test that wrong-length keys are rejected."""
        with pytest.raises(ValidationError):
            ChannelCreate(name="Test", key_hex="A" * 16)

    def test_invalid_key_too_long(self) -> None:
        """Test that keys longer than 64 chars are rejected."""
        with pytest.raises(ValidationError):
            ChannelCreate(name="Test", key_hex="A" * 128)

    def test_name_required(self) -> None:
        """Test that name is required."""
        with pytest.raises(ValidationError):
            ChannelCreate(key_hex="A" * 32)  # type: ignore[call-arg]

    def test_name_too_long(self) -> None:
        """Test that name max length is 100."""
        with pytest.raises(ValidationError):
            ChannelCreate(name="X" * 101, key_hex="A" * 32)

    def test_default_visibility(self) -> None:
        """Test default visibility is community."""
        schema = ChannelCreate(name="Test", key_hex="A" * 32)
        assert schema.visibility == "community"

    def test_default_enabled(self) -> None:
        """Test default enabled is True."""
        schema = ChannelCreate(name="Test", key_hex="A" * 32)
        assert schema.enabled is True


class TestChannelUpdateSchema:
    """Tests for ChannelUpdate Pydantic schema."""

    def test_key_hex_none_passthrough(self) -> None:
        """Test that None key_hex is allowed."""
        schema = ChannelUpdate()
        assert schema.key_hex is None

    def test_valid_key_hex(self) -> None:
        """Test valid key_hex update."""
        schema = ChannelUpdate(key_hex="A" * 32)
        assert schema.key_hex == "A" * 32

    def test_key_hex_uppercases(self) -> None:
        """Test that key_hex is normalized to uppercase."""
        schema = ChannelUpdate(key_hex="a" * 32)
        assert schema.key_hex == "A" * 32

    def test_invalid_key_non_hex(self) -> None:
        """Test that non-hex characters are rejected."""
        with pytest.raises(ValidationError, match="hexadecimal"):
            ChannelUpdate(key_hex="Z" * 32)

    def test_invalid_key_wrong_length(self) -> None:
        """Test that wrong-length keys are rejected."""
        with pytest.raises(ValidationError):
            ChannelUpdate(key_hex="A" * 48)

    def test_all_fields_optional(self) -> None:
        """Test that all fields are optional."""
        schema = ChannelUpdate()
        assert schema.key_hex is None
        assert schema.visibility is None
        assert schema.enabled is None
