"""Tests for the OAuth callback server."""

import asyncio
import ssl

import aiohttp
import pytest

from sectorem.auth.server import AiohttpCallbackServer, localhost_server, _default_ssl_context


async def _noop(params):
    pass


class TestAiohttpCallbackServer:
    @pytest.mark.asyncio
    async def test_url_format(self):
        server = AiohttpCallbackServer(_noop, "127.0.0.1", 9876, "/cb")
        assert server.url == "http://127.0.0.1:9876/cb"

    @pytest.mark.asyncio
    async def test_url_omits_port_80_for_http(self):
        server = AiohttpCallbackServer(_noop, port=80)
        assert server.url == "http://127.0.0.1/callback"

    @pytest.mark.asyncio
    async def test_url_omits_port_443_for_https(self):
        ssl_ctx = _default_ssl_context()
        server = AiohttpCallbackServer(_noop, port=443, ssl_context=ssl_ctx)
        assert server.url == "https://127.0.0.1/callback"

    @pytest.mark.asyncio
    async def test_url_includes_non_default_port(self):
        ssl_ctx = _default_ssl_context()
        server = AiohttpCallbackServer(_noop, port=8443, ssl_context=ssl_ctx)
        assert server.url == "https://127.0.0.1:8443/callback"

    @pytest.mark.asyncio
    async def test_explicit_url_overrides_computed(self):
        server = AiohttpCallbackServer(
            _noop, host="0.0.0.0", port=8080,
            url="https://myapp.example.com/callback",
        )
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
    async def test_callback_receives_query_params_https(self):
        received = asyncio.Future()

        async def capture(params):
            received.set_result(params)

        ssl_ctx = _default_ssl_context()
        server = AiohttpCallbackServer(capture, "127.0.0.1", 0, "/callback", ssl_context=ssl_ctx)
        await server.start()
        try:
            site = list(server._runner._sites)[0]
            port = site._server.sockets[0].getsockname()[1]
            url = f"https://127.0.0.1:{port}/callback?code=abc123&session=xyz"

            # Trust the self-signed cert for this request.
            client_ssl = ssl.create_default_context()
            client_ssl.check_hostname = False
            client_ssl.verify_mode = ssl.CERT_NONE

            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=client_ssl) as resp:
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
    async def test_factory_creates_https_server(self):
        factory = localhost_server()
        server = await factory(_noop)
        assert server.url == "https://127.0.0.1:8443"
        assert server._port == 8443
        assert server._path == '/'
        assert server._ssl_context is not None
