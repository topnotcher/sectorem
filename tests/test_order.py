"""Tests for the order builder."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from sectorem.trader.constants import OptionRight
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
