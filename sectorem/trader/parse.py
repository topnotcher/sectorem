"""Parsers for Schwab Trader API responses."""

from __future__ import annotations

import enum
from datetime import date
from typing import Any

from .constants import AssetType, InstrumentType, OptionRight
from .types import (
    CashEquivalentPosition,
    CollectiveInvestmentPosition,
    CurrencyPosition,
    EquityPosition,
    FixedIncomePosition,
    IndexPosition,
    Instrument,
    MutualFundPosition,
    OptionInstrument,
    OptionPosition,
    Position,
)

_POSITION_CLASS: dict[AssetType, type[Position]] = {
    AssetType.EQUITY: EquityPosition,
    AssetType.OPTION: OptionPosition,
    AssetType.INDEX: IndexPosition,
    AssetType.MUTUAL_FUND: MutualFundPosition,
    AssetType.CASH_EQUIVALENT: CashEquivalentPosition,
    AssetType.FIXED_INCOME: FixedIncomePosition,
    AssetType.CURRENCY: CurrencyPosition,
    AssetType.COLLECTIVE_INVESTMENT: CollectiveInvestmentPosition,
}


def parse_position(raw: dict) -> Position:
    """
    Parse a raw Schwab position dict into a :class:`Position`.
    """
    raw_instrument = raw["instrument"]
    asset_type = AssetType(raw_instrument["assetType"])
    instrument = _parse_instrument(raw_instrument, asset_type)

    if raw["shortQuantity"] > 0:
        quantity = -raw["shortQuantity"]
        open_profit_loss = raw.get("shortOpenProfitLoss", 0.0)
    else:
        quantity = raw["longQuantity"]
        open_profit_loss = raw.get("longOpenProfitLoss", 0.0)

    average_price = raw.get("averagePrice", 0.0)

    pos_cls = _POSITION_CLASS.get(asset_type, Position)
    return pos_cls(
        instrument=instrument,
        quantity=quantity,
        average_price=average_price,
        market_value=raw["marketValue"],
        day_profit_loss=raw["currentDayProfitLoss"],
        open_profit_loss=open_profit_loss,
    )


def _parse_instrument(raw: dict, asset_type: AssetType) -> Instrument:
    """
    Parse a raw instrument dict into an :class:`Instrument`.
    """
    if asset_type == AssetType.OPTION:
        return _parse_option_instrument(raw)

    instrument_type = _parse_nullable_enum(InstrumentType, raw.get("type"))
    symbol = raw["symbol"]

    return Instrument(
        asset_type=asset_type,
        symbol=symbol,
        description=raw.get("description") or symbol,
        cusip=raw.get("cusip", ""),
        instrument_type=instrument_type,
    )


def _parse_option_instrument(raw: dict) -> OptionInstrument:
    """
    Parse an option instrument from raw API data.

    Extracts strike and expiration from the OCC symbol since the
    API does not provide them as separate fields.
    """
    occ_symbol = raw["symbol"]
    underlying = raw.get("underlyingSymbol") or occ_symbol[:6].strip()
    right = OptionRight(raw["putCall"])
    multiplier = raw.get("optionMultiplier", 100)

    strike, expiration = _parse_occ_symbol(occ_symbol)

    instrument_type = _parse_nullable_enum(InstrumentType, raw.get("type"))

    return OptionInstrument(
        asset_type=AssetType.OPTION,
        symbol=underlying,
        description=raw.get("description") or f'{underlying} {expiration} ${strike} {right.value}',
        cusip=raw.get("cusip", ""),
        instrument_type=instrument_type,
        strike=strike,
        right=right,
        expiration=expiration,
        multiplier=multiplier,
    )


def _parse_nullable_enum[T: enum.Enum](enum_cls: type[T], raw_value: Any) -> T|  None:
    """Convert a raw value to an enum value, or None."""
    try:
        return enum_cls(raw_value)

    except ValueError:
        return None


def _parse_occ_symbol(occ: str) -> tuple[float, date]:
    """
    Extract strike and expiration from an OCC symbol.

    Format: ``SYMBOL YYMMDDPSSSSSSSS``

    :returns: ``(strike, expiration)``
    """
    # The last 9 characters are: P/C (1) + strike*1000 (8)
    strike_int = int(occ[-8:])
    strike = strike_int / 1000.0

    # Date is 6 characters before that
    date_str = occ[-15:-9]
    expiration = date(2000 + int(date_str[:2]), int(date_str[2:4]), int(date_str[4:6]))

    return strike, expiration
