"""Tests for Token model and TokenStore implementations."""

from datetime import datetime, timedelta, timezone

import pytest

from sectorem.auth.token import FileTokenStore, Token


def _make_token(
    access_offset: timedelta = timedelta(minutes=30),
    refresh_offset: timedelta = timedelta(0),
) -> Token:
    """Create a token with controllable expiry times.

    ``access_offset`` is added to *now* to get ``access_expires_at``.
    ``refresh_offset`` is subtracted from *now* to get ``refresh_issued_at``.
    """
    now = datetime.now(timezone.utc)
    return Token(
        access_token="access-abc",
        refresh_token="refresh-xyz",
        token_type="Bearer",
        scope="api",
        access_expires_at=now + access_offset,
        refresh_issued_at=now - refresh_offset,
    )


class TestToken:
    def test_access_not_expired(self):
        token = _make_token(access_offset=timedelta(minutes=30))
        assert not token.access_expired

    def test_access_expired(self):
        token = _make_token(access_offset=timedelta(minutes=-1))
        assert token.access_expired

    def test_refresh_not_expired(self):
        token = _make_token(refresh_offset=timedelta(days=3))
        assert not token.refresh_expired

    def test_refresh_expired(self):
        token = _make_token(refresh_offset=timedelta(days=8))
        assert token.refresh_expired

    def test_refresh_expires_at(self):
        now = datetime.now(timezone.utc)
        token = _make_token(refresh_offset=timedelta(0))
        expected = now + timedelta(days=7)
        assert abs((token.refresh_expires_at - expected).total_seconds()) < 1

    def test_from_response(self):
        data = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "token_type": "Bearer",
            "scope": "api",
            "expires_in": 1800,
        }
        token = Token.from_response(data)
        assert token.access_token == "at-123"
        assert token.refresh_token == "rt-456"
        assert not token.access_expired

    def test_from_response_preserves_refresh_issued_at(self):
        old_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
        data = {
            "access_token": "at-new",
            "refresh_token": "rt-same",
            "expires_in": 1800,
        }
        token = Token.from_response(data, refresh_issued_at=old_time)
        assert token.refresh_issued_at == old_time

    def test_round_trip_dict(self):
        token = _make_token()
        restored = Token.from_dict(token.to_dict())
        assert restored.access_token == token.access_token
        assert restored.refresh_token == token.refresh_token
        assert restored.access_expires_at == token.access_expires_at
        assert restored.refresh_issued_at == token.refresh_issued_at


class TestFileTokenStore:
    @pytest.mark.asyncio
    async def test_load_missing_file(self, tmp_path):
        store = FileTokenStore(tmp_path / "tokens.json")
        assert await store.load() is None

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        path = tmp_path / "tokens.json"
        store = FileTokenStore(path)
        token = _make_token()
        await store.save(token)
        loaded = await store.load()
        assert loaded.access_token == token.access_token
        assert loaded.refresh_token == token.refresh_token

    @pytest.mark.asyncio
    async def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "tokens.json"
        store = FileTokenStore(path)
        await store.save(_make_token())
        assert path.exists()
