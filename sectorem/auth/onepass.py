"""
Share Schwab tokens through a 1Password item.

One process, the *writer*, runs an :class:`~sectorem.auth.manager.Authenticator` whose token store is the item. It
refreshes the access token and handles the weekly re-authorization. Any number of *readers* use
:class:`OnePasswordAuthProvider`, which reads the access token from the item and never talks to Schwab's token endpoint.

Requires the ``onepass`` extra (``pip install sectorem[onepass]``).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from onepassword import Client, DesktopAuth, Item, ItemField, ItemFieldType

from ..errors import NotAuthenticatedError
from .manager import Authenticator, AuthProvider
from .token import Token, TokenStore

__all__ = [
    "create_authenticator",
    "OnePasswordAuthProvider",
    "OnePasswordClient",
    "OnePasswordLookupError",
    "OnePasswordTokenStore",
]

log = logging.getLogger(__name__)

INTEGRATION_NAME = "sectorem"
INTEGRATION_VERSION = "0.1.0"


class OnePasswordLookupError(LookupError):
    """The configured vault, item or field does not exist."""


def _find_by_title(collection, title: str) -> Any | None:
    for obj in collection:
        if obj.title == title:
            return obj
    return None


def _find_field(item: Item, field_id: str) -> ItemField | None:
    for field in item.fields:
        if field.id == field_id:
            return field
    return None


class OnePasswordClient:
    """
    Access to the 1Password item that holds the Schwab credentials and token.

    The item is an *API Credential* whose built-in fields hold the app key (``username``) and app secret
    (``credential``), plus a field titled ``token`` holding the token JSON. Only the writer needs the key and secret; the
    token field is created on the first save if it does not exist.

    The vault and item are looked up by name once, then addressed by ID. Each later read or write is one request
    against 1Password's rate limits.

    :param auth: A service account token or a :class:`onepassword.DesktopAuth`.
    :param vault_name: The vault containing the item.
    :param item_name: The item's title.
    """

    #: Title of the field holding the token JSON.
    TOKEN_FIELD_TITLE = "token"
    #: ID of the field holding the Schwab app key.
    APP_KEY_FIELD_ID = "username"
    #: ID of the field holding the Schwab app secret.
    APP_SECRET_FIELD_ID = "credential"

    def __init__(self, auth: str | DesktopAuth, vault_name: str, item_name: str) -> None:
        self._auth = auth
        self._vault_name = vault_name
        self._item_name = item_name

        self._client: Client | None = None
        self._vault_id: str | None = None
        self._item_id: str | None = None
        self._lock = asyncio.Lock()

    async def _ids(self) -> tuple[Client, str, str]:
        """Authenticate and look up the vault and item IDs, once."""
        async with self._lock:
            if self._client is None:
                self._client = await Client.authenticate(
                    auth=self._auth, integration_name=INTEGRATION_NAME, integration_version=INTEGRATION_VERSION,
                )

            vault_id, item_id = self._vault_id, self._item_id
            if vault_id is None or item_id is None:
                vault = _find_by_title(await self._client.vaults.list(), self._vault_name)
                if vault is None:
                    raise OnePasswordLookupError(f"Vault {self._vault_name!r} not found.")

                item = _find_by_title(await self._client.items.list(vault.id), self._item_name)
                if item is None:
                    raise OnePasswordLookupError(f"Item {self._item_name!r} not found in vault {self._vault_name!r}.")

                vault_id, item_id = self._vault_id, self._item_id = vault.id, item.id

            return self._client, vault_id, item_id

    async def connect(self) -> None:
        """
        Authenticate to 1Password and look up the vault and item.

        Other methods do this on first use; calling it first surfaces a bad token or name immediately.

        :raises OnePasswordLookupError: If the vault or item does not exist.
        """
        await self._ids()

    async def get_item(self) -> Item:
        """
        Fetch the item.

        :raises OnePasswordLookupError: If the vault or item does not exist.
        """
        client, vault_id, item_id = await self._ids()
        return await client.items.get(vault_id, item_id)

    async def put_item(self, item: Item) -> Item:
        """Replace the item, returning the stored version."""
        client, _, _ = await self._ids()
        return await client.items.put(item)

    async def app_credentials(self) -> tuple[str, str]:
        """
        Read the Schwab app key and secret.

        :raises OnePasswordLookupError: If either field is missing or empty.
        """
        item = await self.get_item()
        values = []
        for field_id in (self.APP_KEY_FIELD_ID, self.APP_SECRET_FIELD_ID):
            field = _find_field(item, field_id)
            if field is None or not field.value:
                raise OnePasswordLookupError(f"Field {field_id!r} is missing or empty in item {self._item_name!r}.")
            values.append(field.value)
        return values[0], values[1]

    @classmethod
    def token_field(cls, item: Item) -> ItemField | None:
        """The field titled :attr:`TOKEN_FIELD_TITLE`, or ``None``. If there are several, the first."""
        fields = [field for field in item.fields if field.title == cls.TOKEN_FIELD_TITLE]
        if len(fields) > 1:
            log.warning("Item %r has %d fields titled %r; using the first.", item.title, len(fields),
                        cls.TOKEN_FIELD_TITLE)
        return fields[0] if fields else None

    @classmethod
    def parse_token(cls, item: Item) -> Token | None:
        """The token stored in ``item``, or ``None`` if the field is missing or unparseable."""
        field = cls.token_field(item)
        if field is None or not field.value:
            return None

        try:
            return Token.from_dict(json.loads(field.value))
        except (KeyError, TypeError, ValueError):
            log.warning("Failed to parse the %r field as a token; ignoring.", cls.TOKEN_FIELD_TITLE)
            return None


class OnePasswordTokenStore(TokenStore):
    """
    Token store for the writer, backed by a 1Password item.

    The item from the last read or write is kept, so a save normally costs one write and no read. If the write fails,
    for example because the item was edited elsewhere, the item is fetched again and the write retried once.

    There must be only one writer per item. Two would each refresh with the same refresh token and overwrite each other.
    """

    def __init__(self, client: OnePasswordClient) -> None:
        self._client = client
        self._item: Item | None = None

    async def load(self) -> Token | None:
        self._item = await self._client.get_item()
        return self._client.parse_token(self._item)

    async def save(self, token: Token) -> None:
        value = json.dumps(token.to_dict())

        if self._item is not None:
            try:
                self._item = await self._client.put_item(self._with_token(self._item, value))
                return
            except Exception as e:
                log.warning("Failed to write the token to 1Password; fetching the item and retrying: %s", e)
                self._item = None

        item = await self._client.get_item()
        self._item = await self._client.put_item(self._with_token(item, value))

    def _with_token(self, item: Item, value: str) -> Item:
        """A copy of ``item`` with the token field set to ``value``, creating the field if needed."""
        item = item.model_copy(deep=True)

        field = OnePasswordClient.token_field(item)
        if field is not None:
            field.value = value
            return item

        # The empty section ID is the item's unnamed section, which also holds the built-in fields.
        item.fields.append(ItemField(
            id=OnePasswordClient.TOKEN_FIELD_TITLE,
            title=OnePasswordClient.TOKEN_FIELD_TITLE,
            sectionId="",
            fieldType=ItemFieldType.CONCEALED,
            value=value,
        ))
        return item


class OnePasswordAuthProvider(AuthProvider):
    """
    Read-only auth provider that takes the access token from a 1Password item kept current by a writer.

    The item is read again only when the token is about to expire: ``refresh_buffer`` before expiry, the current token
    is still returned while the new one is fetched in the background. ``refresh_buffer`` should be shorter than the
    writer's ``access_refresh_buffer`` (60 seconds by default), so the new token is there by the time it is looked for.

    When the item does not have a fresher token, it is polled with exponential backoff from ``poll_interval`` up to
    ``max_poll_interval``. This keeps a writer outage, or a re-authorization nobody has done yet, from using up the
    1Password rate limits.

    :param client: The item to read.
    :param refresh_buffer: How long before access-token expiry to fetch the next token.
    :param access_wait_timeout: How long :meth:`get_access_token` waits for a new token once the current one has
        expired.
    :param poll_interval: The first delay between reads while waiting for a new token.
    :param max_poll_interval: The longest delay between reads.
    """

    def __init__(
        self,
        client: OnePasswordClient,
        *,
        refresh_buffer: timedelta = timedelta(seconds=30),
        access_wait_timeout: float = 60.0,
        poll_interval: float = 5.0,
        max_poll_interval: float = 300.0,
    ) -> None:
        self._client = client
        self._refresh_buffer = refresh_buffer
        self._access_wait_timeout = access_wait_timeout
        self._poll_interval = poll_interval
        self._max_poll_interval = max_poll_interval

        self._token: Token | None = None
        self._fetch_task: asyncio.Task | None = None

    async def start(self) -> None:
        """
        Connect to 1Password and start fetching the token.

        :raises OnePasswordLookupError: If the vault or item does not exist.
        """
        await self._client.connect()
        self._fetch()

    async def stop(self) -> None:
        """Stop any fetch in progress."""
        task, self._fetch_task = self._fetch_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def wait(self) -> None:
        """
        Block until 1Password has a usable token.

        :raises OnePasswordLookupError: If the vault or item does not exist.
        """
        while self._token is None or self._token.refresh_expired:
            await asyncio.shield(self._fetch())

    async def get_access_token(self) -> str:
        """
        Get the current access token.

        Waits up to ``access_wait_timeout`` for a new token if the current access token has expired.

        :raises NotAuthenticatedError: If there is no token, its refresh token has expired, or no new token appeared in
            time.
        """
        token = self._token
        if token is None or token.refresh_expired:
            if token is not None:
                self._fetch()
            raise NotAuthenticatedError("No valid token in 1Password")

        if self._fresh(token):
            return token.access_token

        task = self._fetch()
        if not token.access_expired:
            return token.access_token

        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self._access_wait_timeout)
        except TimeoutError:
            raise NotAuthenticatedError("Access token expired; no new token in 1Password") from None
        assert self._token is not None
        return self._token.access_token

    def _fresh(self, token: Token) -> bool:
        return datetime.now(timezone.utc) < token.access_expires_at - self._refresh_buffer

    def _fetch(self) -> asyncio.Task:
        """The running fetch, or a new one."""
        if self._fetch_task is None or self._fetch_task.done():
            self._fetch_task = asyncio.create_task(self._poll())
        return self._fetch_task

    async def _poll(self) -> None:
        """Read the item until it has a token fresher than the current one, with backoff."""
        delay = self._poll_interval
        while True:
            try:
                token = self._client.parse_token(await self._client.get_item())
            except OnePasswordLookupError:
                raise
            except Exception as e:
                log.warning("Failed to read the token from 1Password: %s", e)
                token = None

            if token is not None and not token.refresh_expired and self._fresh(token):
                self._token = token
                log.info("Token read from 1Password; access token expires at %s.", token.access_expires_at)
                return

            if token is not None and (self._token is None or token.access_expires_at > self._token.access_expires_at):
                # Not fresh, but newer than ours: an expired access token with a live refresh token still lets
                # get_access_token() know to wait rather than give up.
                self._token = token

            log.info("No fresh token in 1Password; checking again in %.0fs.", delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, self._max_poll_interval)


async def create_authenticator(client: OnePasswordClient, **kwargs) -> Authenticator:
    """
    Create the writer: an :class:`~sectorem.auth.manager.Authenticator` with the app key and secret from the item and
    the item as its token store.

    Run exactly one per item. Example::

        op = OnePasswordClient(os.environ["OP_SERVICE_ACCOUNT_TOKEN"], "trading", "schwab")
        auth = await create_authenticator(op, login_prompt=post_to_discord)
        async with SchwabClient(auth=auth) as client:
            ...

    :param client: The item holding the credentials and token.
    :param kwargs: Passed to :class:`~sectorem.auth.manager.Authenticator`, e.g. ``login_prompt`` or
        ``server_factory``.
    :raises OnePasswordLookupError: If the vault, item, app key or app secret is missing.
    """
    app_key, app_secret = await client.app_credentials()
    return Authenticator(app_key=app_key, app_secret=app_secret, token_store=OnePasswordTokenStore(client), **kwargs)
