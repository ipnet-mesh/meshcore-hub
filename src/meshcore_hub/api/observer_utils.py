"""Shared utilities for fetching event observer data."""

from sqlalchemy import select

from meshcore_hub.api.dependencies import DbSession
from meshcore_hub.common.models import EventObserver, Node, NodeTag
from meshcore_hub.common.schemas.messages import ObserverInfo


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
