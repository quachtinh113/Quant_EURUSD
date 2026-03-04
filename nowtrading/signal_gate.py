from __future__ import annotations

from nowtrading.types import NtDirection, NtSignalSnapshot


class NtSignalGate:
    H1_BUY_MIN = 55.0
    H1_SELL_MAX = 45.0
    M30_BUY_MIN = 40.0
    M30_BUY_MAX = 50.0
    M30_SELL_MIN = 50.0
    M30_SELL_MAX = 60.0
    M15_BUY_CROSS = 40.0
    M15_SELL_CROSS = 60.0
    ADX_MIN = 22.0

    def evaluate(self, sig: NtSignalSnapshot, max_spread_points: float) -> NtDirection:
        if sig.spread_points > max_spread_points:
            return NtDirection.NONE
        if sig.adx_h1 <= self.ADX_MIN:
            return NtDirection.NONE

        if sig.rsi_h1 > self.H1_BUY_MIN:
            if sig.rsi_m30 < self.M30_BUY_MIN or sig.rsi_m30 > self.M30_BUY_MAX:
                return NtDirection.NONE
            crossed_up = (
                sig.rsi_m15_prev2 <= self.M15_BUY_CROSS
                and sig.rsi_m15_prev1 > self.M15_BUY_CROSS
            )
            return NtDirection.BUY if crossed_up else NtDirection.NONE

        if sig.rsi_h1 < self.H1_SELL_MAX:
            if sig.rsi_m30 < self.M30_SELL_MIN or sig.rsi_m30 > self.M30_SELL_MAX:
                return NtDirection.NONE
            crossed_down = (
                sig.rsi_m15_prev2 >= self.M15_SELL_CROSS
                and sig.rsi_m15_prev1 < self.M15_SELL_CROSS
            )
            return NtDirection.SELL if crossed_down else NtDirection.NONE

        return NtDirection.NONE

