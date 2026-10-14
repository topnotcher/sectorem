"""Tests for the order builder."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest

from sectorem.errors import OrderNotFilledError, StreamError
from sectorem.trader.constants import OptionRight, OrderStatus
from sectorem.trader.order import Duration, OrderBuilder, OrderHandle, Session, Side
from sectorem.trader.types import Option


def make_builder() -> OrderBuilder:
    """An OrderBuilder backed by a mock account."""
    account = AsyncMock()
    return OrderBuilder(account)


CALL = Option("AAPL", 200.0, OptionRight.CALL, date(2026, 6, 19))


class TestBuildMarket:
    def test_equity_market(self):
        payload = make_builder().leg("AAPL", Side.BUY, 100).market().build()

        assert payload == {
            "orderType": "MARKET",
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": "BUY",
                "quantity": 100,
                "instrument": {"assetType": "EQUITY", "symbol": "AAPL"},
            }],
        }

    def test_market_has_no_price(self):
        payload = make_builder().leg("AAPL", Side.BUY, 100).market().build()
        assert "price" not in payload
        assert "stopPrice" not in payload


class TestBuildLimit:
    def test_equity_limit(self):
        payload = make_builder().leg("AAPL", Side.BUY, 100).limit(150.00).build()

        assert payload["orderType"] == "LIMIT"
        assert payload["price"] == "150.00"

    def test_sub_dollar_price_gets_four_decimals(self):
        payload = make_builder().leg("AAPL", Side.BUY, 100).limit(0.05).build()
        assert payload["price"] == "0.0500"

    def test_dollar_price_gets_two_decimals(self):
        payload = make_builder().leg("AAPL", Side.BUY, 100).limit(1.5).build()
        assert payload["price"] == "1.50"


class TestBuildStop:
    def test_stop(self):
        payload = make_builder().leg("AAPL", Side.SELL, 100).stop(140.00).build()

        assert payload["orderType"] == "STOP"
        assert payload["stopPrice"] == "140.00"
        assert "price" not in payload

    def test_stop_limit(self):
        payload = make_builder().leg("AAPL", Side.SELL, 100).stop_limit(139.50, 140.00).build()

        assert payload["orderType"] == "STOP_LIMIT"
        assert payload["price"] == "139.50"
        assert payload["stopPrice"] == "140.00"


class TestBuildOptions:
    def test_option_leg_uses_occ_symbol(self):
        payload = make_builder().leg(CALL, Side.BUY_TO_OPEN, 1).limit(3.50).build()

        instrument = payload["orderLegCollection"][0]["instrument"]
        assert instrument["assetType"] == "OPTION"
        assert instrument["symbol"] == CALL.occ_symbol

    def test_net_debit_spread(self):
        long_call = Option("AAPL", 200.0, OptionRight.CALL, date(2026, 6, 19))
        short_call = Option("AAPL", 210.0, OptionRight.CALL, date(2026, 6, 19))

        payload = (
            make_builder()
            .leg(long_call, Side.BUY_TO_OPEN, 1)
            .leg(short_call, Side.SELL_TO_OPEN, 1)
            .net_debit(1.50)
            .build()
        )

        assert payload["orderType"] == "NET_DEBIT"
        assert payload["price"] == "1.50"
        assert len(payload["orderLegCollection"]) == 2
        assert payload["orderLegCollection"][0]["instruction"] == "BUY_TO_OPEN"
        assert payload["orderLegCollection"][1]["instruction"] == "SELL_TO_OPEN"

    def test_net_credit(self):
        payload = make_builder().leg(CALL, Side.SELL_TO_OPEN, 1).net_credit(2.25).build()
        assert payload["orderType"] == "NET_CREDIT"
        assert payload["price"] == "2.25"


class TestSessionAndDuration:
    def test_defaults(self):
        payload = make_builder().leg("AAPL", Side.BUY, 100).market().build()
        assert payload["session"] == "NORMAL"
        assert payload["duration"] == "DAY"

    def test_overrides(self):
        payload = (
            make_builder()
            .leg("AAPL", Side.BUY, 100)
            .limit(150.00)
            .session(Session.PM)
            .duration(Duration.GTC)
            .build()
        )
        assert payload["session"] == "PM"
        assert payload["duration"] == "GOOD_TILL_CANCEL"


class TestBuildValidation:
    def test_no_order_type_raises(self):
        with pytest.raises(ValueError, match="Order type is required"):
            make_builder().leg("AAPL", Side.BUY, 100).build()

    def test_no_legs_raises(self):
        with pytest.raises(ValueError, match="At least one leg is required"):
            make_builder().market().build()

    def test_market_with_price_raises(self):
        builder = make_builder().leg("AAPL", Side.BUY, 100).limit(150.00).market()
        with pytest.raises(ValueError, match="Market orders cannot have a price"):
            builder.build()


class TestChaining:
    def test_methods_return_self(self):
        builder = make_builder()
        assert builder.leg("AAPL", Side.BUY, 100) is builder
        assert builder.market() is builder
        assert builder.session(Session.NORMAL) is builder
        assert builder.duration(Duration.DAY) is builder


class TestSubmitAndPreview:
    @pytest.mark.asyncio
    async def test_submit_passes_payload_to_account(self):
        account = AsyncMock()
        handle = OrderHandle(account, 42)
        account._submit_order.return_value = handle

        builder = OrderBuilder(account).leg("AAPL", Side.BUY, 100).limit(150.00)
        result = await builder.submit()

        assert result is handle
        account._submit_order.assert_awaited_once_with(builder.build())

    @pytest.mark.asyncio
    async def test_preview_passes_payload_to_account(self):
        account = AsyncMock()
        account._preview_order.return_value = {"price": "150.00"}

        builder = OrderBuilder(account).leg("AAPL", Side.BUY, 100).limit(150.00)
        result = await builder.preview()

        assert result == {"price": "150.00"}
        account._preview_order.assert_awaited_once_with(builder.build())

    @pytest.mark.asyncio
    async def test_submit_with_replaces_calls_replace(self):
        account = AsyncMock()
        new_handle = OrderHandle(account, 43)
        account._replace_order.return_value = new_handle

        builder = OrderBuilder(account, replaces=42).leg("AAPL", Side.BUY, 100).limit(151.00)
        result = await builder.submit()

        assert result is new_handle
        account._replace_order.assert_awaited_once_with(42, builder.build())
        account._submit_order.assert_not_awaited()


class TestReplace:
    def test_replace_builder_is_bound_to_order(self):
        account = AsyncMock()
        account._order_builder = Mock(
            side_effect=lambda symbol, side, quantity, *, replaces: (
                OrderBuilder(account, replaces=replaces).leg(symbol, side, quantity)
            ),
        )

        builder = OrderHandle(account, 42).replace("AAPL", Side.BUY, 100)

        assert builder._replaces == 42
        assert builder.limit(151.00).build()["orderLegCollection"][0]["instrument"]["symbol"] == "AAPL"


class FakeSubscription:
    def __init__(self, stream: FakeStream) -> None:
        self._stream = stream

    async def cancel(self) -> None:
        self._stream.cancelled = True


class FakeStream:
    """Stand-in for StreamClient that captures the ACCT_ACTIVITY callback."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.callback = None
        self.cancelled = False
        self.subscribe_args: tuple | None = None

    async def subscribe(self, service, callback, *, keys=None, fields=(), timeout=60):
        if self.fail:
            raise StreamError("subscription failed")
        self.callback = callback
        self.subscribe_args = (service, keys, tuple(fields))
        return FakeSubscription(self)


def make_wait_handle(statuses: list[str], stream: FakeStream | None = None) -> tuple[OrderHandle, AsyncMock]:
    """An OrderHandle whose account returns the given order statuses in sequence."""
    account = AsyncMock()
    account._stream = stream
    account._get_order.side_effect = [{"orderId": 42, "status": s} for s in statuses]
    return OrderHandle(account, 42), account


def activity_event(order_id: int | str) -> dict:
    return {
        "service": "ACCT_ACTIVITY",
        "fields": {
            "message_type": "OrderFillCompleted",
            "message_data": {"SchwabOrderID": str(order_id)},
        },
    }


async def wait_until(predicate, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.001)


class TestWaitPolling:
    @pytest.mark.asyncio
    async def test_returns_final_order_on_fill(self):
        handle, account = make_wait_handle(["WORKING", "FILLED"])

        order = await handle.wait(poll_interval=0.001)

        assert order["status"] == "FILLED"
        assert account._get_order.await_count == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["CANCELED", "REJECTED", "EXPIRED", "REPLACED"])
    async def test_raises_on_terminal_non_fill(self, status):
        handle, _ = make_wait_handle([status])

        with pytest.raises(OrderNotFilledError) as exc_info:
            await handle.wait(poll_interval=0.001)

        assert exc_info.value.order_id == 42
        assert exc_info.value.status is OrderStatus(status)
        assert exc_info.value.order["status"] == status

    @pytest.mark.asyncio
    async def test_timeout_raises(self):
        account = AsyncMock()
        account._stream = None
        account._get_order.side_effect = None
        account._get_order.return_value = {"orderId": 42, "status": "WORKING"}
        handle = OrderHandle(account, 42)

        with pytest.raises(TimeoutError):
            await handle.wait(timeout=0.05, poll_interval=0.01)

    @pytest.mark.asyncio
    async def test_unknown_status_raises(self):
        handle, _ = make_wait_handle(["SOME_FUTURE_STATUS"])

        with pytest.raises(OrderNotFilledError) as exc_info:
            await handle.wait(poll_interval=0.001)

        assert exc_info.value.status is OrderStatus.UNKNOWN


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_returns_enum(self):
        handle, _ = make_wait_handle(["WORKING"])
        assert await handle.status() is OrderStatus.WORKING

    @pytest.mark.asyncio
    async def test_unrecognized_status_is_unknown(self):
        handle, _ = make_wait_handle(["SOME_FUTURE_STATUS"])
        assert await handle.status() is OrderStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_fetch_returns_raw_order(self):
        handle, _ = make_wait_handle(["WORKING"])
        assert await handle.fetch() == {"orderId": 42, "status": "WORKING"}


class TestWaitStream:
    @pytest.mark.asyncio
    async def test_event_triggers_immediate_poll(self):
        stream = FakeStream()
        # Default stream poll interval is 30s, so completion requires the nudge.
        handle, account = make_wait_handle(["WORKING", "FILLED"], stream=stream)

        task = asyncio.create_task(handle.wait())
        await wait_until(lambda: account._get_order.await_count == 1)
        stream.callback(activity_event(42))

        order = await asyncio.wait_for(task, timeout=1)
        assert order["status"] == "FILLED"
        assert stream.cancelled

    @pytest.mark.asyncio
    async def test_event_for_other_order_is_ignored(self):
        stream = FakeStream()
        handle, account = make_wait_handle(["WORKING", "FILLED"], stream=stream)

        task = asyncio.create_task(handle.wait())
        await wait_until(lambda: account._get_order.await_count == 1)
        stream.callback(activity_event(999))
        await asyncio.sleep(0.05)
        assert account._get_order.await_count == 1

        stream.callback(activity_event(42))
        order = await asyncio.wait_for(task, timeout=1)
        assert order["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_unparseable_event_still_wakes(self):
        stream = FakeStream()
        handle, account = make_wait_handle(["WORKING", "FILLED"], stream=stream)

        task = asyncio.create_task(handle.wait())
        await wait_until(lambda: account._get_order.await_count == 1)
        stream.callback({"service": "ACCT_ACTIVITY", "fields": {"message_data": "unparsed"}})

        order = await asyncio.wait_for(task, timeout=1)
        assert order["status"] == "FILLED"

    @pytest.mark.asyncio
    async def test_subscribes_to_acct_activity(self):
        stream = FakeStream()
        handle, _ = make_wait_handle(["FILLED"], stream=stream)

        await handle.wait()

        assert stream.subscribe_args is not None
        assert stream.subscribe_args[0] == "ACCT_ACTIVITY"

    @pytest.mark.asyncio
    async def test_subscription_cancelled_on_error(self):
        stream = FakeStream()
        handle, _ = make_wait_handle(["REJECTED"], stream=stream)

        with pytest.raises(OrderNotFilledError):
            await handle.wait()

        assert stream.cancelled

    @pytest.mark.asyncio
    async def test_subscribe_failure_falls_back_to_polling(self):
        stream = FakeStream(fail=True)
        handle, account = make_wait_handle(["WORKING", "FILLED"], stream=stream)

        order = await handle.wait(poll_interval=0.001)

        assert order["status"] == "FILLED"
        assert account._get_order.await_count == 2
