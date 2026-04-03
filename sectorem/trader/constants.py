"""Constants for the Schwab Trader API."""

from __future__ import annotations

import enum


class AssetType(enum.Enum):
    """Schwab asset type classification."""
    EQUITY = "EQUITY"
    OPTION = "OPTION"
    INDEX = "INDEX"
    MUTUAL_FUND = "MUTUAL_FUND"
    CASH_EQUIVALENT = "CASH_EQUIVALENT"
    FIXED_INCOME = "FIXED_INCOME"
    CURRENCY = "CURRENCY"
    COLLECTIVE_INVESTMENT = "COLLECTIVE_INVESTMENT"
    FUTURE = "FUTURE"
    FOREX = "FOREX"
    PRODUCT = "PRODUCT"


class AccountType(enum.Enum):
    """Schwab account type."""
    MARGIN = "MARGIN"
    CASH = "CASH"


class InstrumentType(enum.Enum):
    """Instrument sub-type within an asset class."""
    # CollectiveInvestment
    EXCHANGE_TRADED_FUND = "EXCHANGE_TRADED_FUND"
    UNIT_INVESTMENT_TRUST = "UNIT_INVESTMENT_TRUST"
    CLOSED_END_FUND = "CLOSED_END_FUND"
    INDEX = "INDEX"
    UNITS = "UNITS"
    # Option
    VANILLA = "VANILLA"
    BINARY = "BINARY"
    BARRIER = "BARRIER"
    # CashEquivalent
    SWEEP_VEHICLE = "SWEEP_VEHICLE"
    SAVINGS = "SAVINGS"
    MONEY_MARKET_FUND = "MONEY_MARKET_FUND"
    # Shared
    UNKNOWN = "UNKNOWN"


class OptionRight(enum.Enum):
    """Option right."""
    PUT = "PUT"
    CALL = "CALL"
