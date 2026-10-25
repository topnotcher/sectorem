"""Types for the Schwab Trader API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .constants import AssetType, InstrumentType, OptionRight, OrderStatus, OrderValidationLevel


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
    description: str = ""
    cusip: str | None = None
    instrument_type: InstrumentType | None = None


@dataclass(slots=True, frozen=True)
class Option:
    """
    An option contract.

    ``symbol`` is the underlying ticker (e.g. ``"SMCI"``), not the
    OCC symbol. Use :meth:`occ_symbol` to get the OCC representation.

    :param symbol: Underlying ticker symbol.
    :param strike: Strike price.
    :param right: Put or call.
    :param expiration: Expiration date.
    :param multiplier: Contract multiplier (typically 100).
    """
    symbol: str
    strike: float
    right: OptionRight
    expiration: date
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


@dataclass(slots=True, frozen=True)
class OptionInstrument(Instrument):
    """
    An option instrument with full API metadata.

    Wraps an :class:`Option` with the instrument metadata from a
    Schwab API response. Use :attr:`option` to access the option
    contract details directly.
    """
    option: Option = Option("", 0.0, OptionRight.CALL, date.min)

    @property
    def strike(self) -> float:
        return self.option.strike

    @property
    def right(self) -> OptionRight:
        return self.option.right

    @property
    def expiration(self) -> date:
        return self.option.expiration

    @property
    def multiplier(self) -> int:
        return self.option.multiplier

    @property
    def occ_symbol(self) -> str:
        return self.option.occ_symbol


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


@dataclass(slots=True, frozen=True)
class ValidationMessage:
    """
    A message from Schwab's order validation.
    """
    #: Severity of the message.
    level: OrderValidationLevel
    #: Human-readable text.
    message: str


@dataclass(slots=True, frozen=True)
class OrderPreview:
    """
    Result of previewing an order without placing it.

    From the ``previewOrder`` response. An accepted preview has an empty
    ``orderValidationResult``; a rejected one carries one or more messages
    (e.g. "You do not have enough available cash/buying power for this order.").
    """
    #: Validation verdict (``ACCEPTED`` when the order would be placed).
    status: OrderStatus
    #: Notional value of the order.
    order_value: float
    #: Available funds after the order.
    projected_available_funds: float
    #: Buying power after the order.
    projected_buying_power: float
    #: Intraday buying power after the order.
    projected_intraday_buying_power: float
    #: Commission estimate from the balance projection.
    projected_commission: float
    #: Total commission across all legs.
    commission: float
    #: Total regulatory fees across all legs.
    fees: float
    #: Validation messages, if any.
    messages: tuple[ValidationMessage, ...] = ()


@dataclass(slots=True, frozen=True)
class Execution:
    """
    A single execution (fill) against an order leg.
    """
    #: Which leg of the order was filled.
    leg_id: int
    #: Shares or contracts filled in this execution.
    quantity: float
    #: Execution price per unit.
    price: float
    #: When the execution occurred.
    time: datetime


@dataclass(slots=True, frozen=True)
class OrderResult:
    """
    The state of a submitted order as last read from the API.

    Returned by :meth:`~sectorem.trader.order.OrderHandle.wait`,
    :meth:`~sectorem.trader.order.OrderHandle.cancel`, and
    :meth:`~sectorem.trader.order.OrderHandle.result`, and carried by
    :class:`~sectorem.errors.OrderError`. Schwab has no partial-fill status:
    a partially filled order stays ``WORKING`` and, if it then expires or is
    canceled, ends ``CANCELED`` or ``EXPIRED`` with a non-zero
    ``filled_quantity``. Always read ``filled_quantity`` rather than inferring
    fills from ``status``.
    """
    #: The Schwab order ID.
    order_id: int
    #: Order status at the time of the read.
    status: OrderStatus
    #: Quantity requested.
    quantity: float
    #: Quantity filled so far.
    filled_quantity: float
    #: Quantity still open.
    remaining_quantity: float
    #: Individual fills, in the order the API reported them.
    executions: tuple[Execution, ...] = ()

    @property
    def average_price(self) -> float | None:
        """
        Quantity-weighted average execution price, or ``None`` if nothing has filled.

        For multi-leg orders this averages across legs and is rarely meaningful;
        use :attr:`executions` instead.
        """
        filled = sum(e.quantity for e in self.executions)
        if not filled:
            return None
        return sum(e.quantity * e.price for e in self.executions) / filled
