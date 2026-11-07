"""Tests for the 1Password token store and auth provider."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("onepassword")

from onepassword import Item, ItemCategory, ItemField, ItemFieldType  # noqa: E402

from sectorem.auth import onepass  # noqa: E402
from sectorem.auth.manager import Authenticator  # noqa: E402
from sectorem.auth.onepass import (  # noqa: E402
    OnePasswordAuthProvider,
    OnePasswordClient,
    OnePasswordLookupError,
    OnePasswordTokenStore,
    create_authenticator,
)
from sectorem.auth.token import Token  # noqa: E402
from sectorem.errors import NotAuthenticatedError  # noqa: E402

VAULT_ID = "vault-1"
ITEM_ID = "item-1"


def _token(access_seconds: float = 1800, refresh_days: float = 0, access_token: str = "access") -> Token:
    now = datetime.now(timezone.utc)
    return Token(
        access_token=access_token,
        refresh_token="refresh",
        token_type="Bearer",
        scope="api",
        access_expires_at=now + timedelta(seconds=access_seconds),
        refresh_issued_at=now - timedelta(days=refresh_days),
    )


def _field(field_id: str, value: str, title: str | None = None, field_type=ItemFieldType.TEXT) -> ItemField:
    return ItemField(id=field_id, title=title or field_id, fieldType=field_type, value=value)


def _item(*fields: ItemField) -> Item:
    return Item(
        id=ITEM_ID,
        title="schwab",
        category=ItemCategory.APICREDENTIALS,
        vaultId=VAULT_ID,
        fields=list(fields),
        sections=[],
        notes="",
        tags=[],
        websites=[],
        version=1,
        files=[],
        createdAt="2026-01-01T00:00:00Z",
        updatedAt="2026-01-01T00:00:00Z",
    )


def _credentials() -> list[ItemField]:
    return [_field("username", "app-key"), _field("credential", "app-secret", field_type=ItemFieldType.CONCEALED)]


class FakeOnePassword:
    """Stands in for an authenticated :class:`onepassword.Client` holding one item."""

    def __init__(self, item: Item) -> None:
        self.item = item
        self.authentications = 0
        self.reads = 0
        self.writes = 0
        self.put_error: Exception | None = None
        self.get_error: Exception | None = None
        self.vaults = SimpleNamespace(list=AsyncMock(return_value=[SimpleNamespace(id=VAULT_ID, title="trading")]))
        self.items = SimpleNamespace(list=self._list, get=self._get, put=self._put)

    async def _list(self, vault_id):
        assert vault_id == VAULT_ID
        return [SimpleNamespace(id="other", title="other"), SimpleNamespace(id=ITEM_ID, title="schwab")]

    async def _get(self, vault_id, item_id):
        assert (vault_id, item_id) == (VAULT_ID, ITEM_ID)
        self.reads += 1
        if self.get_error is not None:
            raise self.get_error
        return self.item.model_copy(deep=True)

    async def _put(self, item):
        self.writes += 1
        if self.put_error is not None:
            error, self.put_error = self.put_error, None
            raise error
        self.item = item.model_copy(update={"version": item.version + 1}, deep=True)
        return self.item.model_copy(deep=True)

    def write_token(self, token: Token) -> None:
        """Do what the writer does, without going through the store."""
        fields = [f for f in self.item.fields if f.title != "token"]
        fields.append(_field("token", json.dumps(token.to_dict()), field_type=ItemFieldType.CONCEALED))
        self.item = self.item.model_copy(update={"fields": fields})

    def token_field(self) -> ItemField | None:
        return next((f for f in self.item.fields if f.title == "token"), None)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeOnePassword(_item(*_credentials()))

    async def authenticate(*, auth, integration_name, integration_version):
        assert auth == "service-token"
        fake.authentications += 1
        return fake

    monkeypatch.setattr(onepass.Client, "authenticate", authenticate)
    return fake


@pytest.fixture
def client(fake):
    return OnePasswordClient("service-token", "trading", "schwab")


def _provider(client, **kwargs) -> OnePasswordAuthProvider:
    kwargs.setdefault("poll_interval", 0.01)
    kwargs.setdefault("max_poll_interval", 0.02)
    kwargs.setdefault("access_wait_timeout", 0.5)
    return OnePasswordAuthProvider(client, **kwargs)


class TestOnePasswordClient:
    @pytest.mark.asyncio
    async def test_app_credentials(self, client):
        assert await client.app_credentials() == ("app-key", "app-secret")

    @pytest.mark.asyncio
    async def test_looks_up_once(self, client, fake):
        await client.get_item()
        await client.get_item()
        assert fake.authentications == 1
        assert fake.vaults.list.await_count == 1
        assert fake.reads == 2

    @pytest.mark.asyncio
    async def test_missing_vault(self, client, fake):
        fake.vaults.list.return_value = []
        with pytest.raises(OnePasswordLookupError, match="Vault 'trading'"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_missing_item(self, fake):
        client = OnePasswordClient("service-token", "trading", "nope")
        with pytest.raises(OnePasswordLookupError, match="Item 'nope'"):
            await client.connect()

    @pytest.mark.asyncio
    async def test_missing_app_secret(self, client, fake):
        fake.item = _item(_field("username", "app-key"))
        with pytest.raises(OnePasswordLookupError, match="'credential'"):
            await client.app_credentials()

    def test_duplicate_token_fields_warn_and_use_first(self, caplog):
        item = _item(_field("t1", "", title="token"), _field("t2", json.dumps(_token().to_dict()), title="token"))
        assert OnePasswordClient.parse_token(item) is None
        assert "2 fields titled 'token'" in caplog.text

    @pytest.mark.parametrize("value", ["", "not json", "[]", '{"access_token": "x"}'])
    def test_unparseable_token_is_none(self, value):
        item = _item(_field("token", value))
        assert OnePasswordClient.parse_token(item) is None


class TestOnePasswordTokenStore:
    @pytest.mark.asyncio
    async def test_load_without_token_field(self, client):
        assert await OnePasswordTokenStore(client).load() is None

    @pytest.mark.asyncio
    async def test_round_trip(self, client):
        token = _token()
        store = OnePasswordTokenStore(client)
        await store.save(token)
        assert await OnePasswordTokenStore(client).load() == token

    @pytest.mark.asyncio
    async def test_creates_concealed_field_in_unnamed_section(self, client, fake):
        await OnePasswordTokenStore(client).save(_token())

        field = fake.token_field()
        assert field.field_type == ItemFieldType.CONCEALED
        assert field.section_id == ""
        assert fake.item.sections == []
        assert [f.id for f in fake.item.fields if f.title != "token"] == ["username", "credential"]

    @pytest.mark.asyncio
    async def test_updates_existing_field_in_place(self, client, fake):
        fake.write_token(_token(access_token="old"))
        fake.item.fields[-1].field_type = ItemFieldType.TEXT

        await OnePasswordTokenStore(client).save(_token(access_token="new"))

        assert [f.title for f in fake.item.fields].count("token") == 1
        assert fake.token_field().field_type == ItemFieldType.TEXT
        assert json.loads(fake.token_field().value)["access_token"] == "new"
        assert fake.item.sections == []

    @pytest.mark.asyncio
    async def test_save_after_load_does_not_read(self, client, fake):
        store = OnePasswordTokenStore(client)
        await store.load()
        await store.save(_token(access_token="a"))
        await store.save(_token(access_token="b"))
        assert (fake.reads, fake.writes) == (1, 2)
        assert json.loads(fake.token_field().value)["access_token"] == "b"

    @pytest.mark.asyncio
    async def test_failed_write_refetches_and_retries(self, client, fake):
        store = OnePasswordTokenStore(client)
        await store.load()
        fake.put_error = Exception("item version conflict")

        await store.save(_token(access_token="retried"))

        assert (fake.reads, fake.writes) == (2, 2)
        assert json.loads(fake.token_field().value)["access_token"] == "retried"


class TestOnePasswordAuthProvider:
    @pytest.mark.asyncio
    async def test_raises_before_token_is_read(self, client):
        with pytest.raises(NotAuthenticatedError):
            await _provider(client).get_access_token()

    @pytest.mark.asyncio
    async def test_start_raises_on_missing_vault(self, client, fake):
        fake.vaults.list.return_value = []
        with pytest.raises(OnePasswordLookupError):
            await _provider(client).start()

    @pytest.mark.asyncio
    async def test_wait_returns_once_token_is_written(self, client, fake):
        provider = _provider(client)
        await provider.start()
        try:
            waiter = asyncio.create_task(provider.wait())
            await asyncio.sleep(0.05)
            assert not waiter.done()

            fake.write_token(_token(access_token="first"))
            await asyncio.wait_for(waiter, 1)
            assert await provider.get_access_token() == "first"
        finally:
            await provider.stop()

    @pytest.mark.asyncio
    async def test_fresh_token_is_not_reread(self, client, fake):
        fake.write_token(_token())
        provider = _provider(client)
        await provider.start()
        try:
            await provider.wait()
            reads = fake.reads
            for _ in range(5):
                assert await provider.get_access_token() == "access"
            assert fake.reads == reads
        finally:
            await provider.stop()

    @pytest.mark.asyncio
    async def test_expiring_token_is_returned_while_next_is_fetched(self, client, fake):
        fake.write_token(_token(access_seconds=10, access_token="old"))
        provider = _provider(client)
        await provider.start()
        try:
            await asyncio.sleep(0.05)
            assert await provider.get_access_token() == "old"

            fake.write_token(_token(access_token="new"))
            await asyncio.sleep(0.1)
            assert await provider.get_access_token() == "new"
        finally:
            await provider.stop()

    @pytest.mark.asyncio
    async def test_expired_token_waits_for_next(self, client, fake):
        fake.write_token(_token(access_seconds=-1, access_token="old"))
        provider = _provider(client)
        await provider.start()
        try:
            await asyncio.sleep(0.05)
            getter = asyncio.create_task(provider.get_access_token())
            await asyncio.sleep(0.05)
            assert not getter.done()

            fake.write_token(_token(access_token="new"))
            assert await asyncio.wait_for(getter, 1) == "new"
        finally:
            await provider.stop()

    @pytest.mark.asyncio
    async def test_expired_token_times_out(self, client, fake):
        fake.write_token(_token(access_seconds=-1))
        provider = _provider(client, access_wait_timeout=0.05)
        await provider.start()
        try:
            await asyncio.sleep(0.05)
            with pytest.raises(NotAuthenticatedError, match="expired"):
                await provider.get_access_token()
        finally:
            await provider.stop()

    @pytest.mark.asyncio
    async def test_expired_refresh_token_raises_immediately(self, client, fake):
        fake.write_token(_token(access_seconds=-1, refresh_days=8))
        provider = _provider(client, access_wait_timeout=10)
        await provider.start()
        try:
            await asyncio.sleep(0.05)
            with pytest.raises(NotAuthenticatedError):
                await asyncio.wait_for(provider.get_access_token(), 1)
        finally:
            await provider.stop()

    @pytest.mark.asyncio
    async def test_read_errors_are_retried(self, client, fake):
        fake.write_token(_token())
        fake.get_error = Exception("network down")
        provider = _provider(client)
        await provider.start()
        try:
            await asyncio.sleep(0.05)
            assert fake.reads > 1
            fake.get_error = None
            await asyncio.wait_for(provider.wait(), 1)
        finally:
            await provider.stop()

    @pytest.mark.asyncio
    async def test_polling_backs_off(self, client, fake):
        provider = _provider(client, poll_interval=0.01, max_poll_interval=0.08)
        await provider.start()
        try:
            await asyncio.sleep(0.4)
        finally:
            await provider.stop()
        # Fixed 10ms polling would read ~40 times; backing off to 80ms reads about 8.
        assert 3 <= fake.reads <= 12

    @pytest.mark.asyncio
    async def test_stop_cancels_fetch(self, client):
        provider = _provider(client)
        await provider.start()
        task = provider._fetch_task
        await provider.stop()
        assert task.cancelled()


class TestCreateAuthenticator:
    @pytest.mark.asyncio
    async def test_uses_item_credentials_and_store(self, client):
        prompt = AsyncMock()
        auth = await create_authenticator(client, login_prompt=prompt)

        assert isinstance(auth, Authenticator)
        assert (auth._app_key, auth._app_secret) == ("app-key", "app-secret")
        assert isinstance(auth._token_store, OnePasswordTokenStore)
        assert auth._login_prompt is prompt
