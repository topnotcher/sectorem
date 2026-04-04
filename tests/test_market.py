"""Tests for the Market Data API client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web

from sectorem.auth.manager import AuthProvider
from sectorem.market import MarketDataClient


@pytest_asyncio.fixture
async def mock_auth():
    auth = AsyncMock(spec=AuthProvider)
    auth.get_access_token = AsyncMock(return_value="test-token")
    session = aiohttp.ClientSession()
    auth.get_authenticated_session.return_value = session
    yield auth
    await session.close()


class TestMarketDataClient:
    @pytest.mark.asyncio
    async def test_get_quotes(self, mock_auth, aiohttp_server):
        data = {
            "AAPL": {"quote": {"lastPrice": 150.0}},
            "MSFT": {"quote": {"lastPrice": 300.0}},
        }

        async def handler(request):
            assert request.query["symbols"] == "AAPL,MSFT"
            return web.json_response(data)

        app = web.Application()
        app.router.add_get("/marketdata/v1/quotes", handler)
        server = await aiohttp_server(app)

        client = MarketDataClient(mock_auth)
        client._base_url = str(server.make_url("/marketdata/v1"))
        result = await client.get_quotes(["AAPL", "MSFT"])

        assert result == data

    @pytest.mark.asyncio
    async def test_get_quotes_with_fields(self, mock_auth, aiohttp_server):
        received_params = {}

        async def handler(request):
            received_params.update(request.query)
            return web.json_response({})

        app = web.Application()
        app.router.add_get("/marketdata/v1/quotes", handler)
        server = await aiohttp_server(app)

        client = MarketDataClient(mock_auth)
        client._base_url = str(server.make_url("/marketdata/v1"))
        await client.get_quotes(["AAPL"], fields=["quote", "fundamental"])

        assert received_params["symbols"] == "AAPL"
        assert received_params["fields"] == "quote,fundamental"
