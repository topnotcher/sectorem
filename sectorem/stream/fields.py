"""Field definitions for Schwab streaming services."""

from __future__ import annotations

from enum import StrEnum


class StreamField(StrEnum):
    """Base class for streaming field enums."""

    @property
    def number(self) -> int:
        """The numeric field ID used by the Schwab streaming API."""
        return _REVERSE_MAPS[type(self)][self]

    @classmethod
    def from_number(cls, n: int) -> StreamField:
        """Look up a field by its numeric ID."""
        return _FORWARD_MAPS[cls][n]


class EquityField(StreamField):
    """Fields available for the ``LEVELONE_EQUITIES`` streaming service."""
    SYMBOL = "symbol"
    BID_PRICE = "bid_price"
    ASK_PRICE = "ask_price"
    LAST_PRICE = "last_price"
    BID_SIZE = "bid_size"
    ASK_SIZE = "ask_size"
    ASK_ID = "ask_id"
    BID_ID = "bid_id"
    TOTAL_VOLUME = "total_volume"
    LAST_SIZE = "last_size"
    HIGH_PRICE = "high_price"
    LOW_PRICE = "low_price"
    CLOSE_PRICE = "close_price"
    EXCHANGE_ID = "exchange_id"
    MARGINABLE = "marginable"
    DESCRIPTION = "description"
    LAST_ID = "last_id"
    OPEN_PRICE = "open_price"
    NET_CHANGE = "net_change"
    WEEK_52_HIGH = "week_52_high"
    WEEK_52_LOW = "week_52_low"
    PE_RATIO = "pe_ratio"
    ANNUAL_DIVIDEND_AMOUNT = "annual_dividend_amount"
    DIVIDEND_YIELD = "dividend_yield"
    NAV = "nav"
    EXCHANGE_NAME = "exchange_name"
    DIVIDEND_DATE = "dividend_date"
    REGULAR_MARKET_QUOTE = "regular_market_quote"
    REGULAR_MARKET_TRADE = "regular_market_trade"
    REGULAR_MARKET_LAST_PRICE = "regular_market_last_price"
    REGULAR_MARKET_LAST_SIZE = "regular_market_last_size"
    REGULAR_MARKET_NET_CHANGE = "regular_market_net_change"
    SECURITY_STATUS = "security_status"
    MARK_PRICE = "mark_price"
    QUOTE_TIME = "quote_time"
    TRADE_TIME = "trade_time"
    REGULAR_MARKET_TRADE_TIME = "regular_market_trade_time"
    BID_TIME = "bid_time"
    ASK_TIME = "ask_time"
    ASK_MIC_ID = "ask_mic_id"
    BID_MIC_ID = "bid_mic_id"
    LAST_MIC_ID = "last_mic_id"
    NET_PERCENT_CHANGE = "net_percent_change"
    REGULAR_MARKET_PERCENT_CHANGE = "regular_market_percent_change"
    MARK_PRICE_NET_CHANGE = "mark_price_net_change"
    MARK_PRICE_PERCENT_CHANGE = "mark_price_percent_change"
    HARD_TO_BORROW_QUANTITY = "hard_to_borrow_quantity"
    HARD_TO_BORROW_RATE = "hard_to_borrow_rate"
    HARD_TO_BORROW = "hard_to_borrow"
    SHORTABLE = "shortable"
    POST_MARKET_NET_CHANGE = "post_market_net_change"
    POST_MARKET_PERCENT_CHANGE = "post_market_percent_change"


_EQUITY_FIELD_MAP: dict[int, EquityField] = {
    0: EquityField.SYMBOL,
    1: EquityField.BID_PRICE,
    2: EquityField.ASK_PRICE,
    3: EquityField.LAST_PRICE,
    4: EquityField.BID_SIZE,
    5: EquityField.ASK_SIZE,
    6: EquityField.ASK_ID,
    7: EquityField.BID_ID,
    8: EquityField.TOTAL_VOLUME,
    9: EquityField.LAST_SIZE,
    10: EquityField.HIGH_PRICE,
    11: EquityField.LOW_PRICE,
    12: EquityField.CLOSE_PRICE,
    13: EquityField.EXCHANGE_ID,
    14: EquityField.MARGINABLE,
    15: EquityField.DESCRIPTION,
    16: EquityField.LAST_ID,
    17: EquityField.OPEN_PRICE,
    18: EquityField.NET_CHANGE,
    19: EquityField.WEEK_52_HIGH,
    20: EquityField.WEEK_52_LOW,
    21: EquityField.PE_RATIO,
    22: EquityField.ANNUAL_DIVIDEND_AMOUNT,
    23: EquityField.DIVIDEND_YIELD,
    24: EquityField.NAV,
    25: EquityField.EXCHANGE_NAME,
    26: EquityField.DIVIDEND_DATE,
    27: EquityField.REGULAR_MARKET_QUOTE,
    28: EquityField.REGULAR_MARKET_TRADE,
    29: EquityField.REGULAR_MARKET_LAST_PRICE,
    30: EquityField.REGULAR_MARKET_LAST_SIZE,
    31: EquityField.REGULAR_MARKET_NET_CHANGE,
    32: EquityField.SECURITY_STATUS,
    33: EquityField.MARK_PRICE,
    34: EquityField.QUOTE_TIME,
    35: EquityField.TRADE_TIME,
    36: EquityField.REGULAR_MARKET_TRADE_TIME,
    37: EquityField.BID_TIME,
    38: EquityField.ASK_TIME,
    39: EquityField.ASK_MIC_ID,
    40: EquityField.BID_MIC_ID,
    41: EquityField.LAST_MIC_ID,
    42: EquityField.NET_PERCENT_CHANGE,
    43: EquityField.REGULAR_MARKET_PERCENT_CHANGE,
    44: EquityField.MARK_PRICE_NET_CHANGE,
    45: EquityField.MARK_PRICE_PERCENT_CHANGE,
    46: EquityField.HARD_TO_BORROW_QUANTITY,
    47: EquityField.HARD_TO_BORROW_RATE,
    48: EquityField.HARD_TO_BORROW,
    49: EquityField.SHORTABLE,
    50: EquityField.POST_MARKET_NET_CHANGE,
    51: EquityField.POST_MARKET_PERCENT_CHANGE,
}


class AccountActivityField(StreamField):
    """Fields available for the ``ACCT_ACTIVITY`` streaming service."""
    ALL = "_all"
    ACCOUNT_NUMBER = "account_number"
    MESSAGE_TYPE = "message_type"
    MESSAGE_DATA = "message_data"


_ACCOUNT_ACTIVITY_FIELD_MAP: dict[int, AccountActivityField] = {
    0: AccountActivityField.ALL,
    1: AccountActivityField.ACCOUNT_NUMBER,
    2: AccountActivityField.MESSAGE_TYPE,
    3: AccountActivityField.MESSAGE_DATA,
}


class StreamService(StrEnum):
    """Available Schwab streaming services."""
    LEVELONE_EQUITIES = "LEVELONE_EQUITIES"
    LEVELONE_OPTIONS = "LEVELONE_OPTIONS"
    LEVELONE_FUTURES = "LEVELONE_FUTURES"
    LEVELONE_FUTURES_OPTIONS = "LEVELONE_FUTURES_OPTIONS"
    LEVELONE_FOREX = "LEVELONE_FOREX"
    NYSE_BOOK = "NYSE_BOOK"
    NASDAQ_BOOK = "NASDAQ_BOOK"
    OPTIONS_BOOK = "OPTIONS_BOOK"
    CHART_EQUITY = "CHART_EQUITY"
    CHART_FUTURES = "CHART_FUTURES"
    SCREENER_EQUITY = "SCREENER_EQUITY"
    SCREENER_OPTION = "SCREENER_OPTION"
    ACCT_ACTIVITY = "ACCT_ACTIVITY"

    @property
    def field_type(self) -> type[StreamField] | None:
        """The field enum type for this service, or ``None`` if not yet mapped."""
        return _SERVICE_FIELD_TYPES.get(self)


# Forward maps: int → field enum member.
_FORWARD_MAPS = {
    EquityField: _EQUITY_FIELD_MAP,
    AccountActivityField: _ACCOUNT_ACTIVITY_FIELD_MAP,
}

# Reverse maps: field enum member → int. Built lazily.
_REVERSE_MAPS = {}

for _cls, _fmap in _FORWARD_MAPS.items():
    _REVERSE_MAPS[_cls] = {v: k for k, v in _fmap.items()}

# Service → field enum type.
_SERVICE_FIELD_TYPES = {
    "LEVELONE_EQUITIES": EquityField,
    "ACCT_ACTIVITY": AccountActivityField,
}

# Verify enums and maps are in sync at import time.
for _cls, _fmap in _FORWARD_MAPS.items():
    assert set(_fmap.values()) == set(_cls), f"{_cls.__name__}: enum and field map are out of sync"
