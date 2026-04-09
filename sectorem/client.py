"""Top-level Schwab API client container."""

from __future__ import annotations

from typing import Any

from .auth import Authenticator, AuthProvider, TokenStore
from .market import MarketDataClient
from .stream import StreamClient
from .trader import TraderClient


class SchwabClient:
    """
    Convenience container that wires together all Schwab API clients.

    Provides two construction modes:

    Easy mode — builds an Authenticator internally::

        client = SchwabClient(
            app_key="...",
            app_secret="...",
            token_store=FileTokenStore("~/.sectorem/token.json"),
        )

    Custom mode — uses a pre-built Authenticator::

        client = SchwabClient(auth=my_authenticator)

    The easy mode builds a default Authenticator with sensible
    defaults.  For full control over the Authenticator (callback
    server, login prompt, reauth threshold, etc.), build one
    yourself and pass it via *auth*.

    Accessing ``.trader`` or ``.market`` lazily creates the
    corresponding client on first access.  All clients share the
    same Authenticator and session.

    :param auth: Pre-built :class:`~.AuthProvider`. Mutually exclusive with *app_key* / *app_secret*.
    :param app_key: Schwab application key.
    :param app_secret: Schwab application secret.
    :param token_store: Token persistence backend.  Required when
        using *app_key* / *app_secret*.
    """

    def __init__(
        self,
        *,
        auth: AuthProvider | None = None,
        app_key: str | None = None,
        app_secret: str | None = None,
        token_store: TokenStore | None = None,
    ) -> None:
        if auth is not None and (app_key is not None or app_secret is not None):
            raise ValueError("Provide either 'auth' or 'app_key'/'app_secret', not both")

        if auth is not None:
            self._auth = auth
        elif app_key is not None and app_secret is not None:
            if token_store is None:
                raise ValueError("token_store is required when using app_key/app_secret")
            self._auth: AuthProvider = Authenticator(
                app_key=app_key,
                app_secret=app_secret,
                token_store=token_store,
            )
        else:
            raise ValueError("Provide either 'auth' or both 'app_key' and 'app_secret'")

        self._trader: TraderClient | None = None
        self._market: MarketDataClient | None = None
        self._stream: StreamClient | None = None

    @property
    def auth(self) -> AuthProvider:
        return self._auth

    @property
    def trader(self) -> TraderClient:
        if self._trader is None:
            self._trader = TraderClient(self._auth)
        return self._trader

    @property
    def stream(self) -> StreamClient:
        """
        The streaming client.

        Only available after :meth:`start` has been called.
        """
        if self._stream is None:
            raise RuntimeError("Stream client not available; call start() first")
        return self._stream

    @property
    def market(self) -> MarketDataClient:
        if self._market is None:
            self._market = MarketDataClient(self._auth)
        return self._market

    async def start(self) -> None:
        """
        Start the client.

        Starts the Authenticator, waits for authentication, and
        initializes the streaming client from user preferences.
        """
        await self._auth.start()
        await self._auth.wait()

        prefs = await self.trader.get_user_preferences()
        streamer = prefs["streamerInfo"][0]
        self._stream = StreamClient(
            self._auth,
            url=streamer["streamerSocketUrl"],
            customer_id=streamer["schwabClientCustomerId"],
            correl_id=streamer["schwabClientCorrelId"],
            channel=streamer["schwabClientChannel"],
            function_id=streamer["schwabClientFunctionId"],
        )

    async def stop(self) -> None:
        """Stop the client and release all resources."""
        if self._stream is not None:
            await self._stream.close()
            self._stream = None
        if self._trader is not None:
            await self._trader.close()
            self._trader = None
        if self._market is not None:
            await self._market.close()
            self._market = None
        await self._auth.stop()

    async def __aenter__(self) -> SchwabClient:
        await self.start()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.stop()
