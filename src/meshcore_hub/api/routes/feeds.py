"""RSS/Atom feed routes for public mesh data.

Four feeds, each in RSS 2.0 and Atom:

- ``messages`` — newest messages across anonymous-visible channels
- ``adverts`` — newest advert per node (deduplicated by ``public_key``)
- ``nodes`` — newest nodes by ``created_at``
- ``channels/{idx}`` — messages on one community-visibility, enabled channel

Feeds are hard-pinned to the **logged-out view**: visibility is always
computed at the anonymous level (community channels + built-in public idx
17), spam filtering cannot be disabled via request parameters, and identity
headers (``X-User-Id`` / ``X-User-Roles``) are deliberately never read —
feeds must never leak member/operator/admin-channel content regardless of
who (or what proxy) asks. There are no user-controllable filters or
pagination so the path-based cache keys stay stable.

Responses are cached behind the shared ``@cached`` machinery with a
``public, max-age`` Cache-Control (safe because the content is
anonymous-pinned) and are invalidated by ``invalidate_messages`` /
``invalidate_advertisements`` / ``invalidate_channels``.
"""

import contextvars
import functools
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.orm import aliased, selectinload

from meshcore_hub.api.auth import RequireRead
from meshcore_hub.api.cache import cached
from meshcore_hub.api.channel_visibility import get_visible_channel_indices
from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.api.feed_xml import FeedItem, FeedMeta, build_atom, build_rss
from meshcore_hub.api.observer_utils import resolve_sender_names
from meshcore_hub.collector.letsmesh_decoder import LetsMeshPacketDecoder
from meshcore_hub.common.models import Advertisement, Channel, Message, Node

router = APIRouter()

# Built-in public channel (no DB row; labelled by the packet decoder).
BUILTIN_PUBLIC_CHANNEL_IDX = 17

FEED_ITEM_LIMIT = 50

# The @cached response_builder runs after the key builder (same thread /
# task context), so the key builder stashes the request for the builder to
# read the feed TTL off app.state. Set on every request, cache HIT or MISS.
_feed_request_ctx: contextvars.ContextVar[Optional[Request]] = contextvars.ContextVar(
    "meshcore_feed_request", default=None
)


def _feeds_key_builder(request: Request) -> str:
    """Path-based cache key — no query params exist on feed endpoints."""
    _feed_request_ctx.set(request)
    return f"feeds:{request.url.path}"


def _feed_response(xml: str, media_type: str) -> Response:
    """Wrap an XML body in a public, max-age response (TR-3)."""
    request = _feed_request_ctx.get()
    ttl = (
        getattr(request.app.state, "redis_cache_ttl_feeds", 300)
        if request is not None
        else 300
    )
    return Response(
        content=xml,
        media_type=media_type,
        headers={"Cache-Control": f"public, max-age={ttl}"},
    )


def _rss_response(xml: str) -> Response:
    return _feed_response(xml, "application/rss+xml; charset=utf-8")


def _atom_response(xml: str) -> Response:
    return _feed_response(xml, "application/atom+xml; charset=utf-8")


def _require_feeds_enabled(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """404 fast-path before any cache interaction when feeds are off (FR-7)."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        request = next((v for v in kwargs.values() if isinstance(v, Request)), None)
        if request is not None and not getattr(
            request.app.state, "feeds_enabled", True
        ):
            raise HTTPException(status_code=404, detail="Feeds are disabled")
        return func(*args, **kwargs)

    return wrapper


def _base_url(request: Request) -> str:
    """Public (web-tier) origin for absolute links (TR-6).

    Precedence: the configured canonical URL (``WEB_PUBLIC_URL`` — stable
    no matter how the request reached the API), then the proxy-forwarded
    host/proto (the web tier synthesizes these), then the request's own
    base URL (direct API access). All feed item links point at SPA pages
    on the web tier; the API itself is usually not publicly reachable.
    """
    public_url = getattr(request.app.state, "web_public_url", None)
    if public_url:
        return str(public_url).rstrip("/")
    host = request.headers.get("x-forwarded-host")
    proto = request.headers.get("x-forwarded-proto")
    if host:
        return f"{proto or 'http'}://{host}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _feed_meta(request: Request, title_suffix: str, link_path: str) -> FeedMeta:
    base = _base_url(request)
    network_name = getattr(request.app.state, "network_name", "MeshCore Network")
    return FeedMeta(
        title=f"{network_name} — {title_suffix}",
        link=f"{base}{link_path}",
        description=f"{network_name} mesh activity: {title_suffix.lower()}",
        # Advertise the clean web-tier URL (/feeds/...) — feed readers
        # refresh from the self URL, and the API path is not public.
        feed_url=f"{base}{request.url.path.removeprefix('/api/v1')}",
    )


def _node_display_name(
    name: Optional[str], node: Optional[Node], public_key: str
) -> str:
    """Tag name > explicit name > node name > key prefix (selectin tags)."""
    if node is not None and node.tags:
        for tag in node.tags:
            if tag.key == "name" and tag.value:
                return tag.value
    if name:
        return name
    if node is not None and node.name:
        return node.name
    return public_key[:12]


def _resolve_feed_channel(session: DbSession, channel_idx: int) -> str:
    """Validate a per-channel feed target and resolve its display title.

    Stricter than /messages (which shows history from disabled channels)
    and the anonymous /channels list (which lists disabled community
    channels): a disabled channel no longer receives traffic, so its feed
    is dead and 404s instead of serving stale history. The built-in public
    channel (idx 17) is always allowed.
    """
    if channel_idx == BUILTIN_PUBLIC_CHANNEL_IDX:
        try:
            labels = LetsMeshPacketDecoder(channel_keys=[]).channel_labels_by_index()
            return labels.get(BUILTIN_PUBLIC_CHANNEL_IDX, "Public")
        except Exception:
            return "Public"

    channels = (
        session.execute(
            select(Channel).where(Channel.channel_hash == f"{channel_idx:02X}")
        )
        .scalars()
        .all()
    )
    for channel in channels:
        if channel.visibility == "community" and channel.enabled:
            return channel.name
    raise HTTPException(
        status_code=404,
        detail=f"Channel {channel_idx} is not available as a public feed",
    )


def _spam_filter_clause(request: Request) -> Optional[ColumnElement[bool]]:
    """Always-on spam hide-filter, mirroring routes/messages.py.

    Respects the master switch: when spam detection is disabled no message
    is filtered regardless of any stored score.
    """
    if not getattr(request.app.state, "spam_detection_enabled", False):
        return None
    threshold = getattr(request.app.state, "spam_score_threshold", 0.65)
    return or_(Message.spam_score < threshold, Message.spam_score.is_(None))


def _query_messages(
    session: DbSession,
    request: Request,
    channel_idx: Optional[int] = None,
) -> list[Message]:
    """Newest messages pinned to the anonymous visibility level."""
    query = select(Message)

    if channel_idx is not None:
        query = query.where(Message.channel_idx == channel_idx)
    else:
        # Anonymous-pinned visibility: never consult X-User-* headers.
        visible = get_visible_channel_indices(session, 0)
        query = query.where(
            or_(
                Message.message_type != "channel",
                Message.channel_idx.is_(None),
                Message.channel_idx.in_(visible),
            )
        )

    spam_filter = _spam_filter_clause(request)
    if spam_filter is not None:
        query = query.where(spam_filter)

    query = query.order_by(Message.received_at.desc()).limit(FEED_ITEM_LIMIT)
    return list(session.execute(query).scalars().all())


def _message_items(
    session: DbSession, messages: list[Message], base: str
) -> list[FeedItem]:
    """Message rows -> feed items with SPA deep links (FR-2)."""
    prefixes = [m.pubkey_prefix for m in messages if m.pubkey_prefix]
    names, tag_names = resolve_sender_names(session, prefixes)

    items: list[FeedItem] = []
    for message in messages:
        prefix = message.pubkey_prefix
        sender = None
        if prefix:
            sender = tag_names.get(prefix) or names.get(prefix) or prefix
        title = f"{sender or message.message_type}: {message.text[:80]}".strip()

        guid = message.packet_hash or f"msg:{message.id}"
        if message.packet_hash:
            link = f"{base}/packets/hash/{message.packet_hash}"
        else:
            link = f"{base}/messages"

        items.append(
            FeedItem(
                title=title,
                description=message.text or "",
                guid=guid,
                link=link,
                pub_date=message.received_at,
                guid_is_permalink=False,
            )
        )
    return items


def _query_newest_adverts(session: DbSession) -> list[Advertisement]:
    """Newest advert per node (DISTINCT ON), newest nodes first (FR-1).

    Nodes re-advertise constantly; raw rows would repeat the same handful
    of nodes within minutes, so the feed carries one item per public key.
    """
    newest_subq = (
        select(Advertisement)
        .distinct(Advertisement.public_key)
        .order_by(Advertisement.public_key, Advertisement.received_at.desc())
        .subquery()
    )
    NewestAdvert = aliased(Advertisement, newest_subq, adapt_on_names=True)
    query = (
        select(NewestAdvert)
        .order_by(NewestAdvert.received_at.desc())
        .limit(FEED_ITEM_LIMIT)
    )
    return list(session.execute(query).scalars().all())


def _advert_items(
    session: DbSession, adverts: list[Advertisement], base: str
) -> list[FeedItem]:
    nodes_by_id: dict[str, Node] = {}
    node_ids = {a.node_id for a in adverts if a.node_id}
    if node_ids:
        nodes = (
            session.execute(
                select(Node)
                .where(Node.id.in_(node_ids))
                .options(selectinload(Node.tags))
            )
            .scalars()
            .all()
        )
        nodes_by_id = {n.id: n for n in nodes}

    items: list[FeedItem] = []
    for advert in adverts:
        node = nodes_by_id.get(advert.node_id) if advert.node_id else None
        title = _node_display_name(advert.name, node, advert.public_key)
        description = (
            f"{advert.adv_type or 'node'} advertisement; "
            f"advertised at {_format_ts(advert.advert_timestamp)}, "
            f"received {_format_ts(advert.received_at)}"
        )
        items.append(
            FeedItem(
                title=title,
                description=description,
                guid=f"advert:{advert.id}",
                link=f"{base}/nodes/{advert.public_key}",
                pub_date=advert.received_at,
                guid_is_permalink=False,
            )
        )
    return items


def _query_new_nodes(session: DbSession) -> list[Node]:
    """Newest 50 nodes by created_at — 'who just joined the mesh'."""
    query = select(Node).order_by(Node.created_at.desc()).limit(FEED_ITEM_LIMIT)
    return list(session.execute(query).scalars().all())


def _node_items(nodes: list[Node], base: str) -> list[FeedItem]:
    items: list[FeedItem] = []
    for node in nodes:
        title = _node_display_name(None, node, node.public_key)
        description = (
            f"{node.adv_type or 'node'} joined the mesh; "
            f"last seen {_format_ts(node.last_seen)}"
        )
        items.append(
            FeedItem(
                title=title,
                description=description,
                guid=f"node:{node.public_key}",
                link=f"{base}/nodes/{node.public_key}",
                pub_date=node.created_at,
                guid_is_permalink=False,
            )
        )
    return items


def _format_ts(value: Optional[datetime]) -> str:
    if value is None:
        return "unknown"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


# --------------------------------------------------------------------------
# Messages feed
# --------------------------------------------------------------------------


@router.get("/messages.xml")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_rss_response,
)
def messages_rss(_: RequireRead, session: DbSession, request: Request) -> str:
    """Public messages feed (RSS 2.0)."""
    meta = _feed_meta(request, "Public Messages", "/messages")
    items = _message_items(
        session, _query_messages(session, request), _base_url(request)
    )
    return build_rss(meta, items)


@router.get("/messages.atom")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_atom_response,
)
def messages_atom(_: RequireRead, session: DbSession, request: Request) -> str:
    """Public messages feed (Atom)."""
    meta = _feed_meta(request, "Public Messages", "/messages")
    items = _message_items(
        session, _query_messages(session, request), _base_url(request)
    )
    return build_atom(meta, items)


# --------------------------------------------------------------------------
# Adverts feed
# --------------------------------------------------------------------------


@router.get("/adverts.xml")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_rss_response,
)
def adverts_rss(_: RequireRead, session: DbSession, request: Request) -> str:
    """Node adverts feed, deduplicated per node (RSS 2.0)."""
    meta = _feed_meta(request, "Node Adverts", "/advertisements")
    items = _advert_items(session, _query_newest_adverts(session), _base_url(request))
    return build_rss(meta, items)


@router.get("/adverts.atom")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_atom_response,
)
def adverts_atom(_: RequireRead, session: DbSession, request: Request) -> str:
    """Node adverts feed, deduplicated per node (Atom)."""
    meta = _feed_meta(request, "Node Adverts", "/advertisements")
    items = _advert_items(session, _query_newest_adverts(session), _base_url(request))
    return build_atom(meta, items)


# --------------------------------------------------------------------------
# New nodes feed
# --------------------------------------------------------------------------


@router.get("/nodes.xml")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_rss_response,
)
def nodes_rss(_: RequireRead, session: DbSession, request: Request) -> str:
    """New nodes feed (RSS 2.0)."""
    meta = _feed_meta(request, "New Nodes", "/nodes")
    items = _node_items(_query_new_nodes(session), _base_url(request))
    return build_rss(meta, items)


@router.get("/nodes.atom")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_atom_response,
)
def nodes_atom(_: RequireRead, session: DbSession, request: Request) -> str:
    """New nodes feed (Atom)."""
    meta = _feed_meta(request, "New Nodes", "/nodes")
    items = _node_items(_query_new_nodes(session), _base_url(request))
    return build_atom(meta, items)


# --------------------------------------------------------------------------
# Per-channel messages feed
# --------------------------------------------------------------------------


@router.get("/channels/{channel_idx}.xml")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_rss_response,
)
def channel_rss(
    _: RequireRead,
    session: DbSession,
    request: Request,
    channel_idx: int,
) -> str:
    """Per-channel messages feed (RSS 2.0)."""
    channel_name = _resolve_feed_channel(session, channel_idx)
    meta = _feed_meta(request, channel_name, f"/messages?channel_idx={channel_idx}")
    items = _message_items(
        session,
        _query_messages(session, request, channel_idx=channel_idx),
        _base_url(request),
    )
    return build_rss(meta, items)


@router.get("/channels/{channel_idx}.atom")
@_require_feeds_enabled
@cached(
    "feeds",
    ttl_setting="redis_cache_ttl_feeds",
    key_builder=_feeds_key_builder,
    response_builder=_atom_response,
)
def channel_atom(
    _: RequireRead,
    session: DbSession,
    request: Request,
    channel_idx: int,
) -> str:
    """Per-channel messages feed (Atom)."""
    channel_name = _resolve_feed_channel(session, channel_idx)
    meta = _feed_meta(request, channel_name, f"/messages?channel_idx={channel_idx}")
    items = _message_items(
        session,
        _query_messages(session, request, channel_idx=channel_idx),
        _base_url(request),
    )
    return build_atom(meta, items)
