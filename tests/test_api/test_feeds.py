"""Tests for the RSS/Atom feed endpoints (api/routes/feeds.py)."""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from meshcore_hub.common.models import Advertisement, Channel, Message, Node

ATOM_NS = "{http://www.w3.org/2005/Atom}"
NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def _channel_idx(channel: Channel) -> int:
    return int(channel.channel_hash, 16)


def _text(element: ET.Element, path: str) -> str:
    """findtext with Optional narrowed for mypy."""
    value = element.findtext(path)
    assert value is not None, f"missing text at {path}"
    return value


def _attr(element: ET.Element, path: str, name: str) -> str:
    """Element attribute lookup with Optionals narrowed for mypy."""
    child = element.find(path)
    assert child is not None, f"missing element at {path}"
    value = child.get(name)
    assert value is not None, f"missing attribute {name} at {path}"
    return value


def _add_message(
    session,
    *,
    text="hello",
    message_type="channel",
    channel_idx=17,
    pubkey_prefix=None,
    received_at=NOW,
    packet_hash=None,
    spam_score=None,
):
    message = Message(
        message_type=message_type,
        channel_idx=channel_idx,
        pubkey_prefix=pubkey_prefix,
        text=text,
        received_at=received_at,
        packet_hash=packet_hash,
        spam_score=spam_score,
    )
    session.add(message)
    session.commit()
    return message


class TestFeedWellFormed:
    """RSS/Atom documents parse and carry the right roots/namespaces."""

    @pytest.mark.parametrize(
        "path,root_tag",
        [
            ("/api/v1/feeds/messages.xml", "rss"),
            ("/api/v1/feeds/adverts.xml", "rss"),
            ("/api/v1/feeds/nodes.xml", "rss"),
            ("/api/v1/feeds/channels/17.xml", "rss"),
        ],
    )
    def test_rss_documents_parse(self, client_no_auth, path, root_tag):
        response = client_no_auth.get(path)
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        assert root.tag == root_tag
        assert root.get("version") == "2.0"
        assert root.find("channel/title") is not None
        assert root.find("channel/link") is not None

    @pytest.mark.parametrize(
        "path",
        [
            "/api/v1/feeds/messages.atom",
            "/api/v1/feeds/adverts.atom",
            "/api/v1/feeds/nodes.atom",
            "/api/v1/feeds/channels/17.atom",
        ],
    )
    def test_atom_documents_parse(self, client_no_auth, path):
        response = client_no_auth.get(path)
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        assert root.tag == f"{ATOM_NS}feed"
        assert root.find(f"{ATOM_NS}title") is not None
        assert root.find(f"{ATOM_NS}updated") is not None


class TestMessagesFeedVisibility:
    def test_community_message_present(self, client_no_auth, api_db_session):
        _add_message(api_db_session, text="community hello", channel_idx=17)
        response = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert response.status_code == 200
        assert "community hello" in response.text

    def test_member_and_admin_channels_absent_even_for_admin_header(
        self,
        client_no_auth,
        api_db_session,
        sample_member_channel,
        sample_admin_channel,
    ):
        """Feeds are anonymous-pinned: a spoofed/real admin role header must
        never unlock member/admin channel content in a feed."""
        _add_message(
            api_db_session,
            text="secret member",
            channel_idx=_channel_idx(sample_member_channel),
        )
        _add_message(
            api_db_session,
            text="secret admin",
            channel_idx=_channel_idx(sample_admin_channel),
        )
        response = client_no_auth.get(
            "/api/v1/feeds/messages.xml", headers={"X-User-Roles": "admin"}
        )
        assert response.status_code == 200
        assert "secret member" not in response.text
        assert "secret admin" not in response.text

    def test_non_channel_messages_included(self, client_no_auth, api_db_session):
        _add_message(
            api_db_session,
            text="direct note",
            message_type="direct",
            channel_idx=None,
            pubkey_prefix="abc123def456",
        )
        response = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert "direct note" in response.text

    def test_spam_excluded_when_detection_enabled(self, client_spam, api_db_session):
        _add_message(api_db_session, text="clean one", spam_score=0.1)
        _add_message(api_db_session, text="spammy one", spam_score=0.9)
        response = client_spam.get("/api/v1/feeds/messages.xml")
        assert response.status_code == 200
        assert "clean one" in response.text
        assert "spammy one" not in response.text

    def test_spam_master_switch_off_shows_everything(
        self, client_no_auth, api_db_session
    ):
        """With detection disabled, stored scores are ignored entirely."""
        _add_message(api_db_session, text="scored while on", spam_score=0.99)
        response = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert "scored while on" in response.text


class TestFeedEscaping:
    def test_script_and_ampersand_escaped(self, client_no_auth, api_db_session):
        _add_message(
            api_db_session,
            text='<script>alert("x")</script> & <b>bold</b>',
            channel_idx=17,
        )
        response = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        descriptions = [
            el.text or "" for el in root.findall("channel/item/description")
        ]
        assert any('<script>alert("x")</script>' in d for d in descriptions)
        # Raw markup must never appear in the serialized document.
        assert "<script>alert" not in response.text
        assert "&amp;" in response.text


class TestAdvertsFeed:
    def test_adverts_dedup_keeps_newest_per_node(
        self, client_no_auth, api_db_session, sample_node
    ):
        old = Advertisement(
            public_key=sample_node.public_key,
            name="OldName",
            received_at=NOW - timedelta(hours=2),
        )
        new = Advertisement(
            public_key=sample_node.public_key,
            name="NewName",
            received_at=NOW,
        )
        api_db_session.add_all([old, new])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/feeds/adverts.xml")
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        items = root.findall("channel/item")
        assert len(items) == 1
        assert "NewName" in (items[0].findtext("title") or "")
        guid = items[0].findtext("guid")
        assert guid == f"advert:{new.id}"
        assert _attr(items[0], "guid", "isPermaLink") == "false"


class TestNodesFeed:
    def test_nodes_ordered_by_created_at_with_links(
        self, client_no_auth, api_db_session
    ):
        older = Node(
            public_key="11" * 32, name="Older", created_at=NOW - timedelta(days=1)
        )
        newer = Node(public_key="22" * 32, name="Newer", created_at=NOW)
        api_db_session.add_all([older, newer])
        api_db_session.commit()

        response = client_no_auth.get("/api/v1/feeds/nodes.xml")
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        items = root.findall("channel/item")
        assert len(items) == 2
        titles = [i.findtext("title") for i in items]
        assert titles.index("Newer") < titles.index("Older")
        assert items[0].findtext("guid") == f"node:{newer.public_key}"
        assert _text(items[0], "link").endswith(f"/nodes/{newer.public_key}")


class TestPerChannelFeed:
    def test_member_channel_404(self, client_no_auth, sample_member_channel):
        response = client_no_auth.get(
            f"/api/v1/feeds/channels/{_channel_idx(sample_member_channel)}.xml"
        )
        assert response.status_code == 404

    def test_disabled_community_channel_404(self, client_no_auth, api_db_session):
        channel = Channel(
            name="DisabledChan",
            key_hex="0102030405060708090A0B0C0D0E0F10",
            channel_hash=Channel.compute_channel_hash(
                "0102030405060708090A0B0C0D0E0F10"
            ),
            visibility="community",
            enabled=False,
        )
        api_db_session.add(channel)
        api_db_session.commit()
        response = client_no_auth.get(
            f"/api/v1/feeds/channels/{_channel_idx(channel)}.xml"
        )
        assert response.status_code == 404

    def test_title_uses_db_channel_name(
        self, client_no_auth, sample_channel, api_db_session
    ):
        _add_message(
            api_db_session,
            text="on the channel",
            channel_idx=_channel_idx(sample_channel),
        )
        response = client_no_auth.get(
            f"/api/v1/feeds/channels/{_channel_idx(sample_channel)}.xml"
        )
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        title = _text(root, "channel/title")
        assert sample_channel.name in title
        assert "on the channel" in response.text

    def test_builtin_public_channel_titled_public(self, client_no_auth, api_db_session):
        _add_message(api_db_session, text="public wave", channel_idx=17)
        response = client_no_auth.get("/api/v1/feeds/channels/17.atom")
        assert response.status_code == 200
        root = ET.fromstring(response.text)
        title = root.findtext(f"{ATOM_NS}title")
        assert title is not None and "Public" in title

    def test_unknown_channel_404(self, client_no_auth):
        response = client_no_auth.get("/api/v1/feeds/channels/250.xml")
        assert response.status_code == 404


class TestFeedItemLinks:
    def test_message_links_to_packet_hash(self, client_no_auth, api_db_session):
        _add_message(
            api_db_session,
            text="with hash",
            channel_idx=17,
            packet_hash="aabbccddeeff00112233445566778899",
        )
        _add_message(
            api_db_session,
            text="without hash",
            channel_idx=17,
            packet_hash=None,
        )
        response = client_no_auth.get("/api/v1/feeds/messages.xml")
        root = ET.fromstring(response.text)
        links = [_text(i, "link") for i in root.findall("channel/item")]
        guids = [
            (_text(i, "guid"), _attr(i, "guid", "isPermaLink"))
            for i in root.findall("channel/item")
        ]
        assert any(
            link.endswith("/packets/hash/aabbccddeeff00112233445566778899")
            for link in links
        )
        assert any(link.endswith("/messages") for link in links)
        assert ("aabbccddeeff00112233445566778899", "false") in guids
        assert any(guid.startswith("msg:") for guid, _ in guids)

    def test_advert_and_node_links(
        self, client_no_auth, api_db_session, sample_advertisement, sample_node
    ):
        response = client_no_auth.get("/api/v1/feeds/adverts.xml")
        root = ET.fromstring(response.text)
        assert _text(root, "channel/item/link").endswith(
            f"/nodes/{sample_advertisement.public_key}"
        )

    def test_channel_feed_link_uses_channel_idx_query(
        self, client_no_auth, api_db_session
    ):
        _add_message(api_db_session, text="chan", channel_idx=17)
        response = client_no_auth.get("/api/v1/feeds/channels/17.xml")
        root = ET.fromstring(response.text)
        assert _text(root, "channel/link").endswith("/messages?channel_idx=17")

    def test_forwarded_host_used_for_absolute_links(
        self, client_no_auth, api_db_session
    ):
        _add_message(api_db_session, text="fwd", channel_idx=17)
        response = client_no_auth.get(
            "/api/v1/feeds/messages.xml",
            headers={
                "X-Forwarded-Host": "hub.example.com",
                "X-Forwarded-Proto": "https",
            },
        )
        root = ET.fromstring(response.text)
        assert _text(root, "channel/link").startswith("https://hub.example.com/")

    def test_self_url_uses_clean_web_alias_not_api_path(
        self, client_no_auth, api_db_session
    ):
        """Feed readers refresh from the self URL — it must be the public
        web endpoint (/feeds/...), not the API-shaped /api/v1/feeds/...
        path (the API tier is not usually publicly reachable)."""
        _add_message(api_db_session, text="self", channel_idx=17)
        rss = client_no_auth.get("/api/v1/feeds/messages.xml")
        root = ET.fromstring(rss.text)
        self_href = _attr(root, f"channel/{ATOM_NS}link[@rel='self']", "href")
        assert self_href.endswith("/feeds/messages.xml")
        assert "/api/v1" not in self_href

        atom = client_no_auth.get("/api/v1/feeds/channels/17.atom")
        atom_root = ET.fromstring(atom.text)
        atom_href = _attr(atom_root, f"{ATOM_NS}link[@rel='self']", "href")
        assert atom_href.endswith("/feeds/channels/17.atom")
        assert "/api/v1" not in atom_href

    def test_web_public_url_overrides_request_headers(
        self, client_no_auth, api_db_session, monkeypatch
    ):
        """WEB_PUBLIC_URL pins the canonical public origin: it wins over
        forwarded headers and stays stable even when the request reached
        the API through an internal/odd origin (cached feeds don't bake in
        whichever host happened to populate them)."""
        _add_message(api_db_session, text="canonical", channel_idx=17)
        monkeypatch.setattr(
            client_no_auth.app.state,
            "web_public_url",
            "https://mesh.example.org",
        )
        response = client_no_auth.get(
            "/api/v1/feeds/messages.xml",
            headers={"X-Forwarded-Host": "internal-api:8000"},
        )
        root = ET.fromstring(response.text)
        assert _text(root, "channel/link").startswith("https://mesh.example.org/")
        assert _text(root, "channel/item/link").startswith("https://mesh.example.org/")


class TestFeedCaching:
    def test_content_type_and_public_cache_control(self, client_no_auth):
        response = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/rss+xml; charset=utf-8"
        cache_control = response.headers["cache-control"]
        assert cache_control.startswith("public")
        assert "max-age=" in cache_control

    def test_atom_content_type(self, client_no_auth):
        response = client_no_auth.get("/api/v1/feeds/messages.atom")
        assert response.headers["content-type"] == (
            "application/atom+xml; charset=utf-8"
        )

    def test_etag_304_and_x_cache_hit(self, client_no_auth):
        first = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert first.status_code == 200
        assert first.headers["x-cache"] == "MISS"
        etag = first.headers["etag"]

        second = client_no_auth.get(
            "/api/v1/feeds/messages.xml", headers={"If-None-Match": etag}
        )
        assert second.status_code == 304
        assert second.headers["x-cache"] == "HIT"
        assert second.headers["etag"] == etag

        # A plain re-fetch (no conditional) is a HIT carrying the same body.
        third = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert third.status_code == 200
        assert third.headers["x-cache"] == "HIT"
        assert third.content == first.content


class TestFeedKillSwitch:
    def test_disabled_feeds_404(self, client_no_auth, monkeypatch):
        monkeypatch.setattr(client_no_auth.app.state, "feeds_enabled", False)
        for path in (
            "/api/v1/feeds/messages.xml",
            "/api/v1/feeds/messages.atom",
            "/api/v1/feeds/adverts.xml",
            "/api/v1/feeds/nodes.xml",
            "/api/v1/feeds/channels/17.xml",
            "/api/v1/feeds/channels/17.atom",
        ):
            assert client_no_auth.get(path).status_code == 404

    def test_enabled_by_default(self, client_no_auth):
        assert client_no_auth.app.state.feeds_enabled is True


class TestFeedRedisOutage:
    def test_redis_error_returns_503(self, client_no_auth, monkeypatch):
        mock_cache = MagicMock()
        mock_cache.get.side_effect = RedisConnectionError("redis down")
        monkeypatch.setattr(
            client_no_auth.app.state, "redis_cache", mock_cache, raising=False
        )
        response = client_no_auth.get("/api/v1/feeds/messages.xml")
        assert response.status_code == 503
        assert response.json()["detail"] == "cache backend unavailable"


class TestFeedAuthInheritance:
    def test_read_key_required_when_configured(self, client_with_auth):
        response = client_with_auth.get("/api/v1/feeds/messages.xml")
        assert response.status_code == 401

    def test_read_key_grants_access(self, client_with_auth):
        response = client_with_auth.get(
            "/api/v1/feeds/messages.xml",
            headers={"Authorization": "Bearer test-read-key"},
        )
        assert response.status_code == 200
