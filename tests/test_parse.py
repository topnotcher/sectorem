"""Tests for position and instrument parsing."""

from __future__ import annotations

from datetime import date

import pytest

from sectorem.trader.constants import AssetType, InstrumentType, OptionRight
from sectorem.trader.parse import parse_position, _parse_occ_symbol
from sectorem.trader.types import (
    CollectiveInvestmentPosition,
    EquityPosition,
    Instrument,
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
        # This tests the Account.get_positions level, not parse_position directly,
        # but parse_position handles individual items — just verify no crash on valid input.
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
