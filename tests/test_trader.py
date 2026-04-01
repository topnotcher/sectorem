"""Tests for the Trader API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, PropertyMock

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web

from sectorem.auth.manager import Authenticator
from sectorem.trader import TraderClient


@pytest_asyncio.fixture
async def mock_auth():
    auth = AsyncMock(spec=Authenticator)
    type(auth).access_token = PropertyMock(return_value="test-token")
    session = aiohttp.ClientSession()
    auth.get_authenticated_session.return_value = session
    yield auth
    await session.close()


class TestTraderClient:
    @pytest.mark.asyncio
    async def test_get_account_numbers(self, mock_auth, aiohttp_server):
        data = [{"accountNumber": "123", "hashValue": "abc"}]

        async def handler(request):
            assert request.path == "/trader/v1/accounts/accountNumbers"
            return web.json_response(data)

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        result = await client.get_account_numbers()

        assert result == data

    @pytest.mark.asyncio
    async def test_get_accounts(self, mock_auth, aiohttp_server):
        data = [{"securitiesAccount": {"accountNumber": "123"}}]

        async def handler(request):
            return web.json_response(data)

        app = web.Application()
        app.router.add_get("/trader/v1/accounts", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        result = await client.get_accounts()

        assert result == data

    @pytest.mark.asyncio
    async def test_get_accounts_with_fields(self, mock_auth, aiohttp_server):
        received_params = {}

        async def handler(request):
            received_params.update(request.query)
            return web.json_response([])

        app = web.Application()
        app.router.add_get("/trader/v1/accounts", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        await client.get_accounts(fields=["positions", "orders"])

        assert received_params["fields"] == "positions,orders"

    @pytest.mark.asyncio
    async def test_get_account(self, mock_auth, aiohttp_server):
        data = {"securitiesAccount": {"accountNumber": "123"}}

        async def handler(request):
            assert request.match_info["hash"] == "abc123"
            return web.json_response(data)

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/{hash}", handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        result = await client.get_account("abc123")

        assert result == data

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
