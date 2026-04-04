"""Shared test fixtures."""

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

from sectorem.rest import RestClient


@pytest_asyncio.fixture
async def aiohttp_server():
    """
    Factory fixture that creates test HTTP servers.

    Usage::

        async def test_example(aiohttp_server):
            app = web.Application()
            app.router.add_get("/test", handler)
            server = await aiohttp_server(app)
            url = server.make_url("/test")
    """
    servers = []

    async def factory(app: web.Application) -> TestServer:
        server = TestServer(app)
        await server.start_server()
        servers.append(server)
        return server

    yield factory

    for server in servers:
        await server.close()


@pytest_asyncio.fixture(autouse=True)
async def _close_rest_clients(monkeypatch):
    """Auto-close any RestClient sessions created during a test."""
    clients: list[RestClient] = []
    original_init = RestClient.__init__

    def tracking_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        clients.append(self)

    monkeypatch.setattr(RestClient, "__init__", tracking_init)
    yield
    for client in clients:
        await client.close()
