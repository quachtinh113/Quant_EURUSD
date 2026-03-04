from __future__ import annotations

from nowtrading.interfaces import NtIndicatorSource
from nowtrading.types import NtSignalSnapshot


class NtIndicators:
    def __init__(self, source: NtIndicatorSource, symbol: str) -> None:
        self._source = source
        self._symbol = symbol

    def snapshot(self) -> NtSignalSnapshot | None:
        try:
            ask = self._source.ask(self._symbol)
            bid = self._source.bid(self._symbol)
            point = self._source.point(self._symbol)
            spread_points = (ask - bid) / point if point > 0 else 0.0
            return NtSignalSnapshot(
                rsi_h1=self._source.rsi(self._symbol, "H1", 14, 1),
                rsi_m30=self._source.rsi(self._symbol, "M30", 14, 1),
                rsi_m15_prev2=self._source.rsi(self._symbol, "M15", 14, 2),
                rsi_m15_prev1=self._source.rsi(self._symbol, "M15", 14, 1),
                rsi_h4=self._source.rsi(self._symbol, "H4", 14, 1),
                rsi_d1=self._source.rsi(self._symbol, "D1", 14, 1),
                adx_h1=self._source.adx(self._symbol, "H1", 14, 1),
                atr_m15=self._source.atr(self._symbol, "M15", 14, 1),
                spread_points=spread_points,
            )
        except Exception:
            return None

