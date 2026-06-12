"""Tests for advertisement handler."""

from sqlalchemy import select

from meshcore_hub.common.models import Advertisement, EventObserver, Node
from meshcore_hub.collector.handlers.advertisement import handle_advertisement


class TestHandleAdvertisement:
    """Tests for handle_advertisement."""

    def test_creates_new_node(self, db_manager, db_session):
        """Test that new nodes are created."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "flags": 218,
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        # Check node was created
        node = db_session.execute(
            select(Node).where(Node.public_key == "a" * 64)
        ).scalar_one_or_none()

        assert node is not None
        assert node.name == "TestNode"
        assert node.adv_type == "chat"
        assert node.flags == 218

    def test_updates_existing_node(self, db_manager, db_session):
        """Test that existing nodes are updated."""
        # Create initial node
        node = Node(public_key="a" * 64, name="OldName", adv_type="repeater")
        db_session.add(node)
        db_session.commit()

        # Handle advertisement with new data
        payload = {
            "public_key": "a" * 64,
            "name": "NewName",
            "adv_type": "chat",
            "flags": 100,
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        # Refresh node
        db_session.refresh(node)

        assert node.name == "NewName"
        assert node.adv_type == "chat"
        assert node.flags == 100

    def test_creates_advertisement_record(self, db_manager, db_session):
        """Test that advertisement records are created."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        # Check advertisement was created
        ad = db_session.execute(select(Advertisement)).scalar_one_or_none()

        assert ad is not None
        assert ad.public_key == "a" * 64
        assert ad.name == "TestNode"

    def test_updates_node_location_fields(self, db_manager, db_session):
        """Advertisement payload lat/lon updates node coordinates."""
        payload = {
            "public_key": "a" * 64,
            "name": "LocNode",
            "adv_type": "repeater",
            "lat": 42.1234,
            "lon": -71.9876,
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        node = db_session.execute(
            select(Node).where(Node.public_key == "a" * 64)
        ).scalar_one_or_none()

        assert node is not None
        assert node.lat == 42.1234
        assert node.lon == -71.9876

    def test_handles_missing_public_key(self, db_manager, db_session):
        """Test that missing public_key is handled gracefully."""
        payload = {
            "name": "TestNode",
            "adv_type": "chat",
        }

        # Should not raise
        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        # No advertisement should be created
        ads = db_session.execute(select(Advertisement)).scalars().all()
        assert len(ads) == 0

    def test_duplicate_adds_observer(self, db_manager, db_session):
        """Duplicate advertisement adds receiver to observers instead of new record."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
        }

        receiver_pk = "c" * 64
        handle_advertisement(receiver_pk, "advertisement", payload, db_manager)

        ads = db_session.execute(select(Advertisement)).scalars().all()
        assert len(ads) == 1

        second_receiver_pk = "d" * 64
        handle_advertisement(second_receiver_pk, "advertisement", payload, db_manager)

        ads = db_session.execute(select(Advertisement)).scalars().all()
        assert len(ads) == 1

        observers = db_session.execute(select(EventObserver)).scalars().all()
        assert len(observers) == 2

    def test_duplicate_updates_node_location(self, db_manager, db_session):
        """Duplicate ad still updates advertised node lat/lon."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
        }
        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        payload_with_loc = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "lat": 10.0,
            "lon": 20.0,
        }
        handle_advertisement("b" * 64, "advertisement", payload_with_loc, db_manager)

        node = db_session.execute(
            select(Node).where(Node.public_key == "a" * 64)
        ).scalar_one()
        assert node.lat == 10.0
        assert node.lon == 20.0

    def test_location_from_nested_dict(self, db_manager, db_session):
        """Location extracted from nested location dict."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "location": {"latitude": 51.5, "longitude": -0.1},
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        node = db_session.execute(
            select(Node).where(Node.public_key == "a" * 64)
        ).scalar_one()
        assert node.lat == 51.5
        assert node.lon == -0.1

    def test_duplicate_same_receiver_skips_observer(self, db_manager, db_session):
        """Duplicate ad from same receiver does not add duplicate observer."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
        }

        receiver_pk = "c" * 64
        handle_advertisement(receiver_pk, "advertisement", payload, db_manager)
        handle_advertisement(receiver_pk, "advertisement", payload, db_manager)

        observers = db_session.execute(select(EventObserver)).scalars().all()
        assert len(observers) == 1

    def test_creates_receiver_node(self, db_manager, db_session):
        """Receiver node is created if it does not exist."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
        }

        receiver_pk = "e" * 64
        handle_advertisement(receiver_pk, "advertisement", payload, db_manager)

        receiver = db_session.execute(
            select(Node).where(Node.public_key == receiver_pk)
        ).scalar_one_or_none()
        assert receiver is not None

    def test_advertisement_stores_snr_and_path_len(self, db_manager, db_session):
        """Advertisement handler stores snr and path_len in event_observers."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "snr": 12.5,
            "path_len": 3,
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        observer = db_session.execute(select(EventObserver)).scalar_one_or_none()
        assert observer is not None
        assert observer.snr == 12.5
        assert observer.path_len == 3

    def test_stores_route_type(self, db_manager, db_session):
        """route_type is stored on the Advertisement record."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "route_type": "flood",
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        ad = db_session.execute(select(Advertisement)).scalar_one()
        assert ad.route_type == "flood"

    def test_stores_advert_timestamp(self, db_manager, db_session):
        """advert_timestamp is stored on the Advertisement record."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "advert_timestamp": 1747300000,
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        ad = db_session.execute(select(Advertisement)).scalar_one()
        assert ad.advert_timestamp is not None
        assert ad.advert_timestamp.year == 2025

    def test_advert_timestamp_invalid_falls_back_to_received_at(
        self, db_manager, db_session
    ):
        """Invalid advert_timestamp (far from received_at) still stored but not used for hash."""
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "advert_timestamp": 0,
        }

        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        ad = db_session.execute(select(Advertisement)).scalar_one()
        assert ad.advert_timestamp is not None
        assert ad.advert_timestamp.year == 1970

    def test_advert_timestamp_valid_used_for_dedup(self, db_manager, db_session):
        """Valid advert_timestamp produces same hash for different received_at times."""
        payload1 = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "advert_timestamp": 1747300000,
        }

        handle_advertisement("b" * 64, "advertisement", payload1, db_manager)

        ads = db_session.execute(select(Advertisement)).scalars().all()
        assert len(ads) == 1


class TestAdvertisementPacketHash:
    """packet_hash links an advertisement to its raw_packets rows."""

    def test_stores_packet_hash(self, db_manager, db_session):
        payload = {
            "public_key": "a" * 64,
            "name": "TestNode",
            "adv_type": "chat",
            "packet_hash": "FEEDFACE9999",
        }
        handle_advertisement("b" * 64, "advertisement", payload, db_manager)

        ad = db_session.execute(select(Advertisement)).scalar_one()
        assert ad.packet_hash == "FEEDFACE9999"
