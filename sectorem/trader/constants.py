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


class OrderStatus(enum.Enum):
    """Schwab order status."""
    AWAITING_PARENT_ORDER = "AWAITING_PARENT_ORDER"
    AWAITING_CONDITION = "AWAITING_CONDITION"
    AWAITING_STOP_CONDITION = "AWAITING_STOP_CONDITION"
    AWAITING_MANUAL_REVIEW = "AWAITING_MANUAL_REVIEW"
    ACCEPTED = "ACCEPTED"
    AWAITING_UR_OUT = "AWAITING_UR_OUT"
    PENDING_ACTIVATION = "PENDING_ACTIVATION"
    QUEUED = "QUEUED"
    WORKING = "WORKING"
    REJECTED = "REJECTED"
    PENDING_CANCEL = "PENDING_CANCEL"
    CANCELED = "CANCELED"
    PENDING_REPLACE = "PENDING_REPLACE"
    REPLACED = "REPLACED"
    FILLED = "FILLED"
    EXPIRED = "EXPIRED"
    NEW = "NEW"
    AWAITING_RELEASE_TIME = "AWAITING_RELEASE_TIME"
    PENDING_ACKNOWLEDGEMENT = "PENDING_ACKNOWLEDGEMENT"
    PENDING_RECALL = "PENDING_RECALL"
    UNKNOWN = "UNKNOWN"

    @property
    def is_terminal(self) -> bool:
        """
        Whether the order can no longer fill from this status.

        ``UNKNOWN`` counts as terminal: it is also what unrecognized API
        values map to, and waiting on a status we can't interpret is unsafe.
        """
        return self in _TERMINAL_ORDER_STATUSES


_TERMINAL_ORDER_STATUSES = frozenset({
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
    OrderStatus.REPLACED,
    OrderStatus.UNKNOWN,
})
