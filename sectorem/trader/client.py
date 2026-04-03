"""Schwab Trader API client."""

from __future__ import annotations

from ..auth import AuthProvider
from ..rest import RestClient
from .constants import AccountType
from .types import Balance, InitialBalance, Position
from .parse import parse_balance, parse_initial_balance, parse_position


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
        self._preferences: dict | None = None

    async def _refresh_accounts(self) -> None:
        """Refresh the account number to hash mapping."""
        for acct in await self.get("accounts/accountNumbers"):
            self._accounts[acct["accountNumber"]] = acct["hashValue"]

    async def _get_account_preferences(self, account_number: str) -> dict:
        """Get the preferences dict for a single account."""
        if self._preferences is None:
            self._preferences = await self.get_user_preferences()

        for acct in self._preferences.get("accounts", []):
            if acct["accountNumber"] == account_number:
                return acct

        return {}

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

    async def get_accounts(self) -> list[Account]:
        """Get all linked accounts."""
        return [await self.get_account(acct) for acct in await self.get_account_numbers()]

    async def get_account(self, account: str) -> Account:
        """Get a single account by account number."""

        account_hash = await self.get_account_hash(account)
        prefs = await self._get_account_preferences(account)
        return Account(self, account, account_hash, prefs)

    async def get_user_preferences(self) -> dict:
        """
        Get user preferences.

        The response includes the streaming WebSocket URL needed
        to connect a streaming client.
        """
        return await self.get("userPreference")


class Account:
    """
    Account-specific client for the Schwab Trader API.

    This class should not be instantiated directly; use :meth:`~.TraderClient.get_account` instead.
    """

    def __init__(self, client: TraderClient, account_number: str, account_hash: str, prefs: dict) -> None:
        #: The account number.
        self.account_number: str = account_number
        #: Display name for the account (e.g. "Individual").
        self.nickname: str | None = prefs.get("nickName")
        #: Whether this is the primary account.
        self.is_primary: bool = prefs.get("primaryAccount", False)

        self._account_hash: str = account_hash
        self._client: TraderClient = client
        self._account_type: AccountType | None = None

    @property
    def is_margin(self) -> bool | None:
        """Whether this is a margin account. ``None`` if not yet fetched."""
        if self._account_type is None:
            return None
        return self._account_type == AccountType.MARGIN

    async def get_positions(self) -> list[Position]:
        """Get the current positions in this account."""
        info = await self._get_info('positions')
        positions = info.get('positions', [])

        return [parse_position(p) for p in positions]

    async def get_balances(self) -> Balance:
        """
        Get current balances for this account.

        Merges fields from ``currentBalances`` and ``projectedBalances``
        in the API response to produce a complete picture.
        """
        info = await self._get_info()
        account_type = self._update_account_type(info)
        return parse_balance(info["currentBalances"], info.get("projectedBalances", {}), account_type)

    async def get_initial_balances(self) -> InitialBalance:
        """Get start-of-day balances for this account."""
        info = await self._get_info()
        account_type = self._update_account_type(info)
        return parse_initial_balance(info["initialBalances"], account_type)

    def _update_account_type(self, info: dict) -> AccountType:
        """Extract and cache the account type from an API response."""
        account_type = AccountType(info["type"])
        self._account_type = account_type
        return account_type

    async def _get_info(self, info_type: str | None=None) -> dict:
        if info_type is not None:
            kwargs = {"params": {"fields": info_type}}
        else:
            kwargs = {}

        info = await self._client.get(f"accounts/{self._account_hash}", **kwargs)
        return info['securitiesAccount']
