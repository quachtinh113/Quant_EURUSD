from __future__ import annotations

from datetime import datetime
from typing import Callable

from nowtrading.interfaces import NtAccountSource
from nowtrading.types import NtRiskSnapshot


class NtRiskGuard:
    def __init__(
        self,
        account_source: NtAccountSource,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._account_source = account_source
        self._now_provider = now_provider or datetime.now
        self._day_start_equity = 0.0
        self._day_of_year = -1

    def init(self) -> None:
        now = self._now_provider()
        self._day_of_year = now.timetuple().tm_yday
        self._day_start_equity = self._account_source.account_state().equity

    def on_tick_rollover_check(self) -> None:
        now = self._now_provider()
        if now.timetuple().tm_yday != self._day_of_year:
            self._day_of_year = now.timetuple().tm_yday
            self._day_start_equity = self._account_source.account_state().equity

    def _is_news_blackout(
        self, enabled: bool, minutes_before_after: int, manual_news_time: datetime | None
    ) -> bool:
        if not enabled or manual_news_time is None:
            return False
        delta_sec = abs((self._now_provider() - manual_news_time).total_seconds())
        return delta_sec <= minutes_before_after * 60

    @staticmethod
    def _correlation_guard_blocks(enabled: bool) -> bool:
        if not enabled:
            return False
        return False

    def evaluate(
        self,
        max_daily_dd: float,
        max_float_dd: float,
        min_free_margin_pct: float,
        consecutive_losses: int,
        max_consecutive_losses: int,
        news_enabled: bool,
        news_window_minutes: int,
        manual_news_time: datetime | None,
        correlation_enabled: bool,
    ) -> NtRiskSnapshot:
        acct = self._account_source.account_state()
        s = NtRiskSnapshot(consecutive_losing_baskets=consecutive_losses)

        s.dd_daily_percent = (
            max(
                0.0, (self._day_start_equity - acct.equity) / self._day_start_equity * 100.0
            )
            if self._day_start_equity > 0.0
            else 0.0
        )
        s.dd_floating_percent = (
            max(0.0, (acct.balance - acct.equity) / acct.balance * 100.0)
            if acct.balance > 0.0
            else 0.0
        )
        used_margin = acct.margin + acct.free_margin
        s.free_margin_percent = (
            acct.free_margin / used_margin * 100.0 if used_margin > 0.0 else 100.0
        )

        reasons: list[str] = []
        if s.dd_daily_percent > max_daily_dd:
            s.block_new_entries = True
            reasons.append("daily_dd")
        if s.dd_floating_percent > max_float_dd:
            s.block_new_entries = True
            reasons.append("float_dd")
        if consecutive_losses >= max_consecutive_losses:
            s.block_new_entries = True
            reasons.append("consecutive_losses")
        if self._is_news_blackout(news_enabled, news_window_minutes, manual_news_time):
            s.block_new_entries = True
            reasons.append("news_blackout")
        if self._correlation_guard_blocks(correlation_enabled):
            s.block_new_entries = True
            reasons.append("correlation")

        if s.dd_floating_percent > 6.0:
            s.block_dca = True
            reasons.append("dca_float_dd")
        if s.free_margin_percent < min_free_margin_pct:
            s.block_dca = True
            reasons.append("dca_free_margin")

        s.reason = ";".join(reasons) + (";" if reasons else "")
        return s
