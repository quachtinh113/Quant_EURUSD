from __future__ import annotations

from datetime import datetime
from typing import Protocol

from nowtrading.types import NtAccountState, NtDirection, NtOrder, NtPosition


class NtIndicatorSource(Protocol):
    def rsi(self, symbol: str, timeframe: str, period: int, shift: int) -> float: ...

    def adx(self, symbol: str, timeframe: str, period: int, shift: int) -> float: ...

    def atr(self, symbol: str, timeframe: str, period: int, shift: int) -> float: ...

    def bid(self, symbol: str) -> float: ...

    def ask(self, symbol: str) -> float: ...

    def point(self, symbol: str) -> float: ...


class NtAccountSource(Protocol):
    def account_state(self) -> NtAccountState: ...


class NtBroker(NtIndicatorSource, Protocol):
    def digits(self, symbol: str) -> int: ...

    def volume_limits(self, symbol: str) -> tuple[float, float, float]: ...

    def place_market_order(
        self,
        direction: NtDirection,
        symbol: str,
        lots: float,
        stop_loss: float,
        comment: str,
    ) -> bool: ...

    def place_limit_order(
        self,
        direction: NtDirection,
        symbol: str,
        lots: float,
        price: float,
        stop_loss: float,
        comment: str,
    ) -> bool: ...

    def get_positions(self, symbol: str, magic: int) -> list[NtPosition]: ...

    def get_orders(self, symbol: str, magic: int) -> list[NtOrder]: ...

    def close_position(self, ticket: int, deviation_points: int) -> bool: ...

    def cancel_order(self, ticket: int) -> bool: ...

    def now(self) -> datetime: ...

