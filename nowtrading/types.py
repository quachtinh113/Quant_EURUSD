from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class NtDirection(IntEnum):
    NONE = 0
    BUY = 1
    SELL = -1


class NtTpMode(IntEnum):
    MONEY = 0
    ATR = 1


class NtLogLevel(IntEnum):
    ERROR = 0
    INFO = 1
    DEBUG = 2


@dataclass(slots=True)
class NtSignalSnapshot:
    rsi_h1: float = 0.0
    rsi_m30: float = 0.0
    rsi_m15_prev2: float = 0.0
    rsi_m15_prev1: float = 0.0
    rsi_h4: float = 0.0
    rsi_d1: float = 0.0
    adx_h1: float = 0.0
    atr_m15: float = 0.0
    spread_points: float = 0.0


@dataclass(slots=True)
class NtRiskSnapshot:
    block_new_entries: bool = False
    block_dca: bool = False
    dd_daily_percent: float = 0.0
    dd_floating_percent: float = 0.0
    free_margin_percent: float = 100.0
    consecutive_losing_baskets: int = 0
    reason: str = ""


@dataclass(slots=True)
class NtBasketState:
    active: bool = False
    basket_id: int = 0
    direction: NtDirection = NtDirection.NONE
    first_open_time: datetime | None = None
    weighted_avg_price: float = 0.0
    floating_profit: float = 0.0
    position_count: int = 0
    dca_count: int = 0
    total_lots: float = 0.0
    last_filled_price: float = 0.0


@dataclass(slots=True)
class NtAccountState:
    equity: float
    balance: float
    margin: float
    free_margin: float


@dataclass(slots=True)
class NtPosition:
    ticket: int
    symbol: str
    magic: int
    comment: str
    volume: float
    open_price: float
    open_time: datetime
    profit: float


@dataclass(slots=True)
class NtOrder:
    ticket: int
    symbol: str
    magic: int
    comment: str

