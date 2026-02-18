"""API test fixtures."""

import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from meshcore_hub.api.app import create_app
from meshcore_hub.api.dependencies import (
    get_db_session,
    get_mqtt_client,
    get_db_manager,
)
from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.models import (
    Advertisement,
    Base,
    Member,
    Message,
    Node,
    NodeTag,
    Telemetry,
    TracePath,
)


@pytest.fixture
def test_db_path():
    """Create a temporary database file path."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def api_db_engine(test_db_path):
    """Create a SQLite database engine for API testing."""
    db_url = f"sqlite:///{test_db_path}"
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def api_db_session(api_db_engine):
    """Create a database session for API testing."""
    Session = sessionmaker(bind=api_db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_mqtt():
    """Create a mock MQTT client."""
    mock = MagicMock()
    mock.connect.return_value = None
    mock.start_background.return_value = None
    mock.stop.return_value = None
    mock.disconnect.return_value = None
    mock.publish_command.return_value = None
    return mock


@pytest.fixture
def mock_db_manager(api_db_engine):
    """Create a mock database manager using the test engine."""
    manager = MagicMock(spec=DatabaseManager)
    Session = sessionmaker(bind=api_db_engine)
    manager.get_session = lambda: Session()

    @contextmanager
    def _session_scope():
        session = Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    manager.session_scope = _session_scope
    return manager


@pytest.fixture
def app_no_auth(test_db_path, api_db_engine, mock_mqtt, mock_db_manager):
    """Create a FastAPI app with no authentication required."""
    db_url = f"sqlite:///{test_db_path}"

    # Patch the global db_manager to avoid lifespan issues
    with patch("meshcore_hub.api.app._db_manager", mock_db_manager):
        app = create_app(
            database_url=db_url,
            read_key=None,
            admin_key=None,
        )

        # Create session maker for this test engine
        Session = sessionmaker(bind=api_db_engine)

        def override_get_db_manager(request=None):
            return mock_db_manager

        def override_get_db_session():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        def override_get_mqtt_client(request=None):
            return mock_mqtt

        app.dependency_overrides[get_db_manager] = override_get_db_manager
        app.dependency_overrides[get_db_session] = override_get_db_session
        app.dependency_overrides[get_mqtt_client] = override_get_mqtt_client

        yield app


@pytest.fixture
def app_with_auth(test_db_path, api_db_engine, mock_mqtt, mock_db_manager):
    """Create a FastAPI app with authentication enabled."""
    db_url = f"sqlite:///{test_db_path}"

    with patch("meshcore_hub.api.app._db_manager", mock_db_manager):
        app = create_app(
            database_url=db_url,
            read_key="test-read-key",
            admin_key="test-admin-key",
        )

        Session = sessionmaker(bind=api_db_engine)

        def override_get_db_manager(request=None):
            return mock_db_manager

        def override_get_db_session():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        def override_get_mqtt_client(request=None):
            return mock_mqtt

        app.dependency_overrides[get_db_manager] = override_get_db_manager
        app.dependency_overrides[get_db_session] = override_get_db_session
        app.dependency_overrides[get_mqtt_client] = override_get_mqtt_client

        yield app


@pytest.fixture
def client_no_auth(app_no_auth, mock_db_manager):
    """Create a test client with no authentication.

    Uses raise_server_exceptions=False to skip lifespan events.
    """
    # Don't use context manager to skip lifespan
    client = TestClient(app_no_auth, raise_server_exceptions=True)
    yield client


@pytest.fixture
def client_with_auth(app_with_auth, mock_db_manager):
    """Create a test client with authentication enabled.

    Uses raise_server_exceptions=False to skip lifespan events.
    """
    client = TestClient(app_with_auth, raise_server_exceptions=True)
    yield client


@pytest.fixture
def sample_node(api_db_session):
    """Create a sample node in the database."""
    node = Node(
        public_key="abc123def456abc123def456abc123de",
        name="Test Node",
        adv_type="REPEATER",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    api_db_session.add(node)
    api_db_session.commit()
    api_db_session.refresh(node)
    return node


@pytest.fixture
def sample_node_tag(api_db_session, sample_node):
    """Create a sample node tag in the database."""
    tag = NodeTag(
        node_id=sample_node.id,
        key="environment",
        value="production",
    )
    api_db_session.add(tag)
    api_db_session.commit()
    api_db_session.refresh(tag)
    return tag


@pytest.fixture
def sample_message(api_db_session):
    """Create a sample message in the database."""
    message = Message(
        message_type="direct",
        pubkey_prefix="abc123",
        text="Hello World",
        received_at=datetime.now(timezone.utc),
    )
    api_db_session.add(message)
    api_db_session.commit()
    api_db_session.refresh(message)
    return message


@pytest.fixture
def sample_advertisement(api_db_session):
    """Create a sample advertisement in the database."""
    advert = Advertisement(
        public_key="abc123def456abc123def456abc123de",
        name="TestNode",
        adv_type="REPEATER",
        received_at=datetime.now(timezone.utc),
    )
    api_db_session.add(advert)
    api_db_session.commit()
    api_db_session.refresh(advert)
    return advert


@pytest.fixture
def sample_telemetry(api_db_session):
    """Create a sample telemetry record in the database."""
    telemetry = Telemetry(
        node_public_key="abc123def456abc123def456abc123de",
        parsed_data={
            "battery_level": 85.5,
            "temperature": 25.3,
        },
        received_at=datetime.now(timezone.utc),
    )
    api_db_session.add(telemetry)
    api_db_session.commit()
    api_db_session.refresh(telemetry)
    return telemetry


@pytest.fixture
def sample_trace_path(api_db_session):
    """Create a sample trace path in the database."""
    trace = TracePath(
        initiator_tag=12345,
        path_hashes=["abc123", "def456", "ghi789"],
        hop_count=3,
        received_at=datetime.now(timezone.utc),
    )
    api_db_session.add(trace)
    api_db_session.commit()
    api_db_session.refresh(trace)
    return trace


@pytest.fixture
def sample_member(api_db_session):
    """Create a sample member in the database."""
    member = Member(
        member_id="alice",
        name="Alice Smith",
        callsign="W1ABC",
        role="Admin",
        description="Network administrator",
        contact="alice@example.com",
    )
    api_db_session.add(member)
    api_db_session.commit()
    api_db_session.refresh(member)
    return member


@pytest.fixture
def receiver_node(api_db_session):
    """Create a receiver node in the database."""
    node = Node(
        public_key="receiver123receiver123receiver12",
        name="Receiver Node",
        adv_type="REPEATER",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
    )
    api_db_session.add(node)
    api_db_session.commit()
    api_db_session.refresh(node)
    return node


@pytest.fixture
def sample_message_with_receiver(api_db_session, receiver_node):
    """Create a message with a receiver node."""
    message = Message(
        message_type="channel",
        channel_idx=1,
        pubkey_prefix="xyz789",
        text="Channel message with receiver",
        received_at=datetime.now(timezone.utc),
        receiver_node_id=receiver_node.id,
    )
    api_db_session.add(message)
    api_db_session.commit()
    api_db_session.refresh(message)
    return message


@pytest.fixture
def sample_advertisement_with_receiver(api_db_session, sample_node, receiver_node):
    """Create an advertisement with source and receiver nodes."""
    advert = Advertisement(
        public_key=sample_node.public_key,
        name="SourceNode",
        adv_type="REPEATER",
        received_at=datetime.now(timezone.utc),
        node_id=sample_node.id,
        receiver_node_id=receiver_node.id,
    )
    api_db_session.add(advert)
    api_db_session.commit()
    api_db_session.refresh(advert)
    return advert


@pytest.fixture
def sample_telemetry_with_receiver(api_db_session, receiver_node):
    """Create a telemetry record with a receiver node."""
    telemetry = Telemetry(
        node_public_key="xyz789xyz789xyz789xyz789xyz789xy",
        parsed_data={"battery_level": 50.0},
        received_at=datetime.now(timezone.utc),
        receiver_node_id=receiver_node.id,
    )
    api_db_session.add(telemetry)
    api_db_session.commit()
    api_db_session.refresh(telemetry)
    return telemetry


@pytest.fixture
def sample_trace_path_with_receiver(api_db_session, receiver_node):
    """Create a trace path with a receiver node."""
    trace = TracePath(
        initiator_tag=99999,
        path_hashes=["aaa111", "bbb222"],
        hop_count=2,
        received_at=datetime.now(timezone.utc),
        receiver_node_id=receiver_node.id,
    )
    api_db_session.add(trace)
    api_db_session.commit()
    api_db_session.refresh(trace)
    return trace


@pytest.fixture
def sample_node_with_name_tag(api_db_session):
    """Create a node with a name tag for search testing."""
    node = Node(
        public_key="searchable123searchable123searc",
        name="Original Name",
        adv_type="CLIENT",
        first_seen=datetime.now(timezone.utc),
    )
    api_db_session.add(node)
    api_db_session.commit()

    tag = NodeTag(
        node_id=node.id,
        key="name",
        value="Friendly Search Name",
    )
    api_db_session.add(tag)
    api_db_session.commit()
    api_db_session.refresh(node)
    return node


@pytest.fixture
def sample_node_with_member_tag(api_db_session):
    """Create a node with a member_id tag for filter testing."""
    node = Node(
        public_key="member123member123member123membe",
        name="Member Node",
        adv_type="CHAT",
        first_seen=datetime.now(timezone.utc),
    )
    api_db_session.add(node)
    api_db_session.commit()

    tag = NodeTag(
        node_id=node.id,
        key="member_id",
        value="alice",
    )
    api_db_session.add(tag)
    api_db_session.commit()
    api_db_session.refresh(node)
    return node
