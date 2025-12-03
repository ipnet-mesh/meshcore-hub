"""Fixtures for end-to-end tests.

These tests require Docker Compose services to be running.
They are disabled by default and can be run with:

    pytest -m e2e tests/e2e/

Or with the --e2e flag:

    pytest --e2e tests/e2e/
"""

import os
import time
from typing import Generator

import httpx
import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the e2e marker."""
    config.addinivalue_line(
        "markers",
        "e2e: mark test as end-to-end test requiring Docker services",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-mark all tests in this directory as e2e and skip if --e2e not provided."""
    # Check if e2e tests should run
    run_e2e = config.getoption("--e2e", default=False)

    skip_e2e = pytest.mark.skip(
        reason="E2E tests disabled by default. Use --e2e to run them."
    )

    for item in items:
        # Mark all tests in e2e directory
        if "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            if not run_e2e:
                item.add_marker(skip_e2e)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add --e2e option to pytest."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests (requires Docker services)",
    )


# E2E test configuration
E2E_API_URL = os.environ.get("E2E_API_URL", "http://localhost:18000")
E2E_WEB_URL = os.environ.get("E2E_WEB_URL", "http://localhost:18080")
E2E_MQTT_HOST = os.environ.get("E2E_MQTT_HOST", "localhost")
E2E_MQTT_PORT = int(os.environ.get("E2E_MQTT_PORT", "11883"))
E2E_READ_KEY = os.environ.get("E2E_READ_KEY", "test-read-key")
E2E_ADMIN_KEY = os.environ.get("E2E_ADMIN_KEY", "test-admin-key")


def wait_for_service(url: str, timeout: int = 60) -> bool:
    """Wait for a service to become available.

    Args:
        url: Health check URL
        timeout: Maximum seconds to wait

    Returns:
        True if service is available, False if timeout
    """
    start = time.time()
    while time.time() - start < timeout:
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code == 200:
                return True
        except httpx.RequestError:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="session")
def api_url() -> str:
    """Get API base URL."""
    return E2E_API_URL


@pytest.fixture(scope="session")
def web_url() -> str:
    """Get Web dashboard URL."""
    return E2E_WEB_URL


@pytest.fixture(scope="session")
def read_key() -> str:
    """Get read API key."""
    return E2E_READ_KEY


@pytest.fixture(scope="session")
def admin_key() -> str:
    """Get admin API key."""
    return E2E_ADMIN_KEY


@pytest.fixture(scope="session")
def api_client(api_url: str, read_key: str) -> Generator[httpx.Client, None, None]:
    """Create an API client with read access.

    This fixture waits for the API to be available before returning.
    """
    health_url = f"{api_url}/health"
    if not wait_for_service(health_url):
        pytest.skip(f"API not available at {api_url}")

    with httpx.Client(
        base_url=api_url,
        headers={"Authorization": f"Bearer {read_key}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def admin_client(api_url: str, admin_key: str) -> Generator[httpx.Client, None, None]:
    """Create an API client with admin access."""
    health_url = f"{api_url}/health"
    if not wait_for_service(health_url):
        pytest.skip(f"API not available at {api_url}")

    with httpx.Client(
        base_url=api_url,
        headers={"Authorization": f"Bearer {admin_key}"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def web_client(web_url: str) -> Generator[httpx.Client, None, None]:
    """Create a web dashboard client."""
    health_url = f"{web_url}/health"
    if not wait_for_service(health_url):
        pytest.skip(f"Web dashboard not available at {web_url}")

    with httpx.Client(
        base_url=web_url,
        timeout=30.0,
    ) as client:
        yield client
