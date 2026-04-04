"""Tests for the Authenticator state machine."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from sectorem.auth.manager import Authenticator, AuthState
from sectorem.auth.server import CallbackServer
from sectorem.auth.token import Token, TokenStore
from sectorem.errors import NotAuthenticatedError


class MemoryTokenStore(TokenStore):
    """In-memory token store for tests."""

    def __init__(self, token: Token | None = None) -> None:
        self.token = token

    async def load(self) -> Token | None:
        return self.token

    async def save(self, token: Token) -> None:
        self.token = token


class FakeCallbackServer(CallbackServer):
    """Test server that records its lifecycle and exposes a trigger."""

    def __init__(self, callback):
        self._callback = callback
        self.started = False
        self.stopped = False

    @property
    def url(self) -> str:
        return "http://127.0.0.1:9999/callback"

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    async def simulate_redirect(self, params: dict[str, str]) -> None:
        """Simulate Schwab redirecting with the given query params."""
        await self._callback(params)


def _fake_server_factory():
    """
    Return a (factory, server_ref) pair.

    ``server_ref`` is populated after the factory is called.
    """
    server_holder: list[FakeCallbackServer] = []

    async def factory(callback):
        server = FakeCallbackServer(callback)
        server_holder.append(server)
        return server

    return factory, server_holder


def _make_valid_token(access_minutes: int = 30, refresh_days: int = 0) -> Token:
    """Create a token with the given remaining lifetimes."""
    now = datetime.now(timezone.utc)
    return Token(
        access_token="valid-access",
        refresh_token="valid-refresh",
        token_type="Bearer",
        scope="api",
        access_expires_at=now + timedelta(minutes=access_minutes),
        refresh_issued_at=now - timedelta(days=refresh_days),
    )


def _token_response(access_token: str = "new-access", refresh_token: str = "new-refresh",
                     expires_in: int = 1800) -> dict:
    """Fake Schwab token endpoint response."""
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "scope": "api",
        "expires_in": expires_in,
    }


class TestAuthenticatorLifecycle:
    @pytest.mark.asyncio
    async def test_no_token_enters_authenticating(self):
        factory, servers = _fake_server_factory()
        prompt = AsyncMock()
        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=MemoryTokenStore(),
            server_factory=factory,
            login_prompt=prompt,
        )
        await auth.start()
        try:
            await asyncio.sleep(0.05)
            assert auth.state == AuthState.AUTHENTICATING
            assert servers[0].started
            prompt.assert_called_once()
        finally:
            await auth.stop()

    @pytest.mark.asyncio
    async def test_access_token_raises_when_authenticating(self):
        factory, _ = _fake_server_factory()
        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=MemoryTokenStore(),
            server_factory=factory,
            login_prompt=AsyncMock(),
        )
        await auth.start()
        try:
            await asyncio.sleep(0.05)
            with pytest.raises(NotAuthenticatedError):
                _ = await auth.get_access_token()
        finally:
            await auth.stop()

    @pytest.mark.asyncio
    async def test_valid_token_enters_ready(self):
        factory, _ = _fake_server_factory()
        token = _make_valid_token()
        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=MemoryTokenStore(token),
            server_factory=factory,
            login_prompt=AsyncMock(),
        )
        await auth.start()
        try:
            await asyncio.sleep(0.05)
            assert auth.state == AuthState.READY
            assert await auth.get_access_token() == "valid-access"
        finally:
            await auth.stop()

    @pytest.mark.asyncio
    async def test_expired_access_refreshes(self):
        factory, _ = _fake_server_factory()
        token = _make_valid_token(access_minutes=-5, refresh_days=1)
        store = MemoryTokenStore(token)

        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=store,
            server_factory=factory,
            login_prompt=AsyncMock(),
        )

        with patch.object(auth, "_token_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _token_response()
            await auth.start()
            try:
                await asyncio.sleep(0.05)
                assert auth.state == AuthState.READY
                assert await auth.get_access_token() == "new-access"
                mock_req.assert_called_once()
            finally:
                await auth.stop()

    @pytest.mark.asyncio
    async def test_expired_refresh_reauthorizes(self):
        factory, _ = _fake_server_factory()
        token = _make_valid_token(access_minutes=-5, refresh_days=8)
        prompt = AsyncMock()

        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=MemoryTokenStore(token),
            server_factory=factory,
            login_prompt=prompt,
        )
        await auth.start()
        try:
            await asyncio.sleep(0.05)
            assert auth.state == AuthState.AUTHENTICATING
            prompt.assert_called_once()
        finally:
            await auth.stop()

    @pytest.mark.asyncio
    async def test_callback_exchanges_code_and_activates(self):
        factory, servers = _fake_server_factory()
        store = MemoryTokenStore()

        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=store,
            server_factory=factory,
            login_prompt=AsyncMock(),
        )

        with patch.object(auth, "_token_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _token_response()
            await auth.start()
            await asyncio.sleep(0.05)
            assert auth.state == AuthState.AUTHENTICATING

            await servers[0].simulate_redirect({"code": "auth-code-123"})

            assert auth.state == AuthState.READY
            assert await auth.get_access_token() == "new-access"
            assert store.token is not None
            await auth.stop()

    @pytest.mark.asyncio
    async def test_wait_resolves_on_activation(self):
        factory, servers = _fake_server_factory()

        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=MemoryTokenStore(),
            server_factory=factory,
            login_prompt=AsyncMock(),
        )

        with patch.object(auth, "_token_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _token_response()
            await auth.start()

            async def activate_later():
                await asyncio.sleep(0.05)
                await servers[0].simulate_redirect({"code": "abc"})

            task = asyncio.create_task(activate_later())
            await asyncio.wait_for(auth.wait(), timeout=2)
            assert auth.state == AuthState.READY
            assert await auth.get_access_token() == "new-access"
            await task
            await auth.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self):
        factory, servers = _fake_server_factory()
        auth = Authenticator(
            app_key="key",
            app_secret="secret",
            token_store=MemoryTokenStore(_make_valid_token()),
            server_factory=factory,
            login_prompt=AsyncMock(),
        )
        await auth.start()
        await auth.stop()

        assert auth.state == AuthState.INACTIVE
        assert servers[0].stopped
