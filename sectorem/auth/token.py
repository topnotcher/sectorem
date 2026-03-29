"""Token model and persistence."""

from __future__ import annotations

import abc
import dataclasses
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Token:
    """
    OAuth2 token pair.

    ``access_expires_at`` is the wall-clock time at which the access
    token becomes invalid (~30 minutes from issuance).

    ``refresh_issued_at`` is the time the current refresh token was
    first obtained.  Schwab refresh tokens expire 7 days after
    initial issuance and are **not** rotated on access-token refresh,
    so this timestamp anchors the re-authentication window.
    """

    access_token: str
    refresh_token: str
    token_type: str
    scope: str
    access_expires_at: datetime
    refresh_issued_at: datetime

    REFRESH_LIFETIME = timedelta(days=7)

    @property
    def access_expired(self) -> bool:
        """True if the access token has expired."""
        return datetime.now(timezone.utc) >= self.access_expires_at

    @property
    def refresh_expires_at(self) -> datetime:
        """Wall-clock time at which the refresh token expires."""
        return self.refresh_issued_at + self.REFRESH_LIFETIME

    @property
    def refresh_expired(self) -> bool:
        """True if the refresh token has expired."""
        return datetime.now(timezone.utc) >= self.refresh_expires_at

    @classmethod
    def from_response(
        cls,
        data: dict,
        refresh_issued_at: datetime | None = None,
    ) -> Token:
        """
        Build a Token from a Schwab token-endpoint response.

        :param data: Parsed JSON from the ``/v1/oauth/token`` endpoint.
        :param refresh_issued_at: Timestamp for the refresh token.
            Defaults to *now* (appropriate for initial authorization).
            Pass the previous value when refreshing an access token
            so the 7-day window is preserved.
        """
        now = datetime.now(timezone.utc)
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", ""),
            access_expires_at=now + timedelta(seconds=data["expires_in"]),
            refresh_issued_at=refresh_issued_at or now,
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for JSON storage)."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "scope": self.scope,
            "access_expires_at": self.access_expires_at.isoformat(),
            "refresh_issued_at": self.refresh_issued_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Token:
        """Deserialize from a dict produced by :meth:`to_dict`."""
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            token_type=data.get("token_type", "Bearer"),
            scope=data.get("scope", ""),
            access_expires_at=datetime.fromisoformat(data["access_expires_at"]),
            refresh_issued_at=datetime.fromisoformat(data["refresh_issued_at"]),
        )


class TokenStore(abc.ABC):
    """Persistence backend for OAuth tokens."""

    @abc.abstractmethod
    async def load(self) -> Token | None:
        """Load the stored token, or ``None`` if absent."""
        ...

    @abc.abstractmethod
    async def save(self, token: Token) -> None:
        """Persist a token, replacing any existing one."""
        ...


class FileTokenStore(TokenStore):
    """Store tokens as JSON on the local filesystem."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    async def load(self) -> Token | None:
        if not self._path.exists():
            return None
        data = json.loads(self._path.read_text(encoding="utf-8"))
        return Token.from_dict(data)

    async def save(self, token: Token) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(token.to_dict(), indent=2),
            encoding="utf-8",
        )
