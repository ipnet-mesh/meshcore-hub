"""Shared utilities for fetching event observer data."""

from collections.abc import Iterable

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.sql.expression import SQLColumnExpression

from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import EventObserver, Node, NodeTag
from meshcore_hub.common.schemas.messages import ObserverInfo


def observed_by_filter_clause(
    event_type: str,
    event_hash_col: SQLColumnExpression[str | None],
    observer_public_keys: list[str],
) -> ColumnElement[bool]:
    """Return a WHERE clause matching events observed by any of the given
    observer node public keys, via the event_observers junction table.

    Args:
        event_type: Type of event ('message', 'advertisement', 'telemetry', 'trace')
        event_hash_col: The event_hash column of the event table being filtered
            (e.g. ``Message.event_hash``).
        observer_public_keys: Observer node public keys to filter by.

    Returns:
        A SQLAlchemy boolean expression suitable for ``query.where(...)``.
    """
    return event_hash_col.in_(
        select(EventObserver.event_hash)
        .join(Node, EventObserver.observer_node_id == Node.id)
        .where(
            EventObserver.event_type == event_type,
            Node.public_key.in_(observer_public_keys),
        )
    )


def fetch_observers_for_events(
    session: DbSession,
    event_type: str,
    event_hashes: list[str],
) -> dict[str, list[ObserverInfo]]:
    """Fetch observer info for a list of events by their hashes.

    Args:
        session: Database session
        event_type: Type of event ('message', 'advertisement', etc.)
        event_hashes: List of event hashes to fetch observers for

    Returns:
        Dict mapping event_hash to list of ObserverInfo objects
    """
    if not event_hashes:
        return {}

    query = (
        select(
            EventObserver.event_hash,
            EventObserver.snr,
            EventObserver.path_len,
            EventObserver.observed_at,
            Node.id.label("node_id"),
            Node.public_key,
            Node.name,
        )
        .join(Node, EventObserver.observer_node_id == Node.id)
        .where(EventObserver.event_type == event_type)
        .where(EventObserver.event_hash.in_(event_hashes))
        .order_by(EventObserver.observed_at)
    )

    results = session.execute(query).all()

    observers_by_hash: dict[str, list[ObserverInfo]] = {}

    node_ids = [r.node_id for r in results]
    tag_names: dict[str, str] = {}
    if node_ids:
        tag_query = (
            select(NodeTag.node_id, NodeTag.value)
            .where(NodeTag.node_id.in_(node_ids))
            .where(NodeTag.key == "name")
        )
        for node_id, value in session.execute(tag_query).all():
            tag_names[node_id] = value

    for row in results:
        if row.event_hash not in observers_by_hash:
            observers_by_hash[row.event_hash] = []

        observers_by_hash[row.event_hash].append(
            ObserverInfo(
                node_id=row.node_id,
                public_key=row.public_key,
                name=row.name,
                tag_name=tag_names.get(row.node_id),
                snr=row.snr,
                path_len=row.path_len,
                observed_at=row.observed_at,
            )
        )

    return observers_by_hash


def resolve_sender_names(
    session: DbSession,
    prefixes: Iterable[str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve sender pubkey prefixes to node names and name-tag values.

    Messages store a leading slice of the sender's public key
    (``pubkey_prefix``). This looks up the matching nodes and returns two
    dicts, each keyed by the 12-char prefix: one of node names and one of
    "name" tag values.

    All prefixes are batched into a single pair of queries (one for names,
    one for tags) rather than a lookup per prefix.

    Args:
        session: Database session
        prefixes: Sender pubkey prefixes to resolve

    Returns:
        Tuple of (names_by_prefix, tag_names_by_prefix)
    """
    names: dict[str, str] = {}
    tag_names: dict[str, str] = {}

    unique = {p for p in prefixes if p}
    if not unique:
        return names, tag_names

    # One indexable LIKE 'prefix%' term per prefix, ORed together. Tolerates
    # variable-length prefixes (unlike substr(...) IN), preserving the
    # per-prefix startswith semantics this replaces.
    clause = or_(*[Node.public_key.startswith(p) for p in unique])

    name_query = select(Node.public_key, Node.name).where(clause)
    for public_key, name in session.execute(name_query).all():
        if name:
            names[public_key[:12]] = name

    tag_query = (
        select(Node.public_key, NodeTag.value)
        .join(NodeTag, Node.id == NodeTag.node_id)
        .where(clause)
        .where(NodeTag.key == "name")
    )
    for public_key, value in session.execute(tag_query).all():
        tag_names[public_key[:12]] = value

    return names, tag_names
