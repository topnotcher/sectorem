"""Schwab Trader API client."""

from __future__ import annotations

from ..auth import AuthProvider
from ..rest import RestClient

TRADER_BASE_URL = "https://api.schwabapi.com/trader/v1"


class TraderClient(RestClient):
    """
    Client for the Schwab Trader API.

    Provides access to accounts, orders, and user preferences.

    :param auth: Authenticator providing access tokens and session.
    """

    def __init__(self, auth: AuthProvider) -> None:
        super().__init__(auth, TRADER_BASE_URL)
        self._accounts: dict[str, str] = {}

    async def _refresh_accounts(self) -> None:
        """Refresh the account number to hash mapping."""
        for acct in await self._get("accounts/accountNumbers"):
            self._accounts[acct["accountNumber"]] = acct["hashValue"]

    async def get_account_hash(self, account_number: str) -> str:
        """
        Get the hash value for an account number.

        The hash value is required for most account-specific API calls. This method need not be used directly unless you
        are making your own custom API calls; the higher-level methods like :meth:`~TraderClient.get_account` handle the
        mapping.
        """
        for _ in range(2):
            hashed_account = self._accounts.get(account_number)

            if hashed_account is None:
                await self._refresh_accounts()
            else:
                return hashed_account

        raise ValueError(f"Account number {account_number} not found")

    async def get_account_numbers(self) -> list[str]:
        """Get all linked account numbers."""
        await self._refresh_accounts()
        return list(self._accounts.keys())

    async def get_accounts(self, *, fields: list[str] | None = None) -> list[dict]:
        """Get all linked accounts."""
        params = {}
        if fields is not None:
            params["fields"] = ",".join(fields)
        return await self._get("accounts", params=params)

    async def get_account(self, account: str, *, fields: list[str] | None = None) -> dict:
        """Get a single account by account number."""
        params = {}
        if fields is not None:
            params["fields"] = ",".join(fields)

        account_hash = await self.get_account_hash(account)
        return await self._get(f"accounts/{account_hash}", params=params)

    async def get_user_preferences(self) -> dict:
        """
        Get user preferences.

        The response includes the streaming WebSocket URL needed
        to connect the :class:`~sectorem.stream.StreamClient`.
        """
        return await self._get("userPreference")
