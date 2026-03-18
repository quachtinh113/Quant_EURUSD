from __future__ import annotations

from datetime import datetime
from typing import Callable


class NtTimeEngine:
    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or datetime.now
        self.last_entry_block_key = -1
        self.daily_baskets = 0
        self.last_day_of_year = -1

    def init(self) -> None:
        self.last_entry_block_key = -1
        self.daily_baskets = 0
        self.last_day_of_year = -1

    def on_tick_rollover_check(self) -> None:
        now = self._now_provider()
        if self.last_day_of_year != now.timetuple().tm_yday:
            self.last_day_of_year = now.timetuple().tm_yday
            self.daily_baskets = 0
            self.last_entry_block_key = -1

    def is_entry_minute(self) -> bool:
        now = self._now_provider()
        return now.minute in (1, 31)

    def is_session_allowed(self, enabled: bool, start_hour: int, end_hour: int) -> bool:
        if not enabled:
            return True
        hour = self._now_provider().hour
        if start_hour <= end_hour:
            return start_hour <= hour < end_hour
        return hour >= start_hour or hour < end_hour

    def current_block_key(self) -> int:
        now = self._now_provider()
        day = now.timetuple().tm_yday
        half_hour_slot = now.hour * 2 + (1 if now.minute >= 30 else 0)
        return now.year * 100000 + day * 100 + half_hour_slot

    def can_open_in_current_block(self, daily_max_baskets: int) -> bool:
        if self.daily_baskets >= daily_max_baskets:
            return False
        return self.current_block_key() != self.last_entry_block_key

    def mark_basket_opened(self) -> None:
        self.last_entry_block_key = self.current_block_key()
        self.daily_baskets += 1
