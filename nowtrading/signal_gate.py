from __future__ import annotations

from nowtrading.types import NtDirection, NtSignalSnapshot


class NtSignalGate:
    RSI_BUY_MIN = 50.0
    RSI_SELL_MAX = 50.0

    def evaluate(self, sig: NtSignalSnapshot, max_spread_points: float) -> NtDirection:
        if sig.spread_points > max_spread_points:
            return NtDirection.NONE

        buy_ready = (
            sig.rsi_h1 > self.RSI_BUY_MIN
            and sig.rsi_m30 > self.RSI_BUY_MIN
            and sig.rsi_m15_prev1 > self.RSI_BUY_MIN
        )
        buy_breakout = sig.m15_close_prev1 > sig.m15_high_prev2
        if buy_ready and buy_breakout:
            return NtDirection.BUY

        sell_ready = (
            sig.rsi_h1 < self.RSI_SELL_MAX
            and sig.rsi_m30 < self.RSI_SELL_MAX
            and sig.rsi_m15_prev1 < self.RSI_SELL_MAX
        )
        sell_breakout = sig.m15_close_prev1 < sig.m15_low_prev2
        if sell_ready and sell_breakout:
            return NtDirection.SELL

        return NtDirection.NONE
