"""Schwab Trader API client."""

from __future__ import annotations

from ..auth import Authenticator
from ..rest import RestClient

TRADER_BASE_URL = "https://api.schwabapi.com/trader/v1"


class TraderClient(RestClient):
    """
    Client for the Schwab Trader API.

    Provides access to accounts, orders, and user preferences.

    :param auth: Authenticator providing access tokens and session.
    """

    def __init__(self, auth: Authenticator) -> None:
        super().__init__(auth, TRADER_BASE_URL)

    async def get_account_numbers(self) -> list[dict]:
        """
        Get account number/hash mappings.

        The hashes are required for all other account-specific
        endpoints.
        """
        return await self._get("accounts/accountNumbers")

    async def get_accounts(self, *, fields: list[str] | None = None) -> list[dict]:
        """Get all linked accounts."""
        params = {}
        if fields is not None:
            params["fields"] = ",".join(fields)
        return await self._get("accounts", params=params)

    async def get_account(self, account_hash: str, *, fields: list[str] | None = None) -> dict:
        """Get a single account by hash."""
        params = {}
        if fields is not None:
            params["fields"] = ",".join(fields)
        return await self._get(f"accounts/{account_hash}", params=params)

    async def get_user_preferences(self) -> dict:
        """
        Get user preferences.

        The response includes the streaming WebSocket URL needed
        to connect the :class:`~sectorem.stream.StreamClient`.
        """
        return await self._get("userPreference")
