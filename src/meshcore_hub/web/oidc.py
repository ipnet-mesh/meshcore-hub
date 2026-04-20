"""Logto OIDC client for Authorization Code Flow."""

import logging
import secrets
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey

logger = logging.getLogger(__name__)


@dataclass
class OidcConfig:
    """Cached OIDC provider configuration from discovery document."""

    authorization_endpoint: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    end_session_endpoint: str = ""
    jwks_uri: str = ""
    issuer: str = ""
    _jwks: KeySet | None = field(default=None, repr=False)

    @property
    def ready(self) -> bool:
        return bool(self.authorization_endpoint and self.token_endpoint)


@dataclass
class OidcUser:
    """Authenticated user claims from OIDC."""

    sub: str
    name: str | None = None
    email: str | None = None
    picture: str | None = None
    username: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sub": self.sub,
            "name": self.name,
            "email": self.email,
            "picture": self.picture,
            "username": self.username,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OidcUser":
        return cls(
            sub=data["sub"],
            name=data.get("name"),
            email=data.get("email"),
            picture=data.get("picture"),
            username=data.get("username"),
        )


class LogtoOidcClient:
    """OIDC client for Logto using Authorization Code Flow."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        discovery_url: str,
        external_url: str,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._discovery_url = discovery_url.rstrip("/")
        self._external_url = external_url.rstrip("/")
        self._config = OidcConfig()

    @property
    def config(self) -> OidcConfig:
        return self._config

    @property
    def external_url(self) -> str:
        return self._external_url

    def _rewrite_url(self, internal_url: str) -> str:
        """Rewrite an internal Docker URL to use the external URL origin.

        Browser-facing endpoints (authorization, end_session) discovered from
        the internal Logto host need to be rewritten so the user's browser can
        reach them. Server-to-server endpoints (token, jwks) keep internal URLs.
        """
        if not self._external_url or not internal_url:
            return internal_url
        internal_origin = urlparse(self._discovery_url)
        external_origin = urlparse(self._external_url)
        if internal_origin.hostname != external_origin.hostname:
            parsed = urlparse(internal_url)
            rewritten = parsed._replace(
                scheme=external_origin.scheme,
                netloc=external_origin.netloc,
            )
            return rewritten.geturl()
        return internal_url

    async def discover(self) -> None:
        """Fetch the OIDC discovery document and populate config."""
        url = f"{self._discovery_url}/.well-known/openid-configuration"
        logger.info("Fetching OIDC discovery document from %s", url)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                doc = resp.json()

            self._config.authorization_endpoint = self._rewrite_url(
                doc["authorization_endpoint"]
            )
            self._config.token_endpoint = doc["token_endpoint"]
            self._config.end_session_endpoint = self._rewrite_url(
                doc.get("end_session_endpoint", "")
            )
            self._config.userinfo_endpoint = doc.get("userinfo_endpoint", "")
            self._config.jwks_uri = doc.get("jwks_uri", "")
            self._config.issuer = doc.get("issuer", "")

            if self._config.jwks_uri:
                await self._fetch_jwks()

            logger.info("OIDC discovery complete: issuer=%s", self._config.issuer)
        except Exception:
            logger.exception("Failed to fetch OIDC discovery document from %s", url)

    async def _fetch_jwks(self) -> None:
        """Fetch JWKS from the provider for ID token validation."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self._config.jwks_uri)
                resp.raise_for_status()
                jwks_data = resp.json()

            keys = []
            for key_data in jwks_data.get("keys", []):
                keys.append(RSAKey.import_key(key_data))
            self._config._jwks = KeySet(keys)
            logger.info("Loaded %d JWKS keys", len(keys))
        except Exception:
            logger.exception("Failed to fetch JWKS from %s", self._config.jwks_uri)

    def get_authorization_url(
        self,
        redirect_uri: str,
        state: str | None = None,
    ) -> tuple[str, str]:
        """Build the authorization URL for the login redirect.

        Returns:
            Tuple of (authorization_url, state).
        """
        if state is None:
            state = secrets.token_urlsafe(32)

        params = {
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
        }
        url = f"{self._config.authorization_endpoint}?{urlencode(params)}"
        return url, state

    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        """Exchange an authorization code for tokens.

        Returns:
            Token response dict with access_token, id_token, etc.
        """
        client = AsyncOAuth2Client(
            client_id=self._client_id,
            client_secret=self._client_secret,
            timeout=10.0,
        )
        token = await client.fetch_token(
            self._config.token_endpoint,
            code=code,
            redirect_uri=redirect_uri,
        )
        return dict(token)

    def validate_id_token(self, id_token_raw: str) -> dict[str, Any] | None:
        """Validate and decode an ID token using cached JWKS.

        Returns:
            Decoded claims dict, or None if validation fails.
        """
        if not self._config._jwks:
            logger.warning("No JWKS available, skipping ID token validation")
            return None

        try:
            decoded = jwt.decode(id_token_raw, self._config._jwks)
            return dict(decoded.claims)
        except Exception:
            logger.exception("ID token validation failed")
            return None

    async def fetch_userinfo(self, access_token: str) -> dict[str, Any] | None:
        """Fetch user info from the OIDC userinfo endpoint."""
        if not self._config.userinfo_endpoint:
            return None
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    self._config.userinfo_endpoint,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                return dict(resp.json())
        except Exception:
            logger.exception("Failed to fetch userinfo")
            return None

    def get_logout_url(
        self,
        id_token_hint: str | None = None,
        post_logout_redirect_uri: str | None = None,
    ) -> str:
        """Build the end-session (logout) URL."""
        if not self._config.end_session_endpoint:
            return post_logout_redirect_uri or "/"

        params: dict[str, str] = {}
        if id_token_hint:
            params["id_token_hint"] = id_token_hint
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri

        if params:
            return f"{self._config.end_session_endpoint}?{urlencode(params)}"
        return self._config.end_session_endpoint

    def build_redirect_uri(self, request_base_url: str) -> str:
        """Build the redirect URI from the request or configured value.

        Uses the request's base URL to derive the callback path.
        """
        base = request_base_url.rstrip("/")
        return f"{base}/auth/callback"

    def build_post_logout_uri(self, request_base_url: str) -> str:
        """Build the post-logout redirect URI from the request."""
        base = request_base_url.rstrip("/")
        return f"{base}/"
