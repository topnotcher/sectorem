"""OAuth2 authenticator state machine."""

from __future__ import annotations

import asyncio
import enum
import logging
from collections.abc import Callable, Coroutine
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import aiohttp
from aiohttp import ClientSession

from ..errors import AuthenticationError, NotAuthenticatedError
from .server import CallbackServer, ServerFactory, localhost_server
from .token import Token, TokenStore

log = logging.getLogger(__name__)

AUTH_URL = "https://api.schwabapi.com/v1/oauth/authorize"
TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"

#: Max interval between maintenance loop iterations. Short enough to
#: recover promptly after system suspend/resume.
_MAINTENANCE_POLL_INTERVAL = 10.0

#: How long :meth:`Authenticator.get_access_token` waits for a fresh
#: token. Must exceed :data:`_MAINTENANCE_POLL_INTERVAL` plus the
#: refresh round-trip, so an expired-token caller doesn't give up
#: before the loop has had a chance to refresh.
_ACCESS_WAIT_TIMEOUT = _MAINTENANCE_POLL_INTERVAL + 5.0

#: Receives the authorization URL; presents it to the user.
LoginPrompt = Callable[[str], Coroutine[None, None, None]]


async def _default_prompt(url: str) -> None:
    """Print the authorization URL to stdout."""
    print(f"Authorize at: {url}")


class AuthState(enum.Enum):
    """Authenticator lifecycle states."""

    #: Not started or has been stopped.
    INACTIVE = enum.auto()
    #: Waiting for the user to complete the authorization flow.
    AUTHENTICATING = enum.auto()
    #: Authenticated and operational.
    READY = enum.auto()


class AuthProvider(ABC):
    """
    Abstract base for authentication providers.

    The only requirement is :meth:`get_access_token`. The
    :class:`Authenticator` implements the full OAuth2 flow, but
    simpler implementations (e.g. reading a token from Redis) work
    just as well.

    The ``start``/``stop``/``wait`` hooks are no-ops by default;
    override them if your provider has its own lifecycle.
    """

    @abstractmethod
    async def get_access_token(self) -> str:
        """
        Get the current access token.

        :raises NotAuthenticatedError: If no valid token is available.
        """
        ...

    async def start(self) -> None:
        """Start the auth provider."""

    async def stop(self) -> None:
        """Stop the auth provider and release resources."""

    async def wait(self) -> None:
        """
        Wait until authentication is established.

        This is typically called once at application start to avoid any API calls
        before authentication is ready. After authentication is ready initially,
        :meth:`~.get_access_token` may raise an exception rather than waiting.
        """


class Authenticator(AuthProvider):
    """
    OAuth2 state machine for the Schwab Trader API.

    Manages the full token lifecycle: initial authorization, automatic
    access-token refresh, proactive re-authorization before the
    refresh token expires, and persistent token storage.

    :param app_key: Schwab application key (client ID).
    :param app_secret: Schwab application secret.
    :param token_store: Backend for persisting tokens.
    :param server_factory: Creates the callback server.  Defaults to
        a localhost aiohttp server on port 8080.
    :param login_prompt: Called when the user must visit an
        authorization URL.  Defaults to printing to stdout.
    :param reauth_threshold: How long before refresh-token expiry to
        proactively request re-authorization.
    :param access_refresh_buffer: How long before access-token expiry
        to trigger a refresh.
    """

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        token_store: TokenStore,
        server_factory: ServerFactory | None = None,
        login_prompt: LoginPrompt | None = None,
        reauth_threshold: timedelta = timedelta(days=1),
        access_refresh_buffer: timedelta = timedelta(seconds=60),
    ) -> None:
        super().__init__()

        self._app_key = app_key
        self._app_secret = app_secret
        self._token_store = token_store
        self._server_factory = server_factory or localhost_server()
        self._login_prompt = login_prompt or _default_prompt
        self._reauth_threshold = reauth_threshold
        self._access_refresh_buffer = access_refresh_buffer

        self._token: Token | None = None
        self._server: CallbackServer | None = None
        self._session: ClientSession | None = None

        self._token_cond = asyncio.Condition()
        self._maintenance_task: asyncio.Task | None = None
        self._reauth_prompted: bool = False

    @property
    def state(self) -> AuthState:
        if self._maintenance_task is None:
            return AuthState.INACTIVE
        if self._refresh_expired():
            return AuthState.AUTHENTICATING
        return AuthState.READY

    async def get_access_token(self) -> str:
        """
        Get the current access token.

        If the access token has expired but the refresh token is still
        valid, waits briefly for the maintenance loop to refresh it.
        If the refresh token has expired, raises immediately since
        recovery requires manual re-authorization.

        :raises NotAuthenticatedError: If no valid token is available.
        """
        if not self._access_expired():
            return self._token.access_token

        if self._refresh_expired():
            raise NotAuthenticatedError("Not authenticated")

        async with self._token_cond:
            if self._access_expired() and not self._refresh_expired():
                try:
                    await asyncio.wait_for(
                        self._token_cond.wait(),
                        timeout=_ACCESS_WAIT_TIMEOUT,
                    )
                except TimeoutError:
                    pass

            if self._access_expired():
                raise NotAuthenticatedError("Not authenticated")

            return self._token.access_token

    async def wait(self) -> None:
        """Block until authentication is established."""
        async with self._token_cond:
            while self._refresh_expired():
                await self._token_cond.wait()

    async def start(self) -> None:
        """
        Start the authenticator.

        Loads any persisted token, starts the callback server, and
        launches the maintenance loop which handles all state
        transitions from that point on.
        """
        if self._maintenance_task is not None:
            raise RuntimeError("Authenticator already started")

        self._session = ClientSession()
        self._server = await self._server_factory(self._on_callback)
        await self._server.start()
        self._token = await self._token_store.load()

        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def stop(self) -> None:
        """Stop the authenticator and release resources."""
        await super().stop()

        if self._maintenance_task is not None:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass
            self._maintenance_task = None

        if self._server is not None:
            await self._server.stop()
            self._server = None

        if self._session is not None:
            await self._session.close()
            self._session = None

    async def _on_callback(self, params: dict[str, str]) -> None:
        """Handle the OAuth redirect from Schwab."""
        self._reauth_prompted = False

        code = params.get("code")
        if code is None:
            log.warning("Callback received without authorization code: %s", params)
            return

        log.info("Authorization code received; exchanging for tokens.")
        data = await self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._server.url,
        })
        token = Token.from_response(data)
        await self._token_store.save(token)
        await self._update_token(token)

    async def _maintenance_loop(self) -> None:
        """
        Single long-lived task that drives all state transitions.

        Evaluates the current token state on each iteration:
        no usable token triggers authorization, an expiring access
        token triggers a refresh, and a fully valid token sleeps
        until the next scheduled event.
        """
        while True:
            now = datetime.now(timezone.utc)

            if self._reauth_at() <= now:
                if not self._reauth_prompted:
                    self._prompt_for_auth()

                if self._refresh_expired():
                    await self.wait()

            if self._refresh_at() <= now:
                await self._refresh_access_token()

            next_wake = self._refresh_at()
            if self._reauth_at() < next_wake and not self._reauth_prompted:
                next_wake = self._reauth_at()

            # This polls rather than sleeping the full delay to handle things like system suspend/resume.
            delay = min(_MAINTENANCE_POLL_INTERVAL, max((next_wake - now).total_seconds(), 0))
            log.debug("Maintenance: sleeping %.0fs.", delay)
            await asyncio.sleep(delay)

    async def _refresh_access_token(self) -> None:
        """Refresh the access token using the refresh token."""
        try:
            data = await self._token_request({
                "grant_type": "refresh_token",
                "refresh_token": self._token.refresh_token,
            })
        except AuthenticationError:
            log.error("Token refresh failed; re-authorization required.")
            await self._update_token(None)
        else:
            token = Token.from_response(data, refresh_issued_at=self._token.refresh_issued_at)
            await self._token_store.save(token)
            await self._update_token(token)

    async def _update_token(self, token: Token | None) -> None:
        """Atomically update the current token and wake any waiters."""
        async with self._token_cond:
            self._token = token
            self._token_cond.notify_all()

    def _refresh_expired(self) -> bool:
        return self._token is None or self._token.refresh_expired

    def _reauth_at(self) -> datetime:
        if self._refresh_expired():
            return datetime.min.replace(tzinfo=timezone.utc)
        else:
            return self._token.refresh_expires_at - self._reauth_threshold

    def _refresh_at(self) -> datetime:
        if self._refresh_expired():
            return datetime.min.replace(tzinfo=timezone.utc)
        else:
            return self._token.access_expires_at - self._access_refresh_buffer

    def _access_expired(self) -> bool:
        return self._token is None or self._token.access_expired

    def _prompt_for_auth(self) -> None:
        self._reauth_prompted = True
        auth_url = self._build_auth_url()
        log.info("Authorization required: %s", auth_url)
        asyncio.create_task(self._login_prompt(auth_url))

    def _build_auth_url(self) -> str:
        """Build the Schwab authorization URL."""
        params = urlencode({
            "client_id": self._app_key,
            "redirect_uri": self._server.url,
            "response_type": "code",
        })
        return f"{AUTH_URL}?{params}"

    async def _token_request(self, data: dict) -> dict:
        """
        POST to the Schwab token endpoint.

        :returns: Parsed JSON response.
        :raises AuthenticationError: On HTTP errors.
        """
        async with self._session.post(
            TOKEN_URL,
            data=data,
            auth=aiohttp.BasicAuth(self._app_key, self._app_secret),
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise AuthenticationError(f"Token request failed: {resp.status} {body}")
            return await resp.json()
