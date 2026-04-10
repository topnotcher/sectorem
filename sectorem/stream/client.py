"""Schwab streaming WebSocket client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from ..auth import AuthProvider
from ..errors import StreamError
from .fields import StreamField, StreamService

log = logging.getLogger(__name__)
_EASTERN = ZoneInfo("America/New_York")

#: Default timeout for subscribe operations.
SUBSCRIBE_TIMEOUT = 60

#: Callback type for streaming data messages.
StreamCallback = Callable[[dict], Coroutine[Any, Any, None] | None]


@dataclass(frozen=True, slots=True)
class _Handle:
    """Internal tracking for a single subscriber."""
    service: str
    keys: str | None
    fields: tuple[int, ...]
    callback: StreamCallback


@dataclass
class _Command:
    """A command queued for transmission."""
    request_id: str
    service: str
    command: str
    parameters: dict[str, str]
    future: asyncio.Future[dict]


@dataclass
class _WireState:
    """Tracks what is currently subscribed on the wire for a service."""
    keys: set[str]
    fields: set[int]


class Subscription:
    """
    Handle for a streaming subscription.

    Returned by :meth:`StreamClient.subscribe`. Call :meth:`cancel`
    to remove the subscription.
    """

    def __init__(self, client: StreamClient, handle: _Handle) -> None:
        self._client = client
        self._handle = handle

    async def cancel(self) -> None:
        """Cancel this subscription."""
        await self._client._remove_subscription(self._handle)


class StreamClient:
    """
    WebSocket client for Schwab's streaming API.

    Manages the WebSocket connection lifecycle, login handshake,
    subscription tracking, and message dispatch. Connects lazily
    on first subscription and disconnects when the last subscription
    is cancelled.

    This class should not be instantiated directly; use
    :meth:`~sectorem.client.SchwabClient.stream` instead.

    :param auth: Auth provider for access tokens.
    :param url: WebSocket URL from user preferences.
    :param customer_id: ``schwabClientCustomerId`` from user preferences.
    :param correl_id: ``schwabClientCorrelId`` from user preferences.
    :param channel: ``SchwabClientChannel`` from user preferences.
    :param function_id: ``SchwabClientFunctionId`` from user preferences.
    """

    def __init__(
        self,
        auth: AuthProvider,
        *,
        url: str,
        customer_id: str,
        correl_id: str,
        channel: str,
        function_id: str,
    ) -> None:
        self._auth = auth
        self._url = url
        self._customer_id = customer_id
        self._correl_id = correl_id
        self._channel = channel
        self._function_id = function_id

        self._request_id: int = 0
        self._pending: dict[str, asyncio.Future[dict]] = {}
        self._handles: set[_Handle] = set()
        self._wire: dict[str, _WireState] = {}

        self._tx_queue: asyncio.Queue[_Command] = asyncio.Queue()
        self._supervisor_task: asyncio.Task | None = None

    async def subscribe(
        self,
        service: StreamService,
        callback: StreamCallback,
        *,
        keys: str | None = None,
        fields: Sequence[StreamField],
        timeout: float = SUBSCRIBE_TIMEOUT,
    ) -> Subscription:
        """
        Subscribe to a streaming service.

        Returns a :class:`Subscription` handle whose
        :meth:`~Subscription.cancel` method removes the subscription.

        :param service: Schwab service name (e.g. ``ACCT_ACTIVITY``).
        :param callback: Called with each data message dict.
        :param keys: Comma-separated keys (e.g. symbols).
        :param fields: Field names from the service's field enum (e.g. :class:`~.fields.EquityField`).
        :param timeout: Seconds to wait for the subscription to be confirmed.
        :raises asyncio.TimeoutError: If not confirmed in time.
        """
        field_type = service.field_type
        frozen_fields = tuple(field_type(f).number for f in fields)
        handle = _Handle(
            service=service, keys=keys, fields=frozen_fields, callback=callback,
        )
        self._handles.add(handle)
        self._ensure_supervisor()

        futs = self._sync_subscribe(service, keys, frozen_fields)

        if futs:
            try:
                results = await asyncio.wait_for(
                    asyncio.gather(*futs), timeout=timeout,
                )
            except asyncio.TimeoutError:
                self._handles.discard(handle)
                raise asyncio.TimeoutError(f"Timed out waiting for {service} subscription")

            for resp in results:
                code = resp.get("content", {}).get("code")
                if code != 0:
                    self._handles.discard(handle)
                    msg = resp.get("content", {}).get("msg", "Unknown error")
                    raise StreamError(f"{service} subscription failed (code {code}): {msg}")

        return Subscription(self, handle)

    async def _remove_subscription(self, handle: _Handle) -> None:
        """Remove a subscription by handle."""
        try:
            self._handles.remove(handle)
        except KeyError:
            return

        self._sync_unsubscribe(handle.service)

        if not self._handles:
            await self._stop_supervisor()

    async def close(self) -> None:
        """Close the streaming connection and cancel all subscriptions."""
        self._handles.clear()
        self._wire.clear()
        await self._stop_supervisor()

    def _sync_subscribe(
        self, service: str, keys: str | None, fields: tuple[int, ...],
    ) -> list[asyncio.Future[dict]]:
        """
        Compute the diff between desired and wire state for a new subscription and enqueue
        the necessary commands. Returns futures for any commands sent.
        """
        requested_keys = set(keys.split(",")) if keys else set()
        requested_fields = set(fields)

        state = self._wire.get(service)
        futs: list[asyncio.Future[dict]] = []

        if state is None:
            log.debug("No existing subscription for %s. Sending ADD.", service)
            fut = self._enqueue_add(service, keys, fields)
            self._wire[service] = _WireState(keys=requested_keys, fields=requested_fields)
            futs.append(fut)
            return futs

        new_keys = requested_keys - state.keys
        if new_keys:
            log.debug("Existing subscription for %s. Adding keys %s.", service, new_keys)
            fut = self._enqueue_add(service, ",".join(new_keys), fields)
            state.keys |= new_keys
            futs.append(fut)

        new_fields = requested_fields - state.fields
        if new_fields:
            log.debug("Existing subscription for %s. Adding fields %s.", service, new_fields)
            union = state.fields | requested_fields
            fut = self._enqueue_view(service, union)
            state.fields = union
            futs.append(fut)

        return futs

    def _sync_unsubscribe(self, service: str) -> None:
        """
        Update wire state after a handle is removed. Sends UNSUBS
        for keys that are no longer needed by any handle.
        """
        # Compute desired keys from remaining handles.
        desired_keys: set[str] = set()
        for h in self._handles:
            if h.service == service and h.keys:
                desired_keys.update(h.keys.split(","))

        state = self._wire.get(service)
        if state is None:
            return

        if not any(h.service == service for h in self._handles):
            log.debug("No remaining handles for %s. Sending UNSUBS.", service)
            # No handles left for this service.
            self._enqueue_command(service, "UNSUBS")
            del self._wire[service]
            return

        # UNSUBS keys that are no longer needed.
        removed_keys = state.keys - desired_keys
        if removed_keys:
            log.debug("Existing subscription for %s. Removing keys %s.", service, removed_keys)
            self._enqueue_command(
                service, "UNSUBS", {"keys": ",".join(removed_keys)},
            )
            state.keys -= removed_keys

    def _resubscribe(self) -> None:
        """Re-enqueue subscriptions for all active handles after reconnect."""
        for handle in self._handles:
            self._sync_subscribe(handle.service, handle.keys, handle.fields)

    def _ensure_supervisor(self) -> None:
        """Start the supervisor task if it isn't running."""
        if self._supervisor_task is None or self._supervisor_task.done():
            self._supervisor_task = asyncio.create_task(self._supervisor())

    async def _stop_supervisor(self) -> None:
        """Cancel the supervisor and wait for it to finish."""
        if self._supervisor_task is not None:
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass
            self._supervisor_task = None

    async def _supervisor(self) -> None:
        """
        Long-lived task that owns the connection lifecycle.

        Connects (with retries), starts RX and TX tasks, logs in,
        re-subscribes, then waits for either RX or TX to exit.
        Cleans up and loops back to reconnect as long as there are
        active subscriptions.
        """
        while self._handles:
            ws: aiohttp.ClientWebSocketResponse | None = None

            try:
                ws = await self._connect()
                rx_task = asyncio.create_task(self._rx_loop(ws))

                tx_task: asyncio.Task | None = None

                try:
                    await self._login(ws)
                    self._resubscribe()
                    tx_task = asyncio.create_task(self._tx_loop(ws))

                    await asyncio.wait([rx_task, tx_task], return_when=asyncio.FIRST_COMPLETED)

                finally:
                    tasks = [rx_task]
                    if tx_task is not None:
                        tasks.append(tx_task)

                    for task in tasks:
                        task.cancel()

                    for task in tasks:
                        try:
                            await task

                        except asyncio.CancelledError:
                            pass

                        except Exception:
                            log.exception("Error in RX/TX task")

            except asyncio.CancelledError:
                raise

            except Exception:
                log.exception("Supervisor error.")

            finally:
                self._fail_pending("Connection lost")

                if ws is not None:
                    await ws.close()

    async def _connect(self) -> aiohttp.ClientWebSocketResponse:
        """Open a WebSocket connection, retrying with backoff on failure."""
        delay = 1
        max_delay = 30

        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    ws = await session.ws_connect(self._url, heartbeat=30)
                    session.detach()
                    return ws

                except IOError:
                    log.warning("Connect failed, retrying in %ds.", delay)

                except Exception:
                    log.exception("Unexpected error during connect, retrying in %ds.", delay)

                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    async def _tx_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Drain the command queue and send messages over the WebSocket."""
        while True:
            cmd = await self._tx_queue.get()
            await self._send_command(ws, cmd)

    async def _rx_loop(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Read messages from the WebSocket and dispatch them."""
        async for msg in ws:

            if msg.type == aiohttp.WSMsgType.TEXT:
                self._dispatch(json.loads(msg.data))

            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                log.debug("WebSocket closed with type %s.", msg.type)
                break

    def _make_command(self, service: str, command: str, parameters: dict[str, str] | None = None) -> _Command:
        """Create a command and register its pending future."""
        request_id = str(self._request_id)
        self._request_id += 1

        fut: asyncio.Future[dict] = asyncio.Future()
        self._pending[request_id] = fut

        return _Command(
            request_id=request_id, service=service, command=command,
            parameters=parameters or {}, future=fut,
        )

    def _enqueue_command(
        self, service: str, command: str, parameters: dict[str, str] | None = None,
    ) -> asyncio.Future[dict]:
        """Create and enqueue a command, returning its response future."""
        cmd = self._make_command(service, command, parameters)
        self._tx_queue.put_nowait(cmd)
        return cmd.future

    async def _send_command(self, ws: aiohttp.ClientWebSocketResponse, cmd: _Command) -> None:
        """Send a command directly on the WebSocket."""
        msg = {
            "requests": [{
                "requestid": cmd.request_id,
                "service": cmd.service,
                "command": cmd.command,
                "SchwabClientCustomerId": self._customer_id,
                "SchwabClientCorrelId": self._correl_id,
                "parameters": cmd.parameters,
            }],
        }
        log.debug("Sending message % r", msg)
        await ws.send_json(msg)

    def _enqueue_add(self, service: str, keys: str | None, fields: tuple[int, ...]) -> asyncio.Future[dict]:
        """Enqueue an ADD command for a service."""
        params: dict[str, str] = {"fields": ",".join(str(f) for f in fields)}
        if keys is not None:
            params["keys"] = keys
        return self._enqueue_command(service, "ADD", params)

    def _enqueue_view(self, service: str, fields: set[int]) -> asyncio.Future[dict]:
        """Enqueue a VIEW command to update fields for a service."""
        return self._enqueue_command(service, "VIEW", {"fields": ",".join(str(f) for f in sorted(fields))})

    async def _login(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Send the LOGIN command and await the response."""
        access_token = await self._auth.get_access_token()
        cmd = self._make_command("ADMIN", "LOGIN", {
            "Authorization": access_token,
            "SchwabClientChannel": self._channel,
            "SchwabClientFunctionId": self._function_id,
        })
        await self._send_command(ws, cmd)

        resp = await cmd.future
        code = resp.get("content", {}).get("code")
        if code != 0:
            msg = resp.get("content", {}).get("msg", "Unknown error")
            raise StreamError(f"Login failed (code {code}): {msg}")

        log.info("Streaming client logged in.")

    def _fail_pending(self, reason: str) -> None:
        """Fail all pending command futures and reset wire state."""
        self._wire.clear()

        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(StreamError(reason))
        self._pending.clear()

        while not self._tx_queue.empty():
            try:
                self._tx_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _dispatch(self, message: dict) -> None:
        """Route an incoming message to the appropriate handler."""
        if "response" in message:
            for resp in message["response"]:
                self._on_response(resp)
        if "notify" in message:
            for note in message["notify"]:
                self._on_notify(note)
        if "data" in message:
            for data in message["data"]:
                self._on_data(data)

    def _on_response(self, resp: dict[str, Any]) -> None:
        """Resolve a pending command future."""
        request_id: str = resp.get("requestid", "")
        fut = self._pending.pop(request_id, None)
        if fut is not None and not fut.done():
            fut.set_result(resp)

    def _on_notify(self, note: dict) -> None:
        """Handle a heartbeat notification."""
        if "heartbeat" in note:
            log.debug("Heartbeat: %s", note["heartbeat"])

    def _on_data(self, data: dict) -> None:
        """Fan out data messages to all subscribers for the service, one event per content item."""
        service = data.get("service")
        if service is None:
            log.error("Received data message without service: %s", data)
            return

        try:
            field_type = StreamService(service).field_type
        except ValueError:
            field_type = None

        timestamp = data.get("timestamp")

        for item in data.get("content", []):
            event = self._transform_item(item, service, timestamp, field_type)

            for handle in self._handles:
                if handle.service == service:
                    try:
                        result = handle.callback(event)
                    except Exception:
                        log.exception("Error in stream callback for %s.", service)
                    else:
                        if asyncio.iscoroutine(result):
                            asyncio.create_task(result)

    @staticmethod
    def _transform_item(item: dict, service: str, timestamp: int | None, field_type: type[StreamField] | None) -> dict:
        """Transform a single content item into a flat event with named fields."""
        ts = datetime.fromtimestamp(timestamp / 1000, tz=_EASTERN) if timestamp else None
        event: dict[str, Any] = {"service": service, "timestamp": ts}
        fields: dict[str, Any] = {}

        for k, v in item.items():
            if k.isdigit() and field_type is not None:
                try:
                    fields[field_type.from_number(int(k)).value] = v
                except (KeyError, ValueError):
                    fields[k] = v
            elif k.isdigit():
                fields[k] = v
            else:
                event[k] = v

        # Parse JSON-in-string for ACCT_ACTIVITY message_data.
        msg_data = fields.get("message_data")
        if isinstance(msg_data, str) and msg_data.startswith("{"):
            try:
                fields["message_data"] = json.loads(msg_data)
            except (json.JSONDecodeError, ValueError):
                pass

        event["fields"] = fields
        return event
