"""Tests for the Trader API client."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web

from sectorem.auth.manager import AuthProvider
from sectorem.trader.client import TraderClient, Account
from sectorem.trader.constants import AssetType, OptionRight
from sectorem.trader.types import (
    CollectiveInvestmentPosition,
    EquityPosition,
    OptionPosition,
)


@pytest_asyncio.fixture
async def mock_auth():
    auth = AsyncMock(spec=AuthProvider)
    auth.get_access_token = AsyncMock(return_value="test-token")
    session = aiohttp.ClientSession()
    auth.get_authenticated_session.return_value = session
    yield auth
    await session.close()


class TestAccountNumberResolution:
    @pytest.mark.asyncio
    async def test_get_account_numbers(self, mock_auth, aiohttp_server):
        data = [{"accountNumber": "123", "hashValue": "abc"}]

        async def handler(request):
            return web.json_response(data)

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        result = await client.get_account_numbers()

        assert result == ["123"]

    @pytest.mark.asyncio
    async def test_get_account_hash_caches(self, mock_auth, aiohttp_server):
        call_count = 0

        async def handler(request):
            nonlocal call_count
            call_count += 1
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))

        assert await client.get_account_hash("123") == "abc"
        assert await client.get_account_hash("123") == "abc"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_get_account_hash_refreshes_on_miss(self, mock_auth, aiohttp_server):
        call_count = 0

        async def handler(request):
            nonlocal call_count
            call_count += 1
            accounts = [{"accountNumber": "123", "hashValue": "abc"}]
            if call_count >= 2:
                accounts.append({"accountNumber": "456", "hashValue": "def"})
            return web.json_response(accounts)

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))

        # First call caches 123
        assert await client.get_account_hash("123") == "abc"
        # 456 not cached yet — triggers refresh
        assert await client.get_account_hash("456") == "def"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_account_hash_raises_for_unknown(self, mock_auth, aiohttp_server):
        async def handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))

        with pytest.raises(ValueError, match="999"):
            await client.get_account_hash("999")


class TestTraderClient:
    @pytest.mark.asyncio
    async def test_get_account_returns_account(self, mock_auth, aiohttp_server):
        async def handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        account = await client.get_account("123")

        assert isinstance(account, Account)
        assert account.account_number == "123"

    @pytest.mark.asyncio
    async def test_get_accounts_returns_all(self, mock_auth, aiohttp_server):
        async def handler(request):
            return web.json_response([
                {"accountNumber": "123", "hashValue": "abc"},
                {"accountNumber": "456", "hashValue": "def"},
            ])

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        accounts = await client.get_accounts()

        assert len(accounts) == 2
        assert all(isinstance(a, Account) for a in accounts)
        assert accounts[0].account_number == "123"
        assert accounts[1].account_number == "456"

    @pytest.mark.asyncio
    async def test_get_user_preferences(self, mock_auth, aiohttp_server):
        data = {"streamerInfo": [{"schwabClientCustomerId": "cust1"}]}

        async def handler(request):
            assert request.path == "/trader/v1/userPreference"
            return web.json_response(data)

        app = web.Application()
        app.router.add_get("/trader/v1/userPreference", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        result = await client.get_user_preferences()

        assert result == data


class TestAccount:
    @pytest.mark.asyncio
    async def test_get_positions_equity(self, mock_auth, aiohttp_server):
        async def numbers_handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        async def account_handler(request):
            return web.json_response({
                "securitiesAccount": {
                    "positions": [{
                        "shortQuantity": 0.0,
                        "longQuantity": 100.0,
                        "averagePrice": 50.0,
                        "currentDayProfitLoss": 25.0,
                        "currentDayProfitLossPercentage": 0.5,
                        "taxLotAverageLongPrice": 50.0,
                        "longOpenProfitLoss": 500.0,
                        "marketValue": 5500.0,
                        "instrument": {
                            "assetType": "EQUITY",
                            "cusip": "123456789",
                            "symbol": "AAPL",
                            "netChange": 0.25,
                        },
                    }],
                },
            })

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", numbers_handler)
        app.router.add_get("/trader/v1/accounts/abc", account_handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        account = await client.get_account("123")
        positions = await account.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert isinstance(pos, EquityPosition)
        assert pos.instrument.symbol == "AAPL"
        assert pos.instrument.asset_type == AssetType.EQUITY
        assert pos.quantity == 100.0
        assert pos.average_price == 50.0
        assert pos.market_value == 5500.0
        assert pos.day_profit_loss == 25.0
        assert pos.open_profit_loss == 500.0

    @pytest.mark.asyncio
    async def test_get_positions_option(self, mock_auth, aiohttp_server):
        async def numbers_handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        async def account_handler(request):
            return web.json_response({
                "securitiesAccount": {
                    "positions": [{
                        "shortQuantity": 10.0,
                        "longQuantity": 0.0,
                        "averagePrice": 3.50,
                        "currentDayProfitLoss": -50.0,
                        "currentDayProfitLossPercentage": -1.5,
                        "taxLotAverageShortPrice": 3.50,
                        "shortOpenProfitLoss": 200.0,
                        "marketValue": -3000.0,
                        "instrument": {
                            "assetType": "OPTION",
                            "cusip": "0AAPL.XX",
                            "symbol": "AAPL  260619C00200000",
                            "description": "APPLE INC 06/19/2026 $200 Call",
                            "netChange": -0.50,
                            "type": "VANILLA",
                            "putCall": "CALL",
                            "underlyingSymbol": "AAPL",
                        },
                    }],
                },
            })

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", numbers_handler)
        app.router.add_get("/trader/v1/accounts/abc", account_handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        account = await client.get_account("123")
        positions = await account.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert isinstance(pos, OptionPosition)
        assert pos.instrument.symbol == "AAPL"
        assert pos.instrument.strike == 200.0
        assert pos.instrument.right == OptionRight.CALL
        assert pos.instrument.expiration == date(2026, 6, 19)
        assert pos.instrument.multiplier == 100
        assert pos.quantity == -10.0
        assert pos.average_price == 3.50
        assert pos.open_profit_loss == 200.0

    @pytest.mark.asyncio
    async def test_get_positions_collective_investment(self, mock_auth, aiohttp_server):
        async def numbers_handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        async def account_handler(request):
            return web.json_response({
                "securitiesAccount": {
                    "positions": [{
                        "shortQuantity": 0.0,
                        "longQuantity": 100.0,
                        "averagePrice": 30.0,
                        "currentDayProfitLoss": 10.0,
                        "currentDayProfitLossPercentage": 0.3,
                        "taxLotAverageLongPrice": 30.0,
                        "longOpenProfitLoss": -50.0,
                        "marketValue": 2950.0,
                        "instrument": {
                            "assetType": "COLLECTIVE_INVESTMENT",
                            "cusip": "123ABC",
                            "symbol": "SPYI",
                            "description": "NEOS S&P 500 HIGH INCOME ETF",
                            "type": "EXCHANGE_TRADED_FUND",
                        },
                    }],
                },
            })

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", numbers_handler)
        app.router.add_get("/trader/v1/accounts/abc", account_handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        account = await client.get_account("123")
        positions = await account.get_positions()

        assert len(positions) == 1
        pos = positions[0]
        assert isinstance(pos, CollectiveInvestmentPosition)
        assert pos.instrument.symbol == "SPYI"
        assert pos.quantity == 100.0

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, mock_auth, aiohttp_server):
        async def numbers_handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        async def account_handler(request):
            return web.json_response({"securitiesAccount": {}})

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", numbers_handler)
        app.router.add_get("/trader/v1/accounts/abc", account_handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        account = await client.get_account("123")
        positions = await account.get_positions()

        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_requests_fields(self, mock_auth, aiohttp_server):
        """Verify that get_positions passes fields=positions to the API."""
        received_params = {}

        async def numbers_handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        async def account_handler(request):
            received_params.update(request.query)
            return web.json_response({"securitiesAccount": {}})

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", numbers_handler)
        app.router.add_get("/trader/v1/accounts/abc", account_handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        account = await client.get_account("123")
        await account.get_positions()

        assert received_params["fields"] == "positions"
