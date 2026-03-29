"""Tests for the OAuth callback server."""

import asyncio

import aiohttp
import pytest

from sectorem.auth.server import AiohttpCallbackServer, localhost_server


async def _noop(params):
    pass


class TestAiohttpCallbackServer:
    @pytest.mark.asyncio
    async def test_url_format(self):
        server = AiohttpCallbackServer(_noop, "127.0.0.1", 9876, "/cb")
        assert server.url == "http://127.0.0.1:9876/cb"

    @pytest.mark.asyncio
    async def test_url_omits_port_80_for_http(self):
        server = AiohttpCallbackServer(_noop, port=80, url_host="example.com")
        assert server.url == "http://example.com/callback"

    @pytest.mark.asyncio
    async def test_url_omits_port_443_for_https(self):
        server = AiohttpCallbackServer(_noop, port=443, url_host="example.com", scheme="https")
        assert server.url == "https://example.com/callback"

    @pytest.mark.asyncio
    async def test_url_includes_non_default_port(self):
        server = AiohttpCallbackServer(_noop, port=8443, url_host="example.com", scheme="https")
        assert server.url == "https://example.com:8443/callback"

    @pytest.mark.asyncio
    async def test_url_host_overrides_bind_host(self):
        server = AiohttpCallbackServer(_noop, host="0.0.0.0", port=8080, url_host="myapp.example.com")
        assert server.url == "http://myapp.example.com:8080/callback"

    @pytest.mark.asyncio
    async def test_url_port_overrides_bind_port(self):
        server = AiohttpCallbackServer(_noop, host="0.0.0.0", port=8080, url_host="myapp.example.com", url_port=443, scheme="https")
        assert server.url == "https://myapp.example.com/callback"

    @pytest.mark.asyncio
    async def test_callback_receives_query_params(self):
        received = asyncio.Future()

        async def capture(params):
            received.set_result(params)

        server = AiohttpCallbackServer(capture, "127.0.0.1", 0, "/callback")
        await server.start()
        try:
            # Discover the actual bound port.
            site = list(server._runner._sites)[0]
            port = site._server.sockets[0].getsockname()[1]
            url = f"http://127.0.0.1:{port}/callback?code=abc123&session=xyz"

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    assert resp.status == 200

            params = await asyncio.wait_for(received, timeout=2)
            assert params["code"] == "abc123"
            assert params["session"] == "xyz"
        finally:
            await server.stop()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self):
        server = AiohttpCallbackServer(_noop, "127.0.0.1", 0, "/callback")
        await server.start()
        await server.stop()
        await server.stop()  # should not raise


class TestLocalhostServerFactory:
    @pytest.mark.asyncio
    async def test_factory_creates_server(self):
        factory = localhost_server(host="127.0.0.1", port=9999, path="/auth")
        server = await factory(_noop)
        assert server.url == "http://127.0.0.1:9999/auth"
