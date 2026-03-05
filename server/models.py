from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class BotState(str, Enum):
    IDLE = "IDLE"
    IN_BASKET = "IN_BASKET"
    COOLDOWN = "COOLDOWN"


@dataclass(slots=True)
class Basket:
    basket_id: str
    symbol: str = "EURUSD"
    side: str = "BUY"
    open_time: datetime | None = None
    first_entry_price: float = 0.0
    last_fill_price: float = 0.0
    total_lot: float = 0.0
    order_count: int = 0
    realized_pnl_usd: float = 0.0
    floating_pnl_usd: float = 0.0
    mae_pips: float = 0.0


@dataclass(slots=True)
class RuntimeState:
    state: BotState = BotState.IDLE
    current_basket: Basket | None = None
    cooldown_until: datetime | None = None
    blocked_for_day: bool = False
    day_start_balance: float = 0.0
    day_key: str = ""
    last_window_id: str = ""
    disable_entries: bool = False
    disable_dca: bool = False
    fail_safe_reason: str = ""
    guard_reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MarketSnapshot:
    now_utc: datetime
    vn_hour: int
    vn_minute: int
    spread_pips: float
    adx_h1: float
    rsi_m15: float
    price_bid: float
    price_ask: float


@dataclass(slots=True)
class AccountSnapshot:
    balance: float
    equity: float


@dataclass(slots=True)
class Decision:
    action: str
    reason: str
    side: str = ""
    lot: float = 0.0
    window_id: str = ""
    basket_id: str = ""
