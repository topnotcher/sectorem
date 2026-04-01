"""OAuth callback server."""

from __future__ import annotations

import abc
import ssl
from collections.abc import Awaitable, Callable
from importlib import resources

from aiohttp import web

#: Called by the server when Schwab redirects with query parameters.
AuthCallback = Callable[[dict[str, str]], Awaitable[None]]

#: Factory that creates a :class:`CallbackServer` wired to a callback.
ServerFactory = Callable[[AuthCallback], Awaitable["CallbackServer"]]


class CallbackServer(abc.ABC):
    """
    Receives the OAuth redirect from Schwab.

    Implementations range from a built-in aiohttp server to a thin
    adapter around an application's existing web server.
    """

    @property
    @abc.abstractmethod
    def url(self) -> str:
        """The full callback URL registered with Schwab."""
        ...

    async def start(self) -> None:
        """Start listening.  No-op if the server is externally managed."""

    async def stop(self) -> None:
        """Stop listening.  No-op if the server is externally managed."""


class AiohttpCallbackServer(CallbackServer):
    """
    Lightweight aiohttp server that listens for the OAuth redirect.

    :param callback: Called when Schwab redirects with query parameters.
    :param host: Address to bind the server to.
    :param port: Port to bind the server to.
    :param path: URL path to listen on.
    :param url_host: Hostname used in the callback URL.
        Defaults to *host*.  Set this when behind a reverse proxy.
    :param url_port: Port used in the callback URL.
        Defaults to *port*.
    :param scheme: URL scheme (``http`` or ``https``).
        Defaults to ``https`` when *ssl_context* is provided,
        ``http`` otherwise.
    :param ssl_context: TLS context for the server.  ``None``
        for plain HTTP.
    """

    def __init__(
        self,
        callback: AuthCallback,
        host: str = "127.0.0.1",
        port: int = 8080,
        path: str = "/callback",
        url_host: str | None = None,
        url_port: int | None = None,
        scheme: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._callback = callback
        self._host = host
        self._port = port
        self._path = path
        self._url_host = url_host or host
        self._url_port = url_port or port
        self._scheme = scheme or ("https" if ssl_context else "http")
        self._ssl_context = ssl_context
        self._runner: web.AppRunner | None = None

    @property
    def url(self) -> str:
        default_port = (
            (self._scheme == "http" and self._url_port == 80)
            or (self._scheme == "https" and self._url_port == 443)
        )
        if default_port:
            return f"{self._scheme}://{self._url_host}{self._path}"
        else:
            return f"{self._scheme}://{self._url_host}:{self._url_port}{self._path}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get(self._path, self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port, ssl_context=self._ssl_context)
        await site.start()

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _handle(self, request: web.Request) -> web.Response:
        params = dict(request.query)
        await self._callback(params)
        return web.Response(
            text="Authorization complete. You may close this window.",
            content_type="text/plain",
        )


def _default_ssl_context() -> ssl.SSLContext:
    """
    Build an SSL context using the bundled self-signed certificate.

    The certificate covers ``IP:127.0.0.1`` and is valid for 10 years.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    etc = resources.files("sectorem") / "etc"
    with resources.as_file(etc / "localhost.crt") as certfile, \
         resources.as_file(etc / "localhost.key") as keyfile:
        ctx.load_cert_chain(certfile, keyfile)
    return ctx


def localhost_server(
    host: str = "127.0.0.1",
    port: int = 8443,
    path: str = "/callback",
) -> ServerFactory:
    """
    Create a :class:`ServerFactory` for a localhost callback server.

    Returns a factory that, when called with an :data:`AuthCallback`,
    produces an HTTPS :class:`AiohttpCallbackServer` bound to the
    given address using the bundled self-signed certificate.

    Binds to *port* (default 8443) but advertises port 443 in the
    callback URL, assuming a redirect (e.g. ``iptables``, ``socat``)
    from 443 to the bind port.
    """

    async def factory(callback: AuthCallback) -> CallbackServer:
        return AiohttpCallbackServer(
            callback, host, port, path,
            url_port=port,
            ssl_context=_default_ssl_context(),
        )

    return factory
