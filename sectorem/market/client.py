"""Schwab Market Data API client."""

from __future__ import annotations

from ..auth import AuthProvider
from ..rest import RestClient

MARKET_DATA_BASE_URL = "https://api.schwabapi.com/marketdata/v1"


class MarketDataClient(RestClient):
    """
    Client for the Schwab Market Data API.

    Provides access to quotes, option chains, and price history.

    :param auth: Authenticator providing access tokens and session.
    """

    def __init__(self, auth: AuthProvider) -> None:
        super().__init__(auth, MARKET_DATA_BASE_URL)

    async def get_quotes(self, symbols: list[str], *, fields: list[str] | None = None) -> dict:
        """
        Get real-time quotes for one or more symbols.

        :param symbols: Ticker symbols to quote.
        :param fields: Optional subset of fields to return.
        """
        params: dict = {"symbols": ",".join(symbols)}
        if fields is not None:
            params["fields"] = ",".join(fields)
        return await self.get("quotes", params=params)
