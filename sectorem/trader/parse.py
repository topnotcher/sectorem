"""Parsers for Schwab Trader API responses."""

from __future__ import annotations

import enum
import logging
from datetime import date
from typing import Any

from ..errors import InvalidApiResponseError
from .constants import AccountType, AssetType, InstrumentType, OptionRight
from .types import (
    Balance,
    CashBalance,
    CashEquivalentPosition,
    CashInitialBalance,
    CollectiveInvestmentPosition,
    CurrencyPosition,
    EquityPosition,
    FixedIncomePosition,
    IndexPosition,
    InitialBalance,
    Instrument,
    MarginBalance,
    MarginInitialBalance,
    MutualFundPosition,
    OptionInstrument,
    OptionPosition,
    Position,
)

log = logging.getLogger(__name__)


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


def _parse_nullable_enum[T: enum.Enum](enum_cls: type[T], raw_value: Any) -> T | None:
    """Convert a raw value to an enum value, or None."""
    try:
        return enum_cls(raw_value)

    except ValueError:
        return None


# Balance field maps: {api_field_name: dataclass_field_name}. Missing fields
# raise InvalidApiResponseError; extra fields are silently ignored.
_MARGIN_CURRENT_FIELDS: dict[str, str] = {
    "accruedInterest": "accrued_interest",
    "availableFunds": "available_funds",
    "availableFundsNonMarginableTrade": "available_funds_non_marginable_trade",
    "bondValue": "bond_value",
    "buyingPower": "buying_power",
    "buyingPowerNonMarginableTrade": "buying_power_non_marginable_trade",
    "cashBalance": "cash_balance",
    "cashReceipts": "cash_receipts",
    "dayTradingBuyingPower": "day_trading_buying_power",
    "equity": "equity",
    "equityPercentage": "equity_percentage",
    "liquidationValue": "liquidation_value",
    "longMarginValue": "long_margin_value",
    "longMarketValue": "long_market_value",
    "longOptionMarketValue": "long_option_market_value",
    "maintenanceCall": "maintenance_call",
    "maintenanceRequirement": "maintenance_requirement",
    "marginBalance": "margin_balance",
    "moneyMarketFund": "money_market_fund",
    "mutualFundValue": "mutual_fund_value",
    "pendingDeposits": "pending_deposits",
    "regTCall": "reg_t_call",
    "savings": "savings",
    "shortBalance": "short_balance",
    "shortMarginValue": "short_margin_value",
    "shortMarketValue": "short_market_value",
    "shortOptionMarketValue": "short_option_market_value",
    "sma": "sma",
}

_MARGIN_PROJECTED_FIELDS: dict[str, str] = {
    "dayTradingBuyingPowerCall": "day_trading_buying_power_call",
    "isInCall": "is_in_call",
    "stockBuyingPower": "stock_buying_power",
}

_MARGIN_INITIAL_FIELDS: dict[str, str] = {
    "accruedInterest": "accrued_interest",
    "availableFundsNonMarginableTrade": "available_funds_non_marginable_trade",
    "bondValue": "bond_value",
    "buyingPower": "buying_power",
    "cashAvailableForTrading": "cash_available_for_trading",
    "cashBalance": "cash_balance",
    "cashReceipts": "cash_receipts",
    "dayTradingBuyingPower": "day_trading_buying_power",
    "dayTradingBuyingPowerCall": "day_trading_buying_power_call",
    "dayTradingEquityCall": "day_trading_equity_call",
    "equity": "equity",
    "equityPercentage": "equity_percentage",
    "isInCall": "is_in_call",
    "liquidationValue": "liquidation_value",
    "longMarginValue": "long_margin_value",
    "longOptionMarketValue": "long_option_market_value",
    "longStockValue": "long_stock_value",
    "maintenanceCall": "maintenance_call",
    "maintenanceRequirement": "maintenance_requirement",
    "marginBalance": "margin_balance",
    "marginEquity": "margin_equity",
    "moneyMarketFund": "money_market_fund",
    "mutualFundValue": "mutual_fund_value",
    "pendingDeposits": "pending_deposits",
    "regTCall": "reg_t_call",
    "shortBalance": "short_balance",
    "shortMarginValue": "short_margin_value",
    "shortOptionMarketValue": "short_option_market_value",
    "shortStockValue": "short_stock_value",
    "totalCash": "total_cash",
}

_CASH_CURRENT_FIELDS: dict[str, str] = {
    "cashAvailableForTrading": "cash_available_for_trading",
    "cashAvailableForWithdrawal": "cash_available_for_withdrawal",
    "cashCall": "cash_call",
    "cashDebitCallValue": "cash_debit_call_value",
    "longNonMarginableMarketValue": "long_non_marginable_market_value",
    "totalCash": "total_cash",
    "unsettledCash": "unsettled_cash",
}

_CASH_INITIAL_FIELDS: dict[str, str] = {
    "accruedInterest": "accrued_interest",
    "bondValue": "bond_value",
    "cashAvailableForTrading": "cash_available_for_trading",
    "cashAvailableForWithdrawal": "cash_available_for_withdrawal",
    "cashBalance": "cash_balance",
    "cashDebitCallValue": "cash_debit_call_value",
    "cashReceipts": "cash_receipts",
    "isInCall": "is_in_call",
    "liquidationValue": "liquidation_value",
    "longOptionMarketValue": "long_option_market_value",
    "longStockValue": "long_stock_value",
    "moneyMarketFund": "money_market_fund",
    "mutualFundValue": "mutual_fund_value",
    "pendingDeposits": "pending_deposits",
    "shortOptionMarketValue": "short_option_market_value",
    "shortStockValue": "short_stock_value",
    "unsettledCash": "unsettled_cash",
}


def _extract_fields(raw: dict, field_map: dict[str, str], label: str) -> dict[str, Any]:
    """
    Extract fields from a raw API dict using a field map.

    :raises InvalidApiResponseError: If any expected fields are missing.
    """
    kwargs: dict[str, Any] = {}
    missing: list[str] = []

    for api_field, py_field in field_map.items():
        if api_field in raw:
            kwargs[py_field] = raw[api_field]
        else:
            missing.append(api_field)

    if missing:
        raise InvalidApiResponseError(
            f"Missing fields in {label}: {', '.join(missing)}"
        )

    return kwargs


def parse_balance(
    current_raw: dict,
    projected_raw: dict,
    account_type: AccountType,
) -> Balance:
    """
    Parse current balances from the ``currentBalances`` and ``projectedBalances``
    sections of a Schwab account response.

    :raises InvalidApiResponseError: If any expected fields are missing.
    """
    if account_type == AccountType.MARGIN:
        kwargs = _extract_fields(current_raw, _MARGIN_CURRENT_FIELDS, "margin currentBalances")
        kwargs.update(_extract_fields(projected_raw, _MARGIN_PROJECTED_FIELDS, "margin projectedBalances"))
        return MarginBalance(**kwargs)

    kwargs = _extract_fields(current_raw, _CASH_CURRENT_FIELDS, "cash currentBalances")
    return CashBalance(**kwargs)


def parse_initial_balance(raw: dict, account_type: AccountType) -> InitialBalance:
    """
    Parse initial (start-of-day) balances from the ``initialBalances``
    section of a Schwab account response.

    :raises InvalidApiResponseError: If any expected fields are missing.
    """
    if account_type == AccountType.MARGIN:
        kwargs = _extract_fields(raw, _MARGIN_INITIAL_FIELDS, "margin initialBalances")
        return MarginInitialBalance(**kwargs)

    kwargs = _extract_fields(raw, _CASH_INITIAL_FIELDS, "cash initialBalances")
    return CashInitialBalance(**kwargs)


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
