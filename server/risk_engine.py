from __future__ import annotations

from datetime import datetime, timedelta

from server.config import BotConfig
from server.models import RuntimeState


class RiskEngine:
    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg

    def daily_loss_blocked(self, state: RuntimeState, balance: float, now: datetime) -> bool:
        day_key = now.strftime("%Y-%m-%d")
        if state.day_key != day_key:
            state.day_key = day_key
            state.day_start_balance = balance
            state.blocked_for_day = False
        if state.day_start_balance <= 0:
            return False
        dd_pct = max(0.0, (state.day_start_balance - balance) / state.day_start_balance * 100.0)
        if dd_pct >= self.cfg.daily_loss_limit_pct:
            state.blocked_for_day = True
        return state.blocked_for_day

    def check_spread(self, spread_pips: float) -> bool:
        return spread_pips <= self.cfg.spread_limit_pips

    def dca_allowed(self, spread_pips: float, adx_h1: float, state: RuntimeState) -> bool:
        if state.disable_dca:
            return False
        return self.check_spread(spread_pips) and adx_h1 <= self.cfg.adx_brake_h1

    def kill_switch_hit(self, mae_pips: float) -> bool:
        return mae_pips >= self.cfg.kill_switch_mae_pips

    def set_cooldown(self, state: RuntimeState, now: datetime) -> None:
        state.cooldown_until = now + timedelta(minutes=self.cfg.cooldown_minutes)
