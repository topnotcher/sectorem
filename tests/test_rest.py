"""Tests for the base REST client."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import web

from sectorem.auth.manager import AuthProvider
from sectorem.errors import ApiError, CreatedResourceError, RateLimitError
from sectorem.rest import RestClient


@pytest_asyncio.fixture
async def mock_auth():
    auth = AsyncMock(spec=AuthProvider)
    auth.get_access_token = AsyncMock(return_value="test-token-123")
    return auth


class TestRequest:
    @pytest.mark.asyncio
    async def test_builds_url_from_base_and_path(self, mock_auth, aiohttp_server):
        received_path = None

        async def handler(request):
            nonlocal received_path
            received_path = request.path
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_get("/v1/accounts", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("/v1")))
        await client.get("accounts")

        assert received_path == "/v1/accounts"

    @pytest.mark.asyncio
    async def test_strips_trailing_slash_from_base(self, mock_auth, aiohttp_server):
        received_path = None

        async def handler(request):
            nonlocal received_path
            received_path = request.path
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_get("/v1/accounts", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("/v1/")))
        await client.get("/accounts")

        assert received_path == "/v1/accounts"

    @pytest.mark.asyncio
    async def test_passes_params(self, mock_auth, aiohttp_server):
        received_params = {}

        async def handler(request):
            received_params.update(request.query)
            return web.json_response({"ok": True})

        app = web.Application()
        app.router.add_get("/quotes", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        await client.get("quotes", params={"symbols": "AAPL,MSFT"})

        assert received_params["symbols"] == "AAPL,MSFT"

    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_non_json(self, mock_auth, aiohttp_server):
        async def handler(request):
            return web.Response(text="OK", content_type="text/plain")

        app = web.Application()
        app.router.add_post("/test", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        result = await client.post("test")

        assert result == {}


class TestFollowLocation:
    @pytest.mark.asyncio
    async def test_201_follows_absolute_location(self, mock_auth, aiohttp_server):
        async def create_handler(request):
            location = str(request.url.with_path("/v1/orders/123"))
            return web.Response(status=201, headers={"Location": location})

        async def get_handler(request):
            return web.json_response({"orderId": 123, "status": "WORKING"})

        app = web.Application()
        app.router.add_post("/v1/orders", create_handler)
        app.router.add_get("/v1/orders/123", get_handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("/v1")))
        result = await client.post("orders", json={"symbol": "AAPL"})

        assert result == {"orderId": 123, "status": "WORKING"}

    @pytest.mark.asyncio
    async def test_201_follows_root_relative_location(self, mock_auth, aiohttp_server):
        """A root-relative Location is resolved against the request URL."""
        async def create_handler(request):
            return web.Response(status=201, headers={"Location": "/v1/orders/123"})

        async def get_handler(request):
            return web.json_response({"orderId": 123})

        app = web.Application()
        app.router.add_post("/v1/orders", create_handler)
        app.router.add_get("/v1/orders/123", get_handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("/v1")))
        result = await client.post("orders", json={"symbol": "AAPL"})

        assert result == {"orderId": 123}

    @pytest.mark.asyncio
    async def test_201_without_location_falls_through(self, mock_auth, aiohttp_server):
        """A 201 with no Location is treated as a normal body response."""
        async def handler(request):
            return web.json_response({"ok": True}, status=201)

        app = web.Application()
        app.router.add_post("/orders", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        result = await client.post("orders")

        assert result == {"ok": True}


    @pytest.mark.asyncio
    async def test_201_retries_reading_the_created_resource(self, mock_auth, aiohttp_server):
        """A failed read of the new resource is retried; the creating request is sent once."""
        calls = {"post": 0, "get": 0}

        async def create_handler(request):
            calls["post"] += 1
            return web.Response(status=201, headers={"Location": "/v1/orders/123"})

        async def get_handler(request):
            calls["get"] += 1
            if calls["get"] < 3:
                return web.json_response({"message": "busy"}, status=503)
            return web.json_response({"orderId": 123})

        app = web.Application()
        app.router.add_post("/v1/orders", create_handler)
        app.router.add_get("/v1/orders/123", get_handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("/v1")))
        client.CREATED_FETCH_DELAY = 0
        result = await client.post("orders", json={"symbol": "AAPL"})

        assert result == {"orderId": 123}
        assert calls == {"post": 1, "get": 3}

    @pytest.mark.asyncio
    async def test_201_unreadable_resource_raises_with_its_location(self, mock_auth, aiohttp_server):
        calls = {"post": 0, "get": 0}

        async def create_handler(request):
            calls["post"] += 1
            return web.Response(status=201, headers={"Location": "/v1/orders/123"})

        async def get_handler(request):
            calls["get"] += 1
            return web.json_response({"message": "busy"}, status=503)

        app = web.Application()
        app.router.add_post("/v1/orders", create_handler)
        app.router.add_get("/v1/orders/123", get_handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("/v1")))
        client.CREATED_FETCH_DELAY = 0
        with pytest.raises(CreatedResourceError) as raised:
            await client.post("orders", json={"symbol": "AAPL"})

        assert raised.value.location == str(server.make_url("/v1/orders/123"))
        assert calls == {"post": 1, "get": RestClient.CREATED_FETCH_ATTEMPTS}


class TestErrorMapping:
    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self, mock_auth, aiohttp_server):
        async def handler(request):
            return web.Response(status=429, text="Too many requests")

        app = web.Application()
        app.router.add_get("/test", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        with pytest.raises(RateLimitError) as exc_info:
            await client.get("test")

        assert exc_info.value.status == 429
        assert "Too Many Requests" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_4xx_raises_api_error(self, mock_auth, aiohttp_server):
        async def handler(request):
            return web.Response(status=404, reason="Not Found", text='{"error": "not found"}')

        app = web.Application()
        app.router.add_get("/test", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        with pytest.raises(ApiError) as exc_info:
            await client.get("test")

        assert exc_info.value.status == 404
        assert "Not Found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_5xx_raises_api_error(self, mock_auth, aiohttp_server):
        async def handler(request):
            return web.Response(status=500, reason="Internal Server Error", text="oops")

        app = web.Application()
        app.router.add_get("/test", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        with pytest.raises(ApiError) as exc_info:
            await client.get("test")

        assert exc_info.value.status == 500


class TestHttpMethods:
    @pytest.mark.asyncio
    async def test_post(self, mock_auth, aiohttp_server):
        received = {}

        async def handler(request):
            received["method"] = request.method
            received["body"] = await request.json()
            return web.json_response({"created": True})

        app = web.Application()
        app.router.add_post("/orders", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        result = await client.post("orders", json={"symbol": "AAPL"})

        assert received["method"] == "POST"
        assert received["body"] == {"symbol": "AAPL"}
        assert result == {"created": True}

    @pytest.mark.asyncio
    async def test_put(self, mock_auth, aiohttp_server):
        received_method = None

        async def handler(request):
            nonlocal received_method
            received_method = request.method
            return web.json_response({"updated": True})

        app = web.Application()
        app.router.add_put("/orders/123", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        result = await client.put("orders/123", json={"qty": 10})

        assert received_method == "PUT"
        assert result == {"updated": True}

    @pytest.mark.asyncio
    async def test_delete(self, mock_auth, aiohttp_server):
        received_method = None

        async def handler(request):
            nonlocal received_method
            received_method = request.method
            return web.json_response({})

        app = web.Application()
        app.router.add_delete("/orders/123", handler)
        server = await aiohttp_server(app)

        client = RestClient(mock_auth, str(server.make_url("")))
        await client.delete("orders/123")

        assert received_method == "DELETE"
