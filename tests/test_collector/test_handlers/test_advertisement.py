"""Tests for advertisement handler."""

import pytest
from sqlalchemy import select

from meshcore_hub.common.models import Advertisement, Node
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
