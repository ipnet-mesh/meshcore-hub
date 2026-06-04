"""Tests for channel_visibility helpers."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meshcore_hub.api.channel_visibility import (
    get_all_known_channel_indices,
    get_max_visibility_level,
    get_visible_channel_indices,
    resolve_user_role,
)
from meshcore_hub.common.models import Base
from meshcore_hub.common.models.channel import Channel


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


def _make_request(
    headers: dict | None = None, app_state: dict | None = None
) -> MagicMock:
    """Create a mock FastAPI Request."""
    from types import SimpleNamespace

    request = MagicMock()
    request.headers = headers or {}
    state = SimpleNamespace(**(app_state or {}))
    request.app.state = state
    return request


class TestResolveUserRole:
    """Tests for resolve_user_role()."""

    def test_no_header_returns_none(self) -> None:
        """No X-User-Roles header returns None."""
        request = _make_request(headers={})
        assert resolve_user_role(request) is None

    def test_empty_header_returns_none(self) -> None:
        """Empty X-User-Roles header returns None."""
        request = _make_request(headers={"x-user-roles": ""})
        assert resolve_user_role(request) is None

    def test_admin_role(self) -> None:
        """Admin role is resolved correctly."""
        request = _make_request(headers={"x-user-roles": "admin"})
        assert resolve_user_role(request) == "admin"

    def test_operator_role(self) -> None:
        """Operator role is resolved correctly."""
        request = _make_request(headers={"x-user-roles": "operator"})
        assert resolve_user_role(request) == "operator"

    def test_member_role(self) -> None:
        """Member role is resolved correctly."""
        request = _make_request(headers={"x-user-roles": "member"})
        assert resolve_user_role(request) == "member"

    def test_admin_takes_precedence_over_member(self) -> None:
        """Admin takes precedence when multiple roles present."""
        request = _make_request(headers={"x-user-roles": "member,admin"})
        assert resolve_user_role(request) == "admin"

    def test_operator_takes_precedence_over_member(self) -> None:
        """Operator takes precedence over member."""
        request = _make_request(headers={"x-user-roles": "member,operator"})
        assert resolve_user_role(request) == "operator"

    def test_admin_takes_precedence_over_all(self) -> None:
        """Admin takes precedence over operator and member."""
        request = _make_request(headers={"x-user-roles": "member,operator,admin"})
        assert resolve_user_role(request) == "admin"

    def test_unknown_role_returns_none(self) -> None:
        """Unknown role returns None."""
        request = _make_request(headers={"x-user-roles": "viewer"})
        assert resolve_user_role(request) is None

    def test_custom_role_names(self) -> None:
        """Custom OIDC role names from app.state are recognized."""
        request = _make_request(
            headers={"x-user-roles": "superadmin,moderator"},
            app_state={
                "oidc_role_admin": "superadmin",
                "oidc_role_operator": "moderator",
                "oidc_role_member": "user",
            },
        )
        assert resolve_user_role(request) == "admin"

    def test_custom_member_role_name(self) -> None:
        """Custom member role name is recognized."""
        request = _make_request(
            headers={"x-user-roles": "user"},
            app_state={
                "oidc_role_member": "user",
            },
        )
        assert resolve_user_role(request) == "member"

    def test_whitespace_in_header(self) -> None:
        """Whitespace around role names is handled."""
        request = _make_request(headers={"x-user-roles": "  admin , member "})
        assert resolve_user_role(request) == "admin"


class TestGetMaxVisibilityLevel:
    """Tests for get_max_visibility_level()."""

    def test_none_returns_zero(self) -> None:
        """Anonymous users get level 0 (community only)."""
        assert get_max_visibility_level(None) == 0

    def test_community_returns_zero(self) -> None:
        assert get_max_visibility_level("community") == 0

    def test_member_returns_one(self) -> None:
        assert get_max_visibility_level("member") == 1

    def test_operator_returns_two(self) -> None:
        assert get_max_visibility_level("operator") == 2

    def test_admin_returns_three(self) -> None:
        assert get_max_visibility_level("admin") == 3

    def test_unknown_returns_zero(self) -> None:
        assert get_max_visibility_level("unknown") == 0


class TestGetVisibleChannelIndices:
    """Tests for get_visible_channel_indices()."""

    def test_always_includes_idx_17(self, db_session) -> None:
        """Built-in Public channel (idx 17) is always visible."""
        indices = get_visible_channel_indices(db_session, 0)
        assert 17 in indices

    def test_community_channels_visible_at_level_0(self, db_session) -> None:
        """Community channels are visible at level 0."""
        key = "AABBCCDDEEFF00112233445566778899"
        ch = Channel(
            name="Community",
            key_hex=key,
            channel_hash=Channel.compute_channel_hash(key),
            visibility="community",
        )
        db_session.add(ch)
        db_session.commit()

        indices = get_visible_channel_indices(db_session, 0)
        expected_idx = int(ch.channel_hash, 16)
        assert expected_idx in indices
        assert 17 in indices

    def test_member_channels_hidden_at_level_0(self, db_session) -> None:
        """Member channels are hidden at level 0."""
        key = "11223344556677889900AABBCCDDEEFF"
        ch = Channel(
            name="MembersOnly",
            key_hex=key,
            channel_hash=Channel.compute_channel_hash(key),
            visibility="member",
        )
        db_session.add(ch)
        db_session.commit()

        indices = get_visible_channel_indices(db_session, 0)
        ch_idx = int(ch.channel_hash, 16)
        assert ch_idx not in indices

    def test_member_channels_visible_at_level_1(self, db_session) -> None:
        """Member channels are visible at level 1."""
        key = "11223344556677889900AABBCCDDEEFF"
        ch = Channel(
            name="MemberCh",
            key_hex=key,
            channel_hash=Channel.compute_channel_hash(key),
            visibility="member",
        )
        db_session.add(ch)
        db_session.commit()

        indices = get_visible_channel_indices(db_session, 1)
        ch_idx = int(ch.channel_hash, 16)
        assert ch_idx in indices

    def test_admin_channels_visible_at_level_3(self, db_session) -> None:
        """Admin channels are visible at level 3."""
        key = "FFEEDDCCBBAA99887766554433221100"
        ch = Channel(
            name="AdminCh",
            key_hex=key,
            channel_hash=Channel.compute_channel_hash(key),
            visibility="admin",
        )
        db_session.add(ch)
        db_session.commit()

        indices = get_visible_channel_indices(db_session, 3)
        ch_idx = int(ch.channel_hash, 16)
        assert ch_idx in indices

    def test_admin_channels_hidden_at_level_1(self, db_session) -> None:
        """Admin channels are hidden at level 1."""
        key = "FFEEDDCCBBAA99887766554433221100"
        ch = Channel(
            name="AdminCh",
            key_hex=key,
            channel_hash=Channel.compute_channel_hash(key),
            visibility="admin",
        )
        db_session.add(ch)
        db_session.commit()

        indices = get_visible_channel_indices(db_session, 1)
        ch_idx = int(ch.channel_hash, 16)
        assert ch_idx not in indices

    def test_mixed_visibility_channels(self, db_session) -> None:
        """Multiple channels with different visibility levels."""
        pub_key = "AABBCCDDEEFF00112233445566778899"
        mem_key = "11223344556677889900AABBCCDDEEFF"
        adm_key = "FFEEDDCCBBAA99887766554433221100"

        for name, key, vis in [
            ("Community", pub_key, "community"),
            ("Member", mem_key, "member"),
            ("Admin", adm_key, "admin"),
        ]:
            db_session.add(
                Channel(
                    name=name,
                    key_hex=key,
                    channel_hash=Channel.compute_channel_hash(key),
                    visibility=vis,
                )
            )
        db_session.commit()

        level_0 = get_visible_channel_indices(db_session, 0)
        level_1 = get_visible_channel_indices(db_session, 1)
        level_3 = get_visible_channel_indices(db_session, 3)

        pub_idx = int(Channel.compute_channel_hash(pub_key), 16)
        mem_idx = int(Channel.compute_channel_hash(mem_key), 16)
        adm_idx = int(Channel.compute_channel_hash(adm_key), 16)

        assert pub_idx in level_0
        assert mem_idx not in level_0
        assert adm_idx not in level_0

        assert pub_idx in level_1
        assert mem_idx in level_1
        assert adm_idx not in level_1

        assert pub_idx in level_3
        assert mem_idx in level_3
        assert adm_idx in level_3

        assert 17 in level_0
        assert 17 in level_1
        assert 17 in level_3


class TestGetAllKnownChannelIndices:
    """Tests for get_all_known_channel_indices()."""

    def test_empty_db(self, db_session) -> None:
        """Empty DB returns empty set."""
        indices = get_all_known_channel_indices(db_session)
        assert indices == set()

    def test_returns_all_indices(self, db_session) -> None:
        """Returns all channel indices from DB."""
        key1 = "AABBCCDDEEFF00112233445566778899"
        key2 = "11223344556677889900AABBCCDDEEFF"
        for name, key in [("Ch1", key1), ("Ch2", key2)]:
            db_session.add(
                Channel(
                    name=name,
                    key_hex=key,
                    channel_hash=Channel.compute_channel_hash(key),
                )
            )
        db_session.commit()

        indices = get_all_known_channel_indices(db_session)
        idx1 = int(Channel.compute_channel_hash(key1), 16)
        idx2 = int(Channel.compute_channel_hash(key2), 16)
        assert indices == {idx1, idx2}

    def test_does_not_include_builtin_17(self, db_session) -> None:
        """Does not include the built-in Public channel (17) unless in DB."""
        indices = get_all_known_channel_indices(db_session)
        assert 17 not in indices
