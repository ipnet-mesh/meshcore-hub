"""Mock MeshCore device for testing without hardware."""

import logging
import random
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from meshcore_hub.interface.device import (
    BaseMeshCoreDevice,
    DeviceConfig,
    EventType,
)

logger = logging.getLogger(__name__)


@dataclass
class MockNodeConfig:
    """Configuration for a simulated node."""

    public_key: str
    name: str
    adv_type: str = "chat"
    flags: int = 218


@dataclass
class MockDeviceConfig:
    """Configuration for mock device behavior."""

    # Device identity
    public_key: Optional[str] = None
    name: str = "MockNode"

    # Simulated network nodes
    nodes: list[MockNodeConfig] = field(default_factory=list)

    # Event generation intervals (seconds)
    advertisement_interval: float = 30.0
    message_interval: float = 10.0
    telemetry_interval: float = 60.0

    # Simulation parameters
    enable_auto_events: bool = True
    message_delay_min: float = 0.1
    message_delay_max: float = 1.0
    error_rate: float = 0.0  # Probability of simulated errors


def generate_random_public_key() -> str:
    """Generate a random 64-character hex public key."""
    return secrets.token_hex(32)


class MockMeshCoreDevice(BaseMeshCoreDevice):
    """Mock MeshCore device for testing.

    Simulates a MeshCore device for unit and integration testing
    without requiring physical hardware.
    """

    def __init__(
        self,
        config: DeviceConfig,
        mock_config: Optional[MockDeviceConfig] = None,
    ):
        """Initialize mock device.

        Args:
            config: Device configuration (port/baud are ignored)
            mock_config: Mock-specific configuration
        """
        super().__init__(config)
        self.mock_config = mock_config or MockDeviceConfig()

        # Generate public key if not provided
        if self.mock_config.public_key:
            self._public_key = self.mock_config.public_key
        else:
            self._public_key = generate_random_public_key()

        # Initialize default simulated nodes if none provided
        if not self.mock_config.nodes:
            self.mock_config.nodes = self._create_default_nodes()

        self._running = False
        self._event_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        logger.info(f"Initialized mock device with public key: {self._public_key}")

    def _create_default_nodes(self) -> list[MockNodeConfig]:
        """Create default simulated network nodes."""
        return [
            MockNodeConfig(
                public_key=generate_random_public_key(),
                name="Alice",
                adv_type="chat",
            ),
            MockNodeConfig(
                public_key=generate_random_public_key(),
                name="Bob",
                adv_type="chat",
            ),
            MockNodeConfig(
                public_key=generate_random_public_key(),
                name="Repeater-01",
                adv_type="repeater",
                flags=128,
            ),
            MockNodeConfig(
                public_key=generate_random_public_key(),
                name="ChatRoom",
                adv_type="room",
            ),
        ]

    def connect(self) -> bool:
        """Connect to the mock device."""
        logger.info("Connecting to mock MeshCore device")
        self._connected = True

        # Simulate initial AppStart event
        self._dispatch_event(
            EventType.STATUS_RESPONSE,
            {
                "node_public_key": self._public_key,
                "status": "connected",
                "uptime": 0,
                "message_count": 0,
            },
        )

        logger.info(f"Mock device connected: {self._public_key}")
        return True

    def disconnect(self) -> None:
        """Disconnect from the mock device."""
        self._connected = False
        self.stop()
        logger.info("Mock device disconnected")

    def send_message(
        self,
        destination: str,
        text: str,
        timestamp: Optional[int] = None,
    ) -> bool:
        """Send a simulated direct message."""
        if not self._connected:
            logger.error("Cannot send message: not connected")
            return False

        if self._should_fail():
            logger.warning("Simulated send failure")
            return False

        logger.info(f"Mock: Sending message to {destination[:12]}...: {text[:20]}...")

        # Simulate send confirmation after delay
        delay = random.uniform(
            self.mock_config.message_delay_min,
            self.mock_config.message_delay_max,
        )

        def send_confirmation() -> None:
            time.sleep(delay)
            self._dispatch_event(
                EventType.SEND_CONFIRMED,
                {
                    "destination_public_key": (
                        destination
                        if len(destination) == 64
                        else destination + "0" * (64 - len(destination))
                    ),
                    "round_trip_ms": int(delay * 1000),
                },
            )

        threading.Thread(target=send_confirmation, daemon=True).start()
        return True

    def send_channel_message(
        self,
        channel_idx: int,
        text: str,
        timestamp: Optional[int] = None,
    ) -> bool:
        """Send a simulated channel message."""
        if not self._connected:
            logger.error("Cannot send channel message: not connected")
            return False

        if self._should_fail():
            logger.warning("Simulated send failure")
            return False

        logger.info(f"Mock: Sending message to channel {channel_idx}: {text[:20]}...")

        return True

    def send_advertisement(self, flood: bool = True) -> bool:
        """Send a simulated advertisement."""
        if not self._connected:
            logger.error("Cannot send advertisement: not connected")
            return False

        logger.info(f"Mock: Sending advertisement (flood={flood})")
        return True

    def request_status(self, target: Optional[str] = None) -> bool:
        """Request status from mock device."""
        if not self._connected:
            logger.error("Cannot request status: not connected")
            return False

        logger.info(f"Mock: Requesting status from {target or 'self'}")

        # Generate status response
        def send_status() -> None:
            time.sleep(0.2)
            self._dispatch_event(
                EventType.STATUS_RESPONSE,
                {
                    "node_public_key": target or self._public_key,
                    "status": "operational",
                    "uptime": random.randint(0, 86400),
                    "message_count": random.randint(0, 10000),
                },
            )

        threading.Thread(target=send_status, daemon=True).start()
        return True

    def request_telemetry(self, target: str) -> bool:
        """Request telemetry from mock device."""
        if not self._connected:
            logger.error("Cannot request telemetry: not connected")
            return False

        logger.info(f"Mock: Requesting telemetry from {target[:12]}...")

        # Generate telemetry response
        def send_telemetry() -> None:
            time.sleep(0.3)
            self._dispatch_event(
                EventType.TELEMETRY_RESPONSE,
                {
                    "node_public_key": target,
                    "parsed_data": {
                        "temperature": round(random.uniform(15.0, 35.0), 1),
                        "humidity": random.randint(30, 90),
                        "battery": round(random.uniform(3.2, 4.2), 2),
                        "pressure": round(random.uniform(980.0, 1040.0), 2),
                    },
                },
            )

        threading.Thread(target=send_telemetry, daemon=True).start()
        return True

    def set_time(self, timestamp: int) -> bool:
        """Set the mock device's hardware clock."""
        if not self._connected:
            logger.error("Cannot set time: not connected")
            return False

        logger.info(f"Mock: Set device time to {timestamp}")
        return True

    def set_name(self, name: str) -> bool:
        """Set the mock device's node name."""
        if not self._connected:
            logger.error("Cannot set name: not connected")
            return False

        logger.info(f"Mock: Set device name to '{name}'")
        # Update the mock config name
        self.mock_config.name = name
        return True

    def start_message_fetching(self) -> bool:
        """Start automatic message fetching (mock)."""
        if not self._connected:
            logger.error("Cannot start message fetching: not connected")
            return False

        logger.info("Mock: Started automatic message fetching")
        return True

    def get_contacts(self) -> bool:
        """Fetch contacts from mock device contact database.

        Note: This should only be called before the event loop is running.
        """
        if not self._connected:
            logger.error("Cannot get contacts: not connected")
            return False

        logger.info("Mock: Requesting contacts from device")

        # Generate CONTACTS event with all configured mock nodes
        def send_contacts() -> None:
            time.sleep(0.2)
            contacts = [
                {
                    "public_key": node.public_key,
                    "name": node.name,
                    "node_type": node.adv_type,
                }
                for node in self.mock_config.nodes
            ]
            self._dispatch_event(
                EventType.CONTACTS,
                {"contacts": contacts},
            )

        threading.Thread(target=send_contacts, daemon=True).start()
        return True

    def schedule_get_contacts(self) -> bool:
        """Schedule a get_contacts request.

        For the mock device, this is the same as get_contacts() since we
        don't have a real async event loop. The contacts are sent via a thread.
        """
        return self.get_contacts()

    def run(self) -> None:
        """Run the mock device event loop."""
        self._running = True
        logger.info("Starting mock device event loop")

        # Start auto event generation thread if enabled
        if self.mock_config.enable_auto_events:
            self._event_thread = threading.Thread(
                target=self._auto_event_generator,
                daemon=True,
            )
            self._event_thread.start()

        while self._running and self._connected:
            time.sleep(0.1)

        logger.info("Mock device event loop stopped")

    def stop(self) -> None:
        """Stop the mock device event loop."""
        self._running = False
        if self._event_thread and self._event_thread.is_alive():
            self._event_thread.join(timeout=1.0)
        logger.info("Mock device stopped")

    def _should_fail(self) -> bool:
        """Check if operation should fail based on error rate."""
        return random.random() < self.mock_config.error_rate

    def _auto_event_generator(self) -> None:
        """Generate automatic events for simulation."""
        last_adv = time.time()
        last_msg = time.time()
        last_telemetry = time.time()

        while self._running:
            now = time.time()

            # Generate advertisements
            if now - last_adv >= self.mock_config.advertisement_interval:
                self._generate_advertisement()
                last_adv = now

            # Generate messages
            if now - last_msg >= self.mock_config.message_interval:
                self._generate_message()
                last_msg = now

            # Generate telemetry
            if now - last_telemetry >= self.mock_config.telemetry_interval:
                self._generate_telemetry()
                last_telemetry = now

            time.sleep(1.0)

    def _generate_advertisement(self) -> None:
        """Generate a random advertisement event."""
        node = random.choice(self.mock_config.nodes)
        self._dispatch_event(
            EventType.ADVERTISEMENT,
            {
                "public_key": node.public_key,
                "name": node.name,
                "adv_type": node.adv_type,
                "flags": node.flags,
            },
        )
        logger.debug(f"Generated advertisement from {node.name}")

    def _generate_message(self) -> None:
        """Generate a random message event."""
        node = random.choice(self.mock_config.nodes)

        # Decide between contact and channel message
        if random.random() < 0.5:
            # Contact message
            sample_messages = [
                "Hello!",
                "How's the signal?",
                "Testing 1, 2, 3",
                "Great weather today!",
                "Anyone copy?",
                "Loud and clear!",
            ]
            self._dispatch_event(
                EventType.CONTACT_MSG_RECV,
                {
                    "pubkey_prefix": node.public_key[:12],
                    "text": random.choice(sample_messages),
                    "path_len": random.randint(1, 10),
                    "txt_type": 0,
                    "SNR": round(random.uniform(-5.0, 25.0), 1),
                    "sender_timestamp": int(time.time()),
                },
            )
            logger.debug(f"Generated contact message from {node.name}")
        else:
            # Channel message
            channel_messages = [
                "Hello everyone!",
                "Network check",
                "CQ CQ CQ",
                "Mesh is working great!",
                "Any repeaters online?",
            ]
            self._dispatch_event(
                EventType.CHANNEL_MSG_RECV,
                {
                    "channel_idx": random.choice([0, 1, 4, 7]),
                    "text": random.choice(channel_messages),
                    "path_len": random.randint(1, 15),
                    "txt_type": 0,
                    "SNR": round(random.uniform(-5.0, 25.0), 1),
                    "sender_timestamp": int(time.time()),
                },
            )
            logger.debug("Generated channel message")

    def _generate_telemetry(self) -> None:
        """Generate a random telemetry event."""
        node = random.choice(self.mock_config.nodes)
        self._dispatch_event(
            EventType.TELEMETRY_RESPONSE,
            {
                "node_public_key": node.public_key,
                "parsed_data": {
                    "temperature": round(random.uniform(15.0, 35.0), 1),
                    "humidity": random.randint(30, 90),
                    "battery": round(random.uniform(3.2, 4.2), 2),
                },
            },
        )
        logger.debug(f"Generated telemetry from {node.name}")

    def inject_event(self, event_type: EventType, payload: dict) -> None:
        """Inject a custom event for testing.

        Args:
            event_type: Event type
            payload: Event payload
        """
        self._dispatch_event(event_type, payload)
