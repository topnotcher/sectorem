"""Shared test fixtures."""

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer


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
