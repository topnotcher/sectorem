"""Tests for the SchwabClient container."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from sectorem.auth.manager import Authenticator
from sectorem.auth.token import TokenStore
from sectorem.client import SchwabClient
from sectorem.market import MarketDataClient
from sectorem.trader import TraderClient


@pytest.fixture
def mock_auth():
    auth = AsyncMock(spec=Authenticator)
    auth.start = AsyncMock()
    auth.stop = AsyncMock()
    auth.wait = AsyncMock()
    return auth


class TestConstruction:
    def test_from_auth(self, mock_auth):
        client = SchwabClient(auth=mock_auth)
        assert client.auth is mock_auth

    def test_from_app_key_secret(self):
        store = AsyncMock(spec=TokenStore)
        client = SchwabClient(app_key="key", app_secret="secret", token_store=store)
        assert client.auth is not None

    def test_rejects_both_auth_and_app_key(self, mock_auth):
        with pytest.raises(ValueError, match="not both"):
            SchwabClient(auth=mock_auth, app_key="key")

    def test_rejects_neither_auth_nor_app_key(self):
        with pytest.raises(ValueError, match="app_key"):
            SchwabClient()

    def test_requires_token_store_with_app_key(self):
        with pytest.raises(ValueError, match="token_store"):
            SchwabClient(app_key="key", app_secret="secret")

    def test_rejects_app_key_without_secret(self):
        with pytest.raises(ValueError, match="app_key"):
            SchwabClient(app_key="key")


class TestLazyProperties:
    def test_trader_created_lazily(self, mock_auth):
        client = SchwabClient(auth=mock_auth)
        assert client._trader is None
        trader = client.trader
        assert isinstance(trader, TraderClient)
        assert client.trader is trader

    def test_market_created_lazily(self, mock_auth):
        client = SchwabClient(auth=mock_auth)
        assert client._market is None
        market = client.market
        assert isinstance(market, MarketDataClient)
        assert client.market is market

    def test_clients_share_auth(self, mock_auth):
        client = SchwabClient(auth=mock_auth)
        assert client.trader._auth is client.market._auth


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_starts_auth_and_waits(self, mock_auth):
        client = SchwabClient(auth=mock_auth)
        await client.start()
        mock_auth.start.assert_awaited_once()
        mock_auth.wait.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, mock_auth):
        client = SchwabClient(auth=mock_auth)
        _ = client.trader
        _ = client.market

        await client.stop()

        assert client._trader is None
        assert client._market is None
        mock_auth.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_auth):
        async with SchwabClient(auth=mock_auth) as client:
            assert isinstance(client, SchwabClient)
            mock_auth.start.assert_awaited_once()

        mock_auth.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_without_clients(self, mock_auth):
        """stop() works even if no clients were ever created."""
        client = SchwabClient(auth=mock_auth)
        await client.stop()
        mock_auth.stop.assert_awaited_once()
