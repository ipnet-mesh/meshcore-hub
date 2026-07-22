"""Mint a signed ``meshcore-session`` cookie for Playwright e2e tests.

Reproduces Starlette's SessionMiddleware signing scheme (an
``itsdangerous.TimestampSigner`` over the base64-encoded session JSON) so the
forged cookie is accepted by the web tier exactly like a real OIDC login -
populating ``window.__APP_CONFIG__`` (user + roles) and driving the API proxy's
``X-User-Id`` / ``X-User-Roles`` injection. No IdP round-trip is performed.

The secret must match the stack's ``OIDC_SESSION_SECRET``
(``test-session-secret`` in ``e2e/docker-compose.test.yml``).

Usage:
    python e2e/mint_session.py <secret> <sub> <name> <email> <roles_csv>

Prints the cookie value to stdout.
"""

from __future__ import annotations

import base64
import json
import sys

import itsdangerous


def mint(secret: str, sub: str, name: str, email: str, roles_csv: str) -> str:
    """Return a signed session-cookie value for the given identity/roles."""
    session = {
        "user": {
            "sub": sub,
            "name": name,
            "email": email,
            "picture": None,
            "roles": [r.strip() for r in roles_csv.split(",") if r.strip()],
        }
    }
    data = base64.b64encode(json.dumps(session).encode("utf-8"))
    signed = itsdangerous.TimestampSigner(secret).sign(data).decode("utf-8")
    return str(signed)


def main() -> None:
    if len(sys.argv) != 6:
        raise SystemExit(
            "usage: mint_session.py <secret> <sub> <name> <email> <roles_csv>"
        )
    secret, sub, name, email, roles_csv = sys.argv[1:6]
    print(mint(secret, sub, name, email, roles_csv))


if __name__ == "__main__":
    main()
