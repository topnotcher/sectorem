"""Types for the Schwab Trader API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .constants import AssetType, OptionRight


# ---------------------------------------------------------------------------
# Instruments
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class Instrument:
    """
    Base instrument identifying a tradable security.

    :param asset_type: Schwab asset classification.
    :param symbol: Ticker symbol.
    """
    asset_type: AssetType
    symbol: str


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
