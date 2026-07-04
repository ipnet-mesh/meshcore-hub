# Remote Observers

Other operators can run their own [meshcore-packet-capture](https://github.com/agessaman/meshcore-packet-capture) instance and publish decoded packets to your MeshCore Hub. They can also optionally contribute to the LetsMesh and MeshRank networks.

This document covers the local packet-capture observer (the `observer` compose profile) and the remote-observer contribution flow. The `PACKETCAPTURE_*` and `SERIAL_PORT` variables that configure the external capture image are documented at the bottom of this page; for everything else see [configuration.md](configuration.md).

> **Prerequisite:** Your MQTT broker must be accessible to remote observers. In production, this means exposing the WebSocket listener via a reverse proxy with TLS (e.g., `wss://mqtt.example.com/mqtt`).

> **Restricting which observers are accepted:** because anyone with broker access can publish as an observer, Hub operators can gate ingestion by observer public key using `OBSERVER_ALLOWLIST` / `OBSERVER_DENYLIST`. See [configuration.md → Observer Ingestion Filters](configuration.md#observer-ingestion-filters).

## Example: Contribute to MeshCore Hub, MeshRank and other services

A ready-made Docker Compose setup is provided in `contrib/packetcapture/`. Download it and configure:

```bash
mkdir meshcore-observer && cd meshcore-observer

wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/contrib/packetcapture/docker-compose.yml
wget https://raw.githubusercontent.com/ipnet-mesh/meshcore-hub/main/contrib/packetcapture/.env.example

cp .env.example .env
```

Edit `.env` and update the following variables:

| Variable               | Description                                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `SERIAL_PORT`          | Device path for your MeshCore companion device (e.g. `/dev/ttyUSB0`, or `/dev/serial/by-id/...` for a stable path) |
| `IATA`                 | 3-letter area code for your location (e.g. `STN`, `SEA`)                                                           |
| `ORIGIN`               | Observer identifier (default: `observer`)                                                                          |
| `IPNET_ENABLE`         | Set `true` to contribute packets to IPNet MeshCore Hub (default: `true`)                                           |
| `MESHRANK_ENABLE`      | Set `true` to contribute to MeshRank (default: `false`)                                                            |
| `MESHRANK_UPLINK_KEY`  | Your MeshRank uplink key (required if MeshRank enabled)                                                            |
| `CUSTOM_ENABLE`        | Set `true` to publish to a custom MQTT broker (default: `false`)                                                   |
| `CUSTOM_MQTT_SERVER`   | Custom MQTT broker hostname                                                                                        |
| `CUSTOM_MQTT_PORT`     | Custom MQTT broker port (default: `8883`)                                                                          |
| `CUSTOM_MQTT_USE_TLS`  | `true` for TLS, `false` for plain (default: `true`)                                                                |
| `CUSTOM_MQTT_USERNAME` | Username for custom broker auth                                                                                    |
| `CUSTOM_MQTT_PASSWORD` | Password for custom broker auth                                                                                    |

Then start the observer:

```bash
docker compose up -d
```

> **Local network (no TLS):** Set `CUSTOM_MQTT_SERVER` to the Hub's LAN IP (e.g. `192.168.1.100`), `CUSTOM_MQTT_PORT=1883`, and `CUSTOM_MQTT_USE_TLS=false`.

## Packet Capture Settings

The variables below configure the external **meshcore-packet-capture** image (`ghcr.io/agessaman/meshcore-packet-capture`), which is run by the `observer` compose profile. They are _not_ consumed by MeshCore Hub itself — they are listed here because they live in the same `.env` and are needed by operators running an observer. See the [meshcore-packet-capture documentation](https://github.com/agessaman/meshcore-packet-capture) for full details.

### Device

| Variable                      | Default         | Description                                                                                             |
| ----------------------------- | --------------- | ------------------------------------------------------------------------------------------------------- |
| `SERIAL_PORT`                 | `/dev/ttyUSB0`  | Serial port for the packet-capture device (typically `/dev/ttyUSB[0-9]` or `/dev/ttyACM[0-9]` on Linux) |
| `PACKETCAPTURE_IATA`          | `LOC`           | 3-letter IATA airport/area code used in topic templates                                                 |
| `PACKETCAPTURE_ORIGIN`        | _(device name)_ | Observer display name (defaults to the device name from the MeshCore connection)                        |
| `PACKETCAPTURE_IMAGE_VERSION` | `latest`        | Docker image tag for the packet-capture image                                                           |

### Connection behaviour

| Variable                               | Default | Description                                                   |
| -------------------------------------- | ------- | ------------------------------------------------------------- |
| `PACKETCAPTURE_TIMEOUT`                | `30`    | Connection timeout in seconds                                 |
| `PACKETCAPTURE_MAX_CONNECTION_RETRIES` | `5`     | Max device-connection retries                                 |
| `PACKETCAPTURE_CONNECTION_RETRY_DELAY` | `5`     | Seconds between device-connection retries                     |
| `PACKETCAPTURE_HEALTH_CHECK_INTERVAL`  | `30`    | Seconds between health checks                                 |
| `PACKETCAPTURE_ADVERT_INTERVAL_HOURS`  | `11`    | Send flood adverts at this interval in hours (`0` = disabled) |
| `PACKETCAPTURE_RF_DATA_TIMEOUT`        | `15.0`  | RF data cache timeout in seconds                              |

### MQTT reconnection

| Variable                               | Default | Description                                   |
| -------------------------------------- | ------- | --------------------------------------------- |
| `PACKETCAPTURE_MAX_MQTT_RETRIES`       | `5`     | Max MQTT reconnection attempts                |
| `PACKETCAPTURE_MQTT_RETRY_DELAY`       | `5`     | Seconds between MQTT reconnection attempts    |
| `PACKETCAPTURE_EXIT_ON_RECONNECT_FAIL` | `true`  | Exit the process when MQTT reconnection fails |
