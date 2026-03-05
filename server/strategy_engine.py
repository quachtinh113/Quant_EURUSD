from __future__ import annotations


class StrategyEngine:
    """Placeholder strategy (replaceable): RSI threshold on M15."""

    def decide_side(self, rsi_m15: float) -> str:
        if rsi_m15 <= 30:
            return "BUY"
        if rsi_m15 >= 70:
            return "SELL"
        return "NONE"
