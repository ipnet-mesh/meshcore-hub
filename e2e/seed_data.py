"""Deterministic seed data for the Playwright end-to-end test stack.

Runs inside the e2e collector container (which has the app and the Postgres
driver installed) against the throwaway e2e database:

    docker compose -f e2e/docker-compose.test.yml exec -T collector \
        python /seed_data.py

Idempotent: clears previously seeded rows and recreates them with fixed public
keys and recent timestamps, so every run yields the same dataset. The e2e
stack uses its own ephemeral Postgres instance - this never touches the local
development database.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from meshcore_hub.common.config import get_common_settings
from meshcore_hub.common.database import (
    create_database_engine,
    create_session_factory,
)
from meshcore_hub.common.models import (
    Advertisement,
    Channel,
    EventObserver,
    Message,
    Node,
    NodeTag,
    PacketPathHop,
    RawPacket,
    Route,
    RouteNode,
    RouteObserver,
    RouteRecentMatch,
    RouteResult,
    RouteResultHistory,
    UserProfile,
    UserProfileNode,
)

NOW = datetime.now(timezone.utc)

ALPHA = ("a1fa" + "0" * 64)[:64]
BRAVO = ("b2b0" + "0" * 64)[:64]
CHARLIE = ("c3c0" + "0" * 64)[:64]
DELTA = ("d4d0" + "0" * 64)[:64]
NORTH_1 = ("aa01" + "0" * 64)[:64]
NORTH_2 = ("aa02" + "0" * 64)[:64]
SOUTH_1 = ("bb01" + "0" * 64)[:64]
SOUTH_2 = ("bb02" + "0" * 64)[:64]

PATH_HOPS = [ALPHA[:4].upper(), BRAVO[:4].upper(), CHARLIE[:4].upper()]


def _hash(seed: str) -> str:
    return (seed + "0" * 32)[:32]


def _event_hash(counter: int) -> str:
    return f"{counter:032x}"


def _ago(minutes: float = 0.0, hours: float = 0.0, days: float = 0.0) -> datetime:
    return NOW - timedelta(minutes=minutes, hours=hours, days=days)


def clear(session: Session) -> None:
    for model in (
        RouteRecentMatch,
        RouteResultHistory,
        RouteResult,
        RouteObserver,
        RouteNode,
        Route,
        PacketPathHop,
        RawPacket,
        EventObserver,
        Advertisement,
        Message,
        UserProfileNode,
        UserProfile,
        NodeTag,
        Node,
        Channel,
    ):
        session.execute(delete(model))


def seed_nodes(session: Session) -> dict[str, Node]:
    content_specs = [
        (ALPHA, "Alpha Node", "chat", 51.5074, -0.1278),
        (BRAVO, "Bravo Node", "repeater", 52.4862, -1.8904),
        (CHARLIE, "Charlie Node", "room", 53.4808, -2.2426),
        (DELTA, "Delta Node", "chat", None, None),
    ]
    observer_specs = [
        (NORTH_1, "North Observer 1", "North", 51.6, -0.2),
        (NORTH_2, "North Observer 2", "North", 51.7, -0.3),
        (SOUTH_1, "South Observer 1", "South", 52.5, -1.9),
        (SOUTH_2, "South Observer 2", "South", 52.6, -2.0),
    ]

    nodes: dict[str, Node] = {}
    for i, (pk, name, adv_type, lat, lon) in enumerate(content_specs):
        node = Node(
            public_key=pk,
            name=name,
            adv_type=adv_type,
            lat=lat,
            lon=lon,
            first_seen=_ago(days=30),
            last_seen=_ago(minutes=i + 1),
        )
        session.add(node)
        nodes[pk] = node

    for i, (pk, name, _area, lat, lon) in enumerate(observer_specs):
        node = Node(
            public_key=pk,
            name=name,
            adv_type="repeater",
            lat=lat,
            lon=lon,
            is_observer=True,
            first_seen=_ago(days=30),
            last_seen=_ago(minutes=i + 1),
        )
        session.add(node)
        nodes[pk] = node

    session.flush()
    for pk, _name, area, _lat, _lon in observer_specs:
        session.add(NodeTag(node_id=nodes[pk].id, key="area", value=area))
    for pk in nodes:
        session.add(NodeTag(node_id=nodes[pk].id, key="name", value=nodes[pk].name))
    session.flush()
    return nodes


def seed_advertisements(
    session: Session, nodes: dict[str, Node]
) -> dict[str, tuple[str, float]]:
    specs = [
        (ALPHA, NORTH_1, "ad01", "flood", 30.0),
        (BRAVO, SOUTH_1, "ad02", "flood", 45.0),
        (CHARLIE, NORTH_2, "ad03", "direct", 60.0),
        (DELTA, SOUTH_2, "ad04", "transport_flood", 90.0),
        (ALPHA, SOUTH_1, "ad05", "flood", 120.0),
        (BRAVO, NORTH_1, "ad06", "flood", 150.0),
    ]
    events: dict[str, tuple[str, float]] = {}
    for i, (node_pk, observer_pk, seed, route_type, minutes) in enumerate(specs):
        packet_hash = _hash(seed)
        event_hash = _event_hash(i + 1)
        events[packet_hash] = (event_hash, minutes)
        node = nodes[node_pk]
        received_at = _ago(minutes=minutes)
        session.add(
            Advertisement(
                observer_node_id=nodes[observer_pk].id,
                node_id=node.id,
                public_key=node_pk,
                name=node.name,
                adv_type=node.adv_type,
                received_at=received_at,
                event_hash=event_hash,
                packet_hash=packet_hash,
                route_type=route_type,
                advert_timestamp=received_at,
            )
        )
        session.add(
            EventObserver(
                event_type="advertisement",
                event_hash=event_hash,
                observer_node_id=nodes[observer_pk].id,
                snr=7.5,
                path_len=2,
                observed_at=received_at,
            )
        )
    session.flush()
    return events


def seed_messages(
    session: Session, nodes: dict[str, Node], custom_channel_idx: int
) -> dict[str, tuple[str, float]]:
    specs = [
        ("channel", NORTH_1, "ce01", 10.0, "Hello from the e2e mesh", 17, None),
        ("channel", SOUTH_1, "ce02", 20.0, "Channel check from the south", 17, None),
        (
            "channel",
            NORTH_2,
            "ce03",
            25.0,
            "Ops channel traffic",
            custom_channel_idx,
            None,
        ),
        (
            "contact",
            SOUTH_2,
            "ce04",
            15.0,
            "Direct hello over the mesh",
            None,
            ALPHA[:12],
        ),
    ]
    events: dict[str, tuple[str, float]] = {}
    for i, (mtype, observer_pk, seed, minutes, text, channel_idx, prefix) in enumerate(
        specs
    ):
        packet_hash = _hash(seed)
        event_hash = _event_hash(100 + i)
        events[packet_hash] = (event_hash, minutes)
        received_at = _ago(minutes=minutes)
        session.add(
            Message(
                observer_node_id=nodes[observer_pk].id,
                message_type=mtype,
                pubkey_prefix=prefix,
                channel_idx=channel_idx,
                text=text,
                path_len=2,
                snr=6.5,
                received_at=received_at,
                event_hash=event_hash,
                packet_hash=packet_hash,
            )
        )
        session.add(
            EventObserver(
                event_type="message",
                event_hash=event_hash,
                observer_node_id=nodes[observer_pk].id,
                snr=6.5,
                path_len=2,
                observed_at=received_at,
            )
        )
    session.flush()
    return events


def seed_raw_packets(
    session: Session,
    nodes: dict[str, Node],
    advert_events: dict[str, tuple[str, float]],
    message_events: dict[str, tuple[str, float]],
    custom_channel_idx: int,
) -> str:
    channel_indices = {
        _hash("ce01"): 17,
        _hash("ce02"): 17,
        _hash("ce03"): custom_channel_idx,
    }
    events = {
        **{h: (e, m, "advertisement") for h, (e, m) in advert_events.items()},
        **{
            h: (e, m, "contact_msg_recv" if h == _hash("ce04") else "channel_msg_recv")
            for h, (e, m) in message_events.items()
        },
    }

    first_raw_packet_id = ""
    for packet_hash, (event_hash, minutes, event_type) in sorted(events.items()):
        for j, observer_pk in enumerate((NORTH_1, SOUTH_1)):
            received_at = _ago(minutes=minutes) + timedelta(seconds=j * 3)
            raw = RawPacket(
                observer_node_id=nodes[observer_pk].id,
                packet_hash=packet_hash,
                event_hash=event_hash,
                raw_hex=(packet_hash * 4)[:128],
                packet_type=5,
                payload_type=4 if event_type == "advertisement" else 5,
                event_type=event_type,
                channel_idx=channel_indices.get(packet_hash),
                source_pubkey_prefix=ALPHA[:12],
                route_type="flood",
                path_len=3,
                path_hash_bytes=2,
                snr=8.5 - j * 2.25,
                decoded={"e2e": True, "packet_hash": packet_hash},
                received_at=received_at,
            )
            session.add(raw)
            session.flush()
            if not first_raw_packet_id:
                first_raw_packet_id = raw.id
            for position, node_hash in enumerate(PATH_HOPS):
                session.add(
                    PacketPathHop(
                        raw_packet_id=raw.id,
                        position=position,
                        node_hash=node_hash,
                        packet_hash=packet_hash,
                        event_hash=event_hash,
                        received_at=received_at,
                        observer_node_id=nodes[observer_pk].id,
                    )
                )
    session.flush()
    return first_raw_packet_id


def seed_channels(session: Session) -> int:
    keys = [
        ("E2E General", "00112233445566778899aabbccddeeff" * 2),
        ("E2E Ops", "ffeeddccbbaa99887766554433221100" * 2),
    ]
    for name, key_hex in keys:
        session.add(
            Channel(
                name=name,
                key_hex=key_hex,
                channel_hash=Channel.compute_channel_hash(key_hex),
                visibility="community",
                enabled=True,
            )
        )
    session.flush()
    general_hash = Channel.compute_channel_hash(keys[0][1])
    return int(general_hash, 16)


def seed_routes(
    session: Session, nodes: dict[str, Node], first_raw_packet_id: str
) -> None:
    route = Route(
        from_label="Alpha Site",
        to_label="Bravo Site",
        description="Synthetic e2e route",
        visibility="community",
        match_width=2,
        window_hours=48,
        packet_count_threshold=3,
        clear_threshold=6,
        max_hop_span=8,
        enabled=True,
        reversible=True,
    )
    session.add(route)
    session.flush()

    for position, pk in enumerate((ALPHA, BRAVO)):
        session.add(
            RouteNode(
                route_id=route.id,
                node_id=nodes[pk].id,
                position=position,
                expected_hash=pk[:4].upper(),
            )
        )
    session.add(RouteObserver(route_id=route.id, node_id=nodes[NORTH_1].id))

    session.add(
        RouteResult(
            route_id=route.id,
            state="healthy",
            quality="clear",
            matched_count=7,
            threshold=3,
            effective_clear=6,
            evaluated_at=_ago(minutes=5),
            quality_avg="clear",
        )
    )

    history = [
        ("clear", 7),
        ("clear", 6),
        ("marginal", 4),
        ("clear", 5),
        ("marginal", 3),
        ("failing", 1),
        ("clear", 6),
    ]
    for day_offset, (quality, matched) in enumerate(history):
        session.add(
            RouteResultHistory(
                route_id=route.id,
                date=(NOW - timedelta(days=day_offset)).date(),
                quality=quality,
                state="unhealthy" if quality == "failing" else "healthy",
                matched_count=matched,
                evaluated_at=_ago(days=day_offset),
            )
        )

    if first_raw_packet_id:
        session.add(
            RouteRecentMatch(
                route_id=route.id,
                raw_packet_id=first_raw_packet_id,
                first_position=0,
                last_position=1,
            )
        )
    session.flush()

    # A second route owned by the e2e operator session (pw-operator).
    # Used by the "mine" filter test: operator-owned routes stay visible
    # when ?mine=true is active, while the legacy NULL-created_by route above
    # disappears.
    op_route = Route(
        from_label="Op North",
        to_label="Op South",
        description="Operator-owned e2e route",
        visibility="operator",
        match_width=1,
        window_hours=24,
        packet_count_threshold=3,
        clear_threshold=6,
        max_hop_span=8,
        enabled=True,
        reversible=False,
        created_by="pw-operator",
    )
    session.add(op_route)
    session.flush()
    for position, pk in enumerate((CHARLIE, DELTA)):
        session.add(
            RouteNode(
                route_id=op_route.id,
                node_id=nodes[pk].id,
                position=position,
                expected_hash=pk[:4].upper(),
            )
        )
    session.add(RouteObserver(route_id=op_route.id, node_id=nodes[NORTH_2].id))
    session.flush()


def seed_profiles(session: Session, nodes: dict[str, Node]) -> None:
    specs = [
        (
            "pw-admin",
            "PW Admin",
            "E2EADM",
            "admin,member",
            "Playwright admin user",
            "https://example.com/pw-admin",
        ),
        (
            "pw-member",
            "PW Member",
            "E2EMBR",
            "member",
            "Playwright member user",
            None,
        ),
        ("op-north", "Op North", "OPN1", "operator,member", "North operator", None),
        ("mem-south", "Mem South", "MEMS1", "member", "South member", None),
    ]
    profiles: dict[str, UserProfile] = {}
    for user_id, name, callsign, roles, description, url in specs:
        profile = UserProfile(
            user_id=user_id,
            name=name,
            callsign=callsign,
            roles=roles,
            description=description,
            url=url,
        )
        session.add(profile)
        profiles[user_id] = profile
    session.flush()

    session.add(
        UserProfileNode(
            user_profile_id=profiles["op-north"].id, node_id=nodes[ALPHA].id
        )
    )
    session.add(
        UserProfileNode(
            user_profile_id=profiles["mem-south"].id, node_id=nodes[BRAVO].id
        )
    )
    session.flush()


def main() -> None:
    settings = get_common_settings()
    engine = create_database_engine(
        settings.effective_database_url,
        schema=settings.effective_database_schema,
    )
    session_factory = create_session_factory(engine)

    last_error: OperationalError | None = None
    for _ in range(15):
        try:
            with session_factory() as session:
                clear(session)
                nodes = seed_nodes(session)
                custom_channel_idx = seed_channels(session)
                advert_events = seed_advertisements(session, nodes)
                message_events = seed_messages(session, nodes, custom_channel_idx)
                first_raw_packet_id = seed_raw_packets(
                    session, nodes, advert_events, message_events, custom_channel_idx
                )
                seed_routes(session, nodes, first_raw_packet_id)
                seed_profiles(session, nodes)
                session.commit()
            print("e2e seed data written")
            return
        except OperationalError as exc:
            last_error = exc
            time.sleep(2)
    raise RuntimeError(f"database not reachable after retries: {last_error}")


if __name__ == "__main__":
    main()
