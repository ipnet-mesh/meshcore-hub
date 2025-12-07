"""FastAPI dependencies for the API."""

import logging
import uuid
from typing import Annotated, Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from meshcore_hub.common.database import DatabaseManager
from meshcore_hub.common.mqtt import MQTTClient, MQTTConfig

logger = logging.getLogger(__name__)


def get_db_manager(request: Request) -> DatabaseManager:
    """Get database manager from app.

    Args:
        request: FastAPI request

    Returns:
        DatabaseManager instance
    """
    from meshcore_hub.api.app import get_db_manager as _get_db_manager

    return _get_db_manager()


def get_db_session(
    db_manager: Annotated[DatabaseManager, Depends(get_db_manager)],
) -> Generator[Session, None, None]:
    """Get a database session.

    Args:
        db_manager: Database manager

    Yields:
        Database session
    """
    session = db_manager.get_session()
    try:
        yield session
    finally:
        session.close()


def get_mqtt_client(request: Request) -> MQTTClient:
    """Get an MQTT client for publishing commands.

    Args:
        request: FastAPI request

    Returns:
        MQTTClient instance
    """
    mqtt_host = getattr(request.app.state, "mqtt_host", "localhost")
    mqtt_port = getattr(request.app.state, "mqtt_port", 1883)
    mqtt_prefix = getattr(request.app.state, "mqtt_prefix", "meshcore")
    mqtt_tls = getattr(request.app.state, "mqtt_tls", False)

    # Use unique client ID to allow multiple API instances
    unique_id = uuid.uuid4().hex[:8]
    config = MQTTConfig(
        host=mqtt_host,
        port=mqtt_port,
        prefix=mqtt_prefix,
        client_id=f"meshcore-api-{unique_id}",
        tls=mqtt_tls,
    )

    client = MQTTClient(config)
    return client


# Dependency types for use in routes
DbSession = Annotated[Session, Depends(get_db_session)]
MqttClient = Annotated[MQTTClient, Depends(get_mqtt_client)]
