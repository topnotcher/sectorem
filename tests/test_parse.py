"""Tests for position and instrument parsing."""

from __future__ import annotations

from datetime import date

import pytest

from sectorem.errors import InvalidApiResponseError
from sectorem.trader.constants import AccountType, AssetType, InstrumentType, OptionRight
from sectorem.trader.parse import (
    parse_balance,
    parse_initial_balance,
    parse_position,
    _parse_occ_symbol,
)
from sectorem.trader.types import (
    CashBalance,
    CashInitialBalance,
    CollectiveInvestmentPosition,
    EquityPosition,
    Instrument,
    MarginBalance,
    MarginInitialBalance,
    OptionInstrument,
    OptionPosition,
)


class TestParseOccSymbol:
    def test_put(self):
        strike, expiration = _parse_occ_symbol("SMCI  270115P00008000")
        assert strike == 8.0
        assert expiration == date(2027, 1, 15)

    def test_call(self):
        strike, expiration = _parse_occ_symbol("AMD   271217C00200000")
        assert strike == 200.0
        assert expiration == date(2027, 12, 17)

    def test_fractional_strike(self):
        strike, expiration = _parse_occ_symbol("CLSK  260618C00015500")
        assert strike == 15.5
        assert expiration == date(2026, 6, 18)

    def test_short_symbol(self):
        strike, expiration = _parse_occ_symbol("X     260120P00025000")
        assert strike == 25.0
        assert expiration == date(2026, 1, 20)


class TestParsePosition:
    def test_equity_long(self):
        raw = {
            "shortQuantity": 0.0,
            "longQuantity": 1000.0,
            "averagePrice": 50.64718,
            "currentDayProfitLoss": -210.0,
            "longOpenProfitLoss": -28087.18,
            "marketValue": 22560.0,
            "instrument": {
                "assetType": "EQUITY",
                "cusip": "86800U302",
                "symbol": "SMCI",
                "netChange": -0.21,
            },
        }
        pos = parse_position(raw)

        assert isinstance(pos, EquityPosition)
        assert pos.instrument.symbol == "SMCI"
        assert pos.instrument.asset_type == AssetType.EQUITY
        assert pos.instrument.description == "SMCI"
        assert pos.instrument.instrument_type is None
        assert pos.quantity == 1000.0
        assert pos.average_price == 50.64718
        assert pos.market_value == 22560.0
        assert pos.day_profit_loss == -210.0
        assert pos.open_profit_loss == -28087.18

    def test_option_short(self):
        raw = {
            "shortQuantity": 12.0,
            "longQuantity": 0.0,
            "averagePrice": 4.0533666667,
            "currentDayProfitLoss": -16.08,
            "shortOpenProfitLoss": 4540.04,
            "marketValue": -324.0,
            "instrument": {
                "assetType": "OPTION",
                "cusip": "0CLSK.FI60015000",
                "symbol": "CLSK  260618C00015000",
                "description": "CLEANSPARK INC 06/18/2026 $15 Call",
                "netChange": 0.0334,
                "type": "VANILLA",
                "putCall": "CALL",
                "underlyingSymbol": "CLSK",
            },
        }
        pos = parse_position(raw)

        assert isinstance(pos, OptionPosition)
        assert isinstance(pos.instrument, OptionInstrument)
        assert pos.instrument.symbol == "CLSK"
        assert pos.instrument.description == "CLEANSPARK INC 06/18/2026 $15 Call"
        assert pos.instrument.instrument_type == InstrumentType.VANILLA
        assert pos.instrument.strike == 15.0
        assert pos.instrument.right == OptionRight.CALL
        assert pos.instrument.expiration == date(2026, 6, 18)
        assert pos.instrument.multiplier == 100
        assert pos.quantity == -12.0
        assert pos.average_price == 4.0533666667

    def test_option_long(self):
        raw = {
            "shortQuantity": 0.0,
            "longQuantity": 20.0,
            "averagePrice": 1.38561,
            "currentDayProfitLoss": 69.0,
            "longOpenProfitLoss": -1071.22,
            "marketValue": 1700.0,
            "instrument": {
                "assetType": "OPTION",
                "cusip": "0SMCI.MF70008000",
                "symbol": "SMCI  270115P00008000",
                "description": "SUPER MICRO COMPUTER INC 01/15/2027 $8 Put",
                "netChange": -0.0255,
                "type": "VANILLA",
                "putCall": "PUT",
                "underlyingSymbol": "SMCI",
            },
        }
        pos = parse_position(raw)

        assert isinstance(pos, OptionPosition)
        assert pos.instrument.symbol == "SMCI"
        assert pos.instrument.strike == 8.0
        assert pos.instrument.right == OptionRight.PUT
        assert pos.instrument.expiration == date(2027, 1, 15)
        assert pos.quantity == 20.0

    def test_collective_investment(self):
        raw = {
            "shortQuantity": 0.0,
            "longQuantity": 100.0396,
            "averagePrice": 32.706,
            "currentDayProfitLoss": 41.917,
            "longOpenProfitLoss": -506.815,
            "marketValue": 2765.09,
            "instrument": {
                "assetType": "COLLECTIVE_INVESTMENT",
                "cusip": "77926X304",
                "symbol": "QDTE",
                "description": "ROUNDHL INVN 100 0DTE COV CL ETF",
                "type": "EXCHANGE_TRADED_FUND",
            },
        }
        pos = parse_position(raw)

        assert isinstance(pos, CollectiveInvestmentPosition)
        assert pos.instrument.symbol == "QDTE"
        assert pos.instrument.asset_type == AssetType.COLLECTIVE_INVESTMENT
        assert pos.instrument.description == "ROUNDHL INVN 100 0DTE COV CL ETF"
        assert pos.instrument.instrument_type == InstrumentType.EXCHANGE_TRADED_FUND
        assert pos.quantity == 100.0396

    def test_occ_symbol_roundtrip(self):
        raw = {
            "shortQuantity": 0.0,
            "longQuantity": 20.0,
            "averagePrice": 1.38561,
            "currentDayProfitLoss": 69.0,
            "longOpenProfitLoss": -1071.22,
            "marketValue": 1700.0,
            "instrument": {
                "assetType": "OPTION",
                "symbol": "SMCI  270115P00008000",
                "putCall": "PUT",
                "underlyingSymbol": "SMCI",
            },
        }
        pos = parse_position(raw)
        assert pos.instrument.occ_symbol == "SMCI  270115P00008000"

    def test_empty_positions(self):
        """Positions list is empty when no positions key exists."""
        raw = {
            "shortQuantity": 0.0,
            "longQuantity": 0.0,
            "averagePrice": 0.0,
            "currentDayProfitLoss": 0.0,
            "longOpenProfitLoss": 0.0,
            "marketValue": 0.0,
            "instrument": {
                "assetType": "EQUITY",
                "symbol": "GHOST",
            },
        }
        pos = parse_position(raw)
        assert pos.quantity == 0.0


# ---------------------------------------------------------------------------
# Margin balance fixtures (based on real API snapshots)
# ---------------------------------------------------------------------------

_MARGIN_CURRENT_RAW = {
    "accruedInterest": 0.0,
    "availableFunds": 85329.15,
    "availableFundsNonMarginableTrade": 84329.15,
    "bondValue": 0.0,
    "buyingPower": 255977.74,
    "buyingPowerNonMarginableTrade": 84328.15,
    "cashBalance": 2173.26,
    "cashReceipts": 1000.0,
    "dayTradingBuyingPower": 409413.0,
    "equity": 229198.23,
    "equityPercentage": 100.0,
    "liquidationValue": 170455.79,
    "longMarginValue": 227024.97,
    "longMarketValue": 230903.03,
    "longOptionMarketValue": 1600.0,
    "maintenanceCall": 0.0,
    "maintenanceRequirement": 143867.8,
    "marginBalance": 0.0,
    "moneyMarketFund": 0.0,
    "mutualFundValue": 0.0,
    "pendingDeposits": 1000.0,
    "regTCall": 0.0,
    "savings": 0.0,
    "shortBalance": 0.0,
    "shortMarginValue": 0.0,
    "shortMarketValue": 0.0,
    "shortOptionMarketValue": -64220.5,
    "sma": 127990.15,
}

_MARGIN_PROJECTED_RAW = {
    "availableFunds": 85328.15,
    "availableFundsNonMarginableTrade": 84328.15,
    "buyingPower": 255976.74,
    "dayTradingBuyingPower": 409413.0,
    "dayTradingBuyingPowerCall": 0.0,
    "isInCall": False,
    "maintenanceCall": 0.0,
    "regTCall": 0.0,
    "stockBuyingPower": 255976.74,
}

_MARGIN_INITIAL_RAW = {
    "accruedInterest": 0.0,
    "availableFundsNonMarginableTrade": 79365.0,
    "bondValue": 321458.0,
    "buyingPower": 256730.0,
    "cashAvailableForTrading": 0.0,
    "cashBalance": 2924.2,
    "cashReceipts": 1000.0,
    "dayTradingBuyingPower": 409413.0,
    "dayTradingBuyingPowerCall": 0.0,
    "dayTradingEquityCall": 0.0,
    "equity": 162511.9,
    "equityPercentage": 70.0,
    "isInCall": False,
    "liquidationValue": 162561.98,
    "longMarginValue": 220944.25,
    "longOptionMarketValue": 1800.0,
    "longStockValue": 220944.25,
    "maintenanceCall": 0.0,
    "maintenanceRequirement": 143504.0,
    "marginBalance": 0.0,
    "marginEquity": 223868.45,
    "moneyMarketFund": 0.0,
    "mutualFundValue": 80365.0,
    "pendingDeposits": 1000.0,
    "regTCall": 0.0,
    "shortBalance": 0.0,
    "shortMarginValue": 0.0,
    "shortOptionMarketValue": -65350.55,
    "shortStockValue": -65350.55,
    "totalCash": 0.0,
}


class TestParseMarginBalance:
    def test_parses_current_and_projected(self):
        bal = parse_balance(_MARGIN_CURRENT_RAW, _MARGIN_PROJECTED_RAW, AccountType.MARGIN)

        assert isinstance(bal, MarginBalance)
        # From current
        assert bal.buying_power == 255977.74
        assert bal.equity == 229198.23
        assert bal.liquidation_value == 170455.79
        assert bal.sma == 127990.15
        assert bal.margin_balance == 0.0
        assert bal.short_option_market_value == -64220.5
        # From projected
        assert bal.is_in_call is False
        assert bal.stock_buying_power == 255976.74
        assert bal.day_trading_buying_power_call == 0.0

    def test_extra_fields_ignored(self):
        current = {**_MARGIN_CURRENT_RAW, "someNewField": 42.0}
        projected = {**_MARGIN_PROJECTED_RAW, "anotherNewField": 99.0}
        bal = parse_balance(current, projected, AccountType.MARGIN)
        assert isinstance(bal, MarginBalance)

    def test_missing_current_field_raises(self):
        current = {k: v for k, v in _MARGIN_CURRENT_RAW.items() if k != "equity"}
        with pytest.raises(InvalidApiResponseError, match="equity"):
            parse_balance(current, _MARGIN_PROJECTED_RAW, AccountType.MARGIN)

    def test_missing_projected_field_raises(self):
        projected = {k: v for k, v in _MARGIN_PROJECTED_RAW.items() if k != "isInCall"}
        with pytest.raises(InvalidApiResponseError, match="isInCall"):
            parse_balance(_MARGIN_CURRENT_RAW, projected, AccountType.MARGIN)


class TestParseMarginInitialBalance:
    def test_parses(self):
        bal = parse_initial_balance(_MARGIN_INITIAL_RAW, AccountType.MARGIN)

        assert isinstance(bal, MarginInitialBalance)
        assert bal.liquidation_value == 162561.98
        assert bal.equity == 162511.9
        assert bal.buying_power == 256730.0
        assert bal.is_in_call is False
        assert bal.margin_equity == 223868.45
        assert bal.total_cash == 0.0

    def test_extra_fields_ignored(self):
        raw = {**_MARGIN_INITIAL_RAW, "accountValue": 162561.98, "margin": 2924.2}
        bal = parse_initial_balance(raw, AccountType.MARGIN)
        assert isinstance(bal, MarginInitialBalance)

    def test_missing_field_raises(self):
        raw = {k: v for k, v in _MARGIN_INITIAL_RAW.items() if k != "isInCall"}
        with pytest.raises(InvalidApiResponseError, match="isInCall"):
            parse_initial_balance(raw, AccountType.MARGIN)


class TestParseCashBalance:
    _CASH_CURRENT_RAW = {
        "cashAvailableForTrading": 5000.0,
        "cashAvailableForWithdrawal": 4000.0,
        "cashCall": 0.0,
        "cashDebitCallValue": 0.0,
        "longNonMarginableMarketValue": 3000.0,
        "totalCash": 5000.0,
        "unsettledCash": 1000.0,
    }

    def test_parses(self):
        bal = parse_balance(self._CASH_CURRENT_RAW, {}, AccountType.CASH)

        assert isinstance(bal, CashBalance)
        assert bal.cash_available_for_trading == 5000.0
        assert bal.total_cash == 5000.0
        assert bal.unsettled_cash == 1000.0

    def test_missing_field_raises(self):
        raw = {k: v for k, v in self._CASH_CURRENT_RAW.items() if k != "totalCash"}
        with pytest.raises(InvalidApiResponseError, match="totalCash"):
            parse_balance(raw, {}, AccountType.CASH)


class TestParseCashInitialBalance:
    _CASH_INITIAL_RAW = {
        "accruedInterest": 0.0,
        "bondValue": 0.0,
        "cashAvailableForTrading": 5000.0,
        "cashAvailableForWithdrawal": 4000.0,
        "cashBalance": 5000.0,
        "cashDebitCallValue": 0.0,
        "cashReceipts": 0.0,
        "isInCall": False,
        "liquidationValue": 8000.0,
        "longOptionMarketValue": 0.0,
        "longStockValue": 3000.0,
        "moneyMarketFund": 0.0,
        "mutualFundValue": 0.0,
        "pendingDeposits": 0.0,
        "shortOptionMarketValue": 0.0,
        "shortStockValue": 0.0,
        "unsettledCash": 1000.0,
    }

    def test_parses(self):
        bal = parse_initial_balance(self._CASH_INITIAL_RAW, AccountType.CASH)

        assert isinstance(bal, CashInitialBalance)
        assert bal.liquidation_value == 8000.0
        assert bal.is_in_call is False
        assert bal.cash_balance == 5000.0

    def test_missing_field_raises(self):
        raw = {k: v for k, v in self._CASH_INITIAL_RAW.items() if k != "isInCall"}
        with pytest.raises(InvalidApiResponseError, match="isInCall"):
            parse_initial_balance(raw, AccountType.CASH)
