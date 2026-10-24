"""Order construction for the Schwab Trader API."""

from __future__ import annotations

import asyncio
import enum
import logging
from typing import TYPE_CHECKING, Any

from ..errors import ApiError, OrderNotFilledError, OrderTimeoutError, StreamError
from ..stream.fields import AccountActivityField, StreamService
from .constants import AssetType, OrderStatus
from .parse import parse_order_result
from .types import Option, OrderPreview, OrderResult

if TYPE_CHECKING:
    from ..stream import Subscription
    from .client import Account

log = logging.getLogger(__name__)

#: Default polling interval for :meth:`OrderHandle.wait` when no stream is available.
POLL_INTERVAL = 2.0

#: Fallback polling interval when ``ACCT_ACTIVITY`` events provide the primary wake-up.
STREAM_POLL_INTERVAL = 30.0

# Schwab requires a key for ACCT_ACTIVITY but ignores its value.
_ACCT_ACTIVITY_KEY = "Account Activity"


class OrderType(enum.Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TRAILING_STOP = "TRAILING_STOP"
    NET_DEBIT = "NET_DEBIT"
    NET_CREDIT = "NET_CREDIT"
    NET_ZERO = "NET_ZERO"


class Session(enum.Enum):
    """Wire value for the order's ``session`` field. See :class:`TimeInForce`."""
    NORMAL = "NORMAL"
    AM = "AM"
    PM = "PM"
    SEAMLESS = "SEAMLESS"


class Duration(enum.Enum):
    """Wire value for the order's ``duration`` field. See :class:`TimeInForce`."""
    DAY = "DAY"
    GTC = "GOOD_TILL_CANCEL"


class TimeInForce(enum.Enum):
    """
    Time in force, using the familiar broker vocabulary.

    Schwab's API splits this into ``session`` and ``duration`` fields, but
    the two are not independent in practice and the meaningful combinations
    are exactly the usual TIF values. Each member carries the pair it maps to.
    """
    #: Regular session, good for the day.
    DAY = (Session.NORMAL, Duration.DAY)
    #: Regular session, good till cancelled.
    GTC = (Session.NORMAL, Duration.GTC)
    #: Pre-market, regular, and after-hours sessions, good for the day.
    EXT = (Session.SEAMLESS, Duration.DAY)
    #: Pre-market, regular, and after-hours sessions, good till cancelled.
    GTC_EXT = (Session.SEAMLESS, Duration.GTC)
    #: Pre-market session only.
    AM = (Session.AM, Duration.DAY)
    #: After-hours session only.
    PM = (Session.PM, Duration.DAY)

    @property
    def session(self) -> Session:
        return self.value[0]

    @property
    def duration(self) -> Duration:
        return self.value[1]


class Side(enum.Enum):
    """Order instruction / side."""
    BUY = "BUY"
    SELL = "SELL"
    BUY_TO_COVER = "BUY_TO_COVER"
    SELL_SHORT = "SELL_SHORT"
    BUY_TO_OPEN = "BUY_TO_OPEN"
    BUY_TO_CLOSE = "BUY_TO_CLOSE"
    SELL_TO_OPEN = "SELL_TO_OPEN"
    SELL_TO_CLOSE = "SELL_TO_CLOSE"


class OrderBuilder:
    """
    Builder for Schwab order requests.

    Created via :meth:`~sectorem.trader.client.Account.order` or
    :meth:`OrderHandle.replace`. Use the chaining methods to configure the
    order, then call :meth:`submit` to place it or :meth:`preview` to dry-run it.

    Example::

        await account.order("AAPL", Side.BUY, 100).limit(150.00).submit()

    :param account: The account to submit to.
    :param replaces: Order ID this order replaces, if any. When set,
        :meth:`submit` replaces that order instead of placing a new one.
    """

    def __init__(self, account: Account, replaces: int | None = None) -> None:
        self._account = account
        self._replaces = replaces
        self._order_type: OrderType | None = None
        self._tif: TimeInForce = TimeInForce.DAY
        self._price: str | None = None
        self._stop_price: str | None = None
        self._legs: list[dict[str, Any]] = []

    def leg(self, symbol: str | Option, side: Side, quantity: int) -> OrderBuilder:
        """Add a leg to the order."""
        self._legs.append({
            "instruction": side.value,
            "quantity": quantity,
            "instrument": _build_instrument(symbol),
        })
        return self

    def market(self) -> OrderBuilder:
        """Set order type to market."""
        self._order_type = OrderType.MARKET
        return self

    def limit(self, price: float) -> OrderBuilder:
        """Set order type to limit with the given price."""
        self._order_type = OrderType.LIMIT
        self._price = _format_price(price)
        return self

    def stop(self, stop_price: float) -> OrderBuilder:
        """Set order type to stop with the given trigger price."""
        self._order_type = OrderType.STOP
        self._stop_price = _format_price(stop_price)
        return self

    def stop_limit(self, price: float, stop_price: float) -> OrderBuilder:
        """Set order type to stop-limit."""
        self._order_type = OrderType.STOP_LIMIT
        self._price = _format_price(price)
        self._stop_price = _format_price(stop_price)
        return self

    def net_debit(self, price: float) -> OrderBuilder:
        """Set order type to net debit with the given price."""
        self._order_type = OrderType.NET_DEBIT
        self._price = _format_price(price)
        return self

    def net_credit(self, price: float) -> OrderBuilder:
        """Set order type to net credit with the given price."""
        self._order_type = OrderType.NET_CREDIT
        self._price = _format_price(price)
        return self

    def tif(self, tif: TimeInForce) -> OrderBuilder:
        """Set the time in force. Defaults to :attr:`TimeInForce.DAY`."""
        self._tif = tif
        return self

    def build(self) -> dict[str, Any]:
        """
        Build the order payload dict.

        :raises ValueError: If required fields are missing or inconsistent.
        """
        if self._order_type is None:
            raise ValueError("Order type is required")
        if not self._legs:
            raise ValueError("At least one leg is required")

        if self._order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and self._price is None:
            raise ValueError(f"{self._order_type.value} orders require a price")
        if self._order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and self._stop_price is None:
            raise ValueError(f"{self._order_type.value} orders require a stop price")
        if self._order_type == OrderType.MARKET and self._price is not None:
            raise ValueError("Market orders cannot have a price")

        payload: dict[str, Any] = {
            "orderType": self._order_type.value,
            "session": self._tif.session.value,
            "duration": self._tif.duration.value,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": self._legs,
        }

        if self._price is not None:
            payload["price"] = self._price
        if self._stop_price is not None:
            payload["stopPrice"] = self._stop_price

        return payload

    async def submit(self) -> OrderHandle:
        """
        Build and submit the order, returning a handle to track it.

        For a replacement order, the handle is for the new order; the
        replaced order's handle will report status ``REPLACED``.
        """
        payload = self.build()
        if self._replaces is None:
            return await self._account._submit_order(payload)
        return await self._account._replace_order(self._replaces, payload)

    async def preview(self) -> OrderPreview:
        """Build and preview the order without placing it."""
        payload = self.build()
        return await self._account._preview_order(payload)


class OrderHandle:
    """
    A handle to a submitted order.

    Returned by :meth:`OrderBuilder.submit`. Use it to check on, wait for,
    replace, or cancel the order. The typical pattern::

        try:
            result = await handle.wait(timeout=30)
        except OrderTimeoutError:
            result = await handle.cancel()   # final: CANCELED (maybe partially filled) or FILLED
        except OrderNotFilledError as e:
            result = e.result                # final: canceled, rejected, expired, ...
        print(result.filled_quantity, result.average_price)
    """

    def __init__(self, account: Account, order_id: int) -> None:
        #: The Schwab order ID.
        self.order_id: int = order_id
        self._account = account

    def __repr__(self) -> str:
        return f"OrderHandle(order_id={self.order_id!r})"

    async def fetch(self) -> dict:
        """Fetch the raw order record from the API. Prefer :meth:`result`."""
        return await self._account._get_order(self.order_id)

    async def result(self) -> OrderResult:
        """Fetch the order's current state from the API."""
        return parse_order_result(await self.fetch())

    async def status(self) -> OrderStatus:
        """Fetch the current order status from the API."""
        return (await self.result()).status

    async def cancel(self, *, timeout: float | None = None, poll_interval: float | None = None) -> OrderResult:
        """
        Cancel the order and wait for it to settle.

        Sends the cancel request, then waits for the order to reach a terminal
        state. Shares can fill between the request and Schwab acting on it, and
        an order that has already finished cannot be canceled at all, so the
        returned result is the authoritative account of what filled: status
        ``CANCELED`` with any partial fills recorded, or ``FILLED`` if the
        order completed first. Canceling an order that is already terminal
        simply returns its result.

        :param timeout: Maximum seconds to wait for the cancel to settle, or
            ``None`` to wait indefinitely.
        :param poll_interval: Seconds between status polls; see :meth:`wait`.
        :raises OrderTimeoutError: If *timeout* elapses before the order settles.
        """
        try:
            await self._account._cancel_order(self.order_id)
        except ApiError as e:
            # Schwab answers 400 "Order in state FILLED cannot be canceled" for a
            # filled order (an already-canceled one is silently re-accepted). If
            # the order is indeed done, its result is the answer; otherwise the
            # error is genuine.
            if e.status != 400:
                raise
            result = await self.result()
            if not result.status.is_terminal:
                raise
            return result

        return await self._wait_terminal(timeout, poll_interval)

    def replace(
        self, symbol: str | Option | None = None, side: Side | None = None, quantity: int | None = None,
    ) -> OrderBuilder:
        """
        Create an :class:`OrderBuilder` that replaces this order.

        Schwab replaces by cancelling this order and creating a new one,
        so the full order must be specified again. Arguments mirror
        :meth:`~sectorem.trader.client.Account.order`::

            new_handle = await handle.replace("AAPL", Side.BUY, 100).limit(151.00).submit()
        """
        return self._account._order_builder(symbol, side, quantity, replaces=self.order_id)

    async def wait(self, *, timeout: float | None = None, poll_interval: float | None = None) -> OrderResult:
        """
        Wait for the order to fill completely.

        The order status is polled until it reaches a terminal state. When the
        trader client has a streaming client attached, ``ACCT_ACTIVITY`` events
        for this order trigger an immediate status check and polling drops to a
        slow fallback (:data:`STREAM_POLL_INTERVAL`); without one, the order is
        polled every :data:`POLL_INTERVAL` seconds. The REST status is always
        the source of truth — stream events only accelerate the next check, so
        orders that don't stream (e.g. EXTO) still resolve via polling.

        Partial fills do not end the wait; Schwab keeps a partially filled
        order ``WORKING``. They are reported through ``filled_quantity`` on the
        result carried by either exception.

        :param timeout: Maximum seconds to wait, or ``None`` to wait indefinitely.
        :param poll_interval: Seconds between status polls. Defaults as described above.
        :return: The order's final state, with status ``FILLED``.
        :raises OrderNotFilledError: If the order reaches a terminal state other
            than filled (canceled, rejected, expired, replaced, or unknown).
            The result it carries is final.
        :raises OrderTimeoutError: If *timeout* elapses first. The order is left
            working; the result it carries is a snapshot, and :meth:`cancel`
            returns the final word.
        """
        result = await self._wait_terminal(timeout, poll_interval)
        if result.status is not OrderStatus.FILLED:
            raise OrderNotFilledError(result)
        return result

    async def _wait_terminal(self, timeout: float | None, poll_interval: float | None) -> OrderResult:
        """Poll (nudged by stream events) until the order reaches any terminal state."""
        nudge = asyncio.Event()
        subscription = await self._subscribe_activity(nudge)

        if poll_interval is None:
            poll_interval = POLL_INTERVAL if subscription is None else STREAM_POLL_INTERVAL

        result: OrderResult | None = None
        try:
            try:
                async with asyncio.timeout(timeout):
                    while True:
                        # Clear before polling so events that race the poll are retained.
                        nudge.clear()
                        result = await self.result()
                        if result.status.is_terminal:
                            return result

                        try:
                            await asyncio.wait_for(nudge.wait(), timeout=poll_interval)
                        except TimeoutError:
                            pass
            except TimeoutError:
                if timeout is None:
                    raise  # Not ours: asyncio.timeout(None) never expires.
                if result is None:
                    result = await self.result()
                raise OrderTimeoutError(result, timeout) from None
        finally:
            if subscription is not None:
                await subscription.cancel()

    async def _subscribe_activity(self, nudge: asyncio.Event) -> Subscription | None:
        """
        Subscribe to ``ACCT_ACTIVITY`` events for this order, setting *nudge*
        on each one. Returns ``None`` (leaving :meth:`wait` on pure polling)
        when no stream is available or the subscription fails.
        """
        stream = self._account._stream
        if stream is None:
            return None

        def callback(event: dict) -> None:
            data = event.get("fields", {}).get("message_data")
            if isinstance(data, dict):
                order_id = data.get("SchwabOrderID")
                # Only ignore events positively identified as another order's;
                # anything unrecognizable just costs an extra poll.
                if order_id is not None and str(order_id) != str(self.order_id):
                    return
            nudge.set()

        try:
            return await stream.subscribe(
                StreamService.ACCT_ACTIVITY,
                callback,
                keys=_ACCT_ACTIVITY_KEY,
                fields=(AccountActivityField.MESSAGE_TYPE, AccountActivityField.MESSAGE_DATA),
            )
        except (StreamError, TimeoutError):
            log.warning("ACCT_ACTIVITY subscription failed; falling back to polling.", exc_info=True)
            return None


def _format_price(price: float) -> str:
    """Format a price as a string with appropriate precision."""
    if price < 1.0:
        return f"{price:.4f}"
    return f"{price:.2f}"


def _build_instrument(symbol: str | Option) -> dict[str, Any]:
    """Build an instrument dict for an order leg."""
    if isinstance(symbol, Option):
        return {
            "assetType": AssetType.OPTION.value,
            "symbol": symbol.occ_symbol,
        }

    return {
        "assetType": AssetType.EQUITY.value,
        "symbol": symbol,
    }
