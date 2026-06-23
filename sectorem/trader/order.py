"""Order construction for the Schwab Trader API."""

from __future__ import annotations

import enum
from typing import TYPE_CHECKING, Any

from .constants import AssetType
from .types import Option

if TYPE_CHECKING:
    from .client import Account


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
    """Trading session."""
    NORMAL = "NORMAL"
    AM = "AM"
    PM = "PM"
    SEAMLESS = "SEAMLESS"


class Duration(enum.Enum):
    """Time in force."""
    DAY = "DAY"
    GTC = "GOOD_TILL_CANCEL"
    FILL_OR_KILL = "FILL_OR_KILL"


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

    Created via :meth:`~sectorem.trader.client.Account.order`. Use the
    chaining methods to configure the order, then call :meth:`submit`
    to place it or :meth:`preview` to dry-run it.

    Example::

        await account.order("AAPL", Side.BUY, 100).limit(150.00).submit()
    """

    def __init__(self, account: Account) -> None:
        self._account = account
        self._order_type: OrderType | None = None
        self._session: Session = Session.NORMAL
        self._duration: Duration = Duration.DAY
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

    def session(self, session: Session) -> OrderBuilder:
        """Set the trading session."""
        self._session = session
        return self

    def duration(self, duration: Duration) -> OrderBuilder:
        """Set the time in force."""
        self._duration = duration
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
            "session": self._session.value,
            "duration": self._duration.value,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": self._legs,
        }

        if self._price is not None:
            payload["price"] = self._price
        if self._stop_price is not None:
            payload["stopPrice"] = self._stop_price

        return payload

    async def submit(self) -> OrderHandle:
        """Build and submit the order, returning a handle to track it."""
        payload = self.build()
        return await self._account._submit_order(payload)

    async def preview(self) -> dict:
        """Build and preview the order without placing it."""
        payload = self.build()
        return await self._account._preview_order(payload)


class OrderHandle:
    """
    A handle to a submitted order.

    Returned by :meth:`OrderBuilder.submit`. Use it to check status or
    cancel the order.
    """

    def __init__(self, account: Account, order_id: int) -> None:
        #: The Schwab order ID.
        self.order_id: int = order_id
        self._account = account

    def __repr__(self) -> str:
        return f"OrderHandle(order_id={self.order_id!r})"

    async def status(self) -> dict:
        """Fetch the current order status from the API."""
        return await self._account._get_order(self.order_id)

    async def cancel(self) -> None:
        """Cancel the order."""
        await self._account._cancel_order(self.order_id)


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
