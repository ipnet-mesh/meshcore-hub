# MeshCore Hub

Python 3.11+ project for managing and orchestrating MeshCore networks.

## Repo

Monorepo structure with the following packages:

- `meshcore_interface`: Component to interface with MeshCore companion nodes over Serial/USB and publish/subscribe to MQTT broker
- `meshcore_collector`: Component to collect and store MeshCore events from MQTT broker into a database
- `meshcore_api`: REST API to query collected data and send commands to the MeshCore network via MQTT broker
- `meshcore_web`: Frontend web dashboard for visualizing MeshCore network status and statistics
- `meshcore_common`: Shared utilities, models and configurations used by all components

Project configuration should use Pydantic for settings management, with all options available via environment variables for easy Docker deployment as well as command-line arguments.

Docker image contains all components, with entrypoint to select which component to run. Docker volumes for persistent storage of database.

MeshCore events and schemas are defined in [SCHEMAS.md](SCHEMAS.md) for reference.

## Dependencies

- Python 3.11+ (pyproject configured for 3.11)
  - All development in virtual environments (`.venv`)
  - Use `pip` for package management
  - Use `black` for code formatting
  - Use `flake8` for linting
  - Use `mypy` for type checking
  - Use `pytest` for testing
- Pre-commit hooks for code quality
- Click for CLI interfaces
- Pydantic for data validation and settings management
- SQLAlchemy for database interactions
- Alembic for database migrations
- FastAPI for REST API
- MQTT client library (e.g. `paho-mqtt` or `gmqtt`)
- meshcore_py for MeshCore device interactions
- Docker for containerization
  - Single Dockerfile for all components
  - Docker Compose for multi-container orchestration

## Testing

`meshcore_interface` should also include a mocked MeshCore device for testing purposes, allowing simulation of various events and conditions without requiring physical hardware. This should be enabled by a command-line flag or equivalent and will facilitate unit and integration testing without the need for actual MeshCore devices.

## Project Components

### Interface

This component interacts with a MeshCore companion node over Serial/USB. It should subscribe to all events provided by the [meshcore_py](https://github.com/meshcore-dev/meshcore_py) Python library. It should also support sending a selection of commands to the companion node, primarily sending messages to contacts or channels, and also sending node advertisments.

This component should run in one of two modes:

- RECEIVER: The component subscribes to all MeshCore events and then publishes them to an MQTT message broker
- SENDER: The component subscribes to an MQTT message broker and sends commands to the MeshCore companion node

The `meshcore_py` library provides a method of querying the connected MeshCore devices "public address" (64 character hex string) which uniquely identifies any MeshCore node on the network. The public key should be the primary identifier for the node in all communications.

Both sender and receiver modes should use a common MQTT topic structure including a customisable prefix, the nodes public address, and the event/command name. For example:

```
<prefix>/<public_address>/event/<event_name>
<prefix>/<public_address>/command/<command
```

The service can only be started in one mode at a time, either SENDER or RECEIVER. A typical MeshCore network might have several receiver nodes distributed around a location, all publishing events to a central MQTT broker, and then a single sender node which subscribes to the broker and sends commands to the network. There should only be one sender node in a network at any time to avoid message duplication.

### Collector

This service subscribes to the MQTT broker and stores all received events in a database for later retrieval. All relevant MeshCore events should be persisted including messages, node advertisments, trace data responses and include the node that provided them (public address in MQTT topic). The data should be persisted using SQLAlchemy to allow for flexibility in database backend (SQLite, Postgres, MySQL etc), but use SQLite as the default backend for simplicity. We should also support database migrations using Alembic from the outset.

Nodes should also be tracked in the database, with their latest known information (name, last seen timestamp etc) updated whenever a node advertisment is received. There should also be a Node Tag model to allow users to assign custom tags/labels to nodes for easier identification, using the public key as a foreign key. This will allow users to add arbitrary metadata to nodes without modifying the core node data.

### API

This service should provide a REST API (using FastAPI) to allow clients to retrieve stored data from the database used by the Collector. The API would need to have access to the same database as the Collector.

The API should support OpenAPI/Swagger documentation for easy exploration and testing. The API should also support optional HTTP bearer token authentication to restrict access to authorized users only. There should be two API keys, one that only allows query access, and another that allows full query and command access.

The API should support retrieving messages by various filters including sender, receiver, channel, date range etc. It should also support retrieving node advertisments and trace data. The API should also provide endpoints to manage Node Tags, allowing users to create, read, update and delete tags associated with nodes.

The API should also provide endpoints to send commands to the network, such as sending messages or advertisements. These commands would be published to the MQTT broker for the SENDER Interface component to pick up and execute. The API should support the same "prefix" configuration as the Interface component to ensure it publishes to the correct topics. The API would publish to a wildcard MQTT topic to allow for multiple sender nodes if required, e.g. `<prefix>/+/command/<command>`, but ideally there should only be one sender node active at any time.

The API should also provide a basic dashboard endpoint that provides summary statistics about the MeshCore network, such as number of nodes, number of messages sent/received, active channels etc. This would provide a quick overview of the network status without needing to query individual endpoints. This should use simple HTML templates served by FastAPI for easy access via web browsers. Styling should use simple CSS, no JavaScript required.

### Web Dashboard

This component provides a more user-friendly web interface for visualizing the MeshCore network status and statistics. It should connect to the API component to retrieve data and display it in an intuitive manner. The dashboard should include the following views:

- Front Page: Customisable welcome page with network name, details and radio configuration.
- Members List: List of all network member profiles (read from static JSON file)
- Network Overview: Summary statistics about the MeshCore network, including number of nodes, messages, advertisements etc.
- Node List: A list of all known nodes with their details and tags. Ability to filter and search nodes.
- Node Map: A visual map showing the locations of nodes based on latitude/longitude from node tags.
- Message Log: A log of all messages sent/received on the network with filtering options.

The following should be configurable via environment variables or command-line arguments:

- NETWORK_DOMAIN: Domain name for the web dashboard (e.g. "meshcore.example.com")
- NETWORK_NAME: Name of the MeshCore network
- NETWORK_CITY: Town/City where the network is located (e.g. "Ipswich")
- NETWORK_COUNTRY: Country where the network is located (ISO 3166-1 alpha-2 code)
- NETWORK_LOCATION: Latitude/Longitude of the network area location
- NETWORK_RADIO_CONFIG: Details about the radio configuration (frequency, power etc)
- NETWORK_CONTACT_EMAIL: Contact email address for network enquiries
- NETWORK_CONTACT_DISCORD: Discord server link for network community

The web dashboard should be a multi-page application using server-side rendering with FastAPI templates. It should use Tailwind CSS for styling and a modern UI component library (DaisyUI or similar) for consistent design. No JavaScript frameworks are required, any JS should be minimal and only for enhancing user experience (e.g. form validation, interactivity).
