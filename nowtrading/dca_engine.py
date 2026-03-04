from __future__ import annotations

from nowtrading.interfaces import NtIndicatorSource
from nowtrading.types import NtBasketState, NtDirection
from nowtrading.utils import nt_pips_to_price


class NtDcaEngine:
    def __init__(self, source: NtIndicatorSource, symbol: str, digits: int) -> None:
        self._source = source
        self._symbol = symbol
        self._digits = digits

    def should_add(self, basket: NtBasketState, spacing_pips: float) -> bool:
        if not basket.active or basket.direction == NtDirection.NONE:
            return False

        bid = self._source.bid(self._symbol)
        ask = self._source.ask(self._symbol)
        point = self._source.point(self._symbol)
        spacing = nt_pips_to_price(self._digits, point, spacing_pips)

        if basket.direction == NtDirection.BUY:
            return (basket.last_filled_price - bid) >= spacing
        return (ask - basket.last_filled_price) >= spacing

