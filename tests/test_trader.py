"""Tests for the Trader API client."""

from __future__ import annotations

from unittest.mock import AsyncMock, PropertyMock

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web

from sectorem.auth.manager import AuthProvider
from sectorem.trader import TraderClient


@pytest_asyncio.fixture
async def mock_auth():
    auth = AsyncMock(spec=AuthProvider)
    type(auth).access_token = PropertyMock(return_value="test-token")
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
    async def test_get_account_resolves_hash(self, mock_auth, aiohttp_server):
        account_data = {"securitiesAccount": {"accountNumber": "123"}}

        async def numbers_handler(request):
            return web.json_response([{"accountNumber": "123", "hashValue": "abc"}])

        async def account_handler(request):
            assert request.match_info["hash"] == "abc"
            return web.json_response(account_data)

        app = web.Application()
        app.router.add_get("/trader/v1/accounts/accountNumbers", numbers_handler)
        app.router.add_get("/trader/v1/accounts/{hash}", account_handler)
        server = await aiohttp_server(app)

        client = TraderClient(mock_auth)
        client._base_url = str(server.make_url("/trader/v1"))
        result = await client.get_account("123")

        assert result == account_data

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
