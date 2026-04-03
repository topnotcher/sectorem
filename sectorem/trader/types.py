"""Types for the Schwab Trader API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .constants import AssetType, InstrumentType, OptionRight


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class Instrument:
    """
    Base instrument identifying a tradable security.

    :param asset_type: Schwab asset classification.
    :param symbol: Ticker symbol.
    :param description: Human-readable description (e.g. fund name).
    :param cusip: CUSIP identifier.
    :param instrument_type: Sub-type within the asset class
        (e.g. ``EXCHANGE_TRADED_FUND``, ``VANILLA``).
    """
    asset_type: AssetType
    symbol: str
    description: str
    cusip: str = ""
    instrument_type: InstrumentType | None = None


@dataclass(slots=True, frozen=True)
class OptionInstrument(Instrument):
    """
    An option contract.

    ``symbol`` is the underlying ticker (e.g. ``"SMCI"``), not the
    OCC symbol. Use :meth:`occ_symbol` to get the OCC representation.

    :param strike: Strike price.
    :param right: Put or call.
    :param expiration: Expiration date.
    :param multiplier: Contract multiplier (typically 100).
    """
    strike: float = 0.0
    right: OptionRight = OptionRight.CALL
    expiration: date = date.min
    multiplier: int = 100

    @property
    def occ_symbol(self) -> str:
        """
        OCC-format symbol string.

        Format: ``SYMBOL YYMMDDPSSSSSSSS`` where the strike is
        the price multiplied by 1000, zero-padded to 8 digits.
        """
        side = self.right.value[0]  # 'C' or 'P'
        strike_int = int(self.strike * 1000)
        return f"{self.symbol:<6s}{self.expiration.strftime('%y%m%d')}{side}{strike_int:08d}"


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class Position:
    """
    A position in a single instrument.

    :param instrument: The held instrument.
    :param quantity: Signed quantity (negative for short).
    :param average_price: Average cost basis per unit.
    :param market_value: Current market value.
    :param day_profit_loss: Unrealized P&L for the current day.
    :param open_profit_loss: Total unrealized P&L.
    """
    instrument: Instrument
    quantity: float
    average_price: float
    market_value: float
    day_profit_loss: float
    open_profit_loss: float


@dataclass(slots=True, frozen=True)
class EquityPosition(Position):
    """A position in an equity instrument."""
    instrument: Instrument


@dataclass(slots=True, frozen=True)
class OptionPosition(Position):
    """A position in an option contract."""
    instrument: OptionInstrument


@dataclass(slots=True, frozen=True)
class CollectiveInvestmentPosition(Position):
    """A position in a collective investment (e.g. ETF)."""
    instrument: Instrument


@dataclass(slots=True, frozen=True)
class MutualFundPosition(Position):
    """A position in a mutual fund."""
    instrument: Instrument


@dataclass(slots=True, frozen=True)
class FixedIncomePosition(Position):
    """A position in a fixed income instrument."""
    instrument: Instrument


@dataclass(slots=True, frozen=True)
class CashEquivalentPosition(Position):
    """A position in a cash equivalent (e.g. money market fund)."""
    instrument: Instrument


@dataclass(slots=True, frozen=True)
class IndexPosition(Position):
    """A position in an index."""
    instrument: Instrument


@dataclass(slots=True, frozen=True)
class CurrencyPosition(Position):
    """A position in a currency."""
    instrument: Instrument


# ---------------------------------------------------------------------------
# Balances — Margin
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class MarginBalance:
    """
    Current balances for a margin account.

    Merged from the ``currentBalances`` and ``projectedBalances`` sections
    of the Schwab API response.
    """
    # From currentBalances
    accrued_interest: float
    available_funds: float
    available_funds_non_marginable_trade: float
    bond_value: float
    buying_power: float
    buying_power_non_marginable_trade: float
    cash_balance: float
    cash_receipts: float
    day_trading_buying_power: float
    equity: float
    equity_percentage: float
    liquidation_value: float
    long_margin_value: float
    long_market_value: float
    long_option_market_value: float
    maintenance_call: float
    maintenance_requirement: float
    #: Margin debit balance
    margin_balance: float
    money_market_fund: float
    mutual_fund_value: float
    pending_deposits: float
    #: Reg-T margin call amount
    reg_t_call: float
    savings: float
    short_balance: float
    short_margin_value: float
    short_market_value: float
    short_option_market_value: float
    #: Special memorandum account
    sma: float
    # From projectedBalances
    day_trading_buying_power_call: float
    #: Whether the account is in a margin call
    is_in_call: bool
    stock_buying_power: float


@dataclass(slots=True, frozen=True)
class MarginInitialBalance:
    """
    Start-of-day balances for a margin account.

    From the ``initialBalances`` section of the Schwab API response.
    """
    accrued_interest: float
    available_funds_non_marginable_trade: float
    bond_value: float
    buying_power: float
    cash_available_for_trading: float
    cash_balance: float
    cash_receipts: float
    day_trading_buying_power: float
    day_trading_buying_power_call: float
    day_trading_equity_call: float
    equity: float
    equity_percentage: float
    #: Whether the account is in a margin call
    is_in_call: bool
    liquidation_value: float
    long_margin_value: float
    long_option_market_value: float
    long_stock_value: float
    maintenance_call: float
    maintenance_requirement: float
    #: Margin debit balance
    margin_balance: float
    margin_equity: float
    money_market_fund: float
    mutual_fund_value: float
    pending_deposits: float
    #: Reg-T margin call amount
    reg_t_call: float
    short_balance: float
    short_margin_value: float
    short_option_market_value: float
    short_stock_value: float
    total_cash: float


# ---------------------------------------------------------------------------
# Balances — Cash
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class CashBalance:
    """
    Current balances for a cash account.

    From the ``currentBalances`` section of the Schwab API response.
    Field set based on the OpenAPI spec — not verified against live data.
    """
    cash_available_for_trading: float
    cash_available_for_withdrawal: float
    cash_call: float
    cash_debit_call_value: float
    long_non_marginable_market_value: float
    total_cash: float
    unsettled_cash: float


@dataclass(slots=True, frozen=True)
class CashInitialBalance:
    """
    Start-of-day balances for a cash account.

    From the ``initialBalances`` section of the Schwab API response.
    Field set based on the OpenAPI spec — not verified against live data.
    """
    accrued_interest: float
    bond_value: float
    cash_available_for_trading: float
    cash_available_for_withdrawal: float
    cash_balance: float
    cash_debit_call_value: float
    cash_receipts: float
    #: Whether the account is in a margin call
    is_in_call: bool
    liquidation_value: float
    long_option_market_value: float
    long_stock_value: float
    money_market_fund: float
    mutual_fund_value: float
    pending_deposits: float
    short_option_market_value: float
    short_stock_value: float
    unsettled_cash: float


#: Union of current balance types.
Balance = MarginBalance | CashBalance

#: Union of initial balance types.
InitialBalance = MarginInitialBalance | CashInitialBalance
