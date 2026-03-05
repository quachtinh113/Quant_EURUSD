from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


VN_TZ = timezone(timedelta(hours=7))


@dataclass(slots=True)
class WindowResult:
    in_window: bool
    window_id: str


class TimeEngine:
    def __init__(self, session_start_vn: int = 7, session_end_vn: int = 15) -> None:
        self.session_start_vn = session_start_vn
        self.session_end_vn = session_end_vn

    def to_vn(self, now_utc: datetime) -> datetime:
        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(tzinfo=timezone.utc)
        return now_utc.astimezone(VN_TZ)

    def in_session(self, now_utc: datetime) -> bool:
        vn = self.to_vn(now_utc)
        return self.session_start_vn <= vn.hour < self.session_end_vn

    def in_entry_window(self, now_utc: datetime) -> WindowResult:
        vn = self.to_vn(now_utc)
        minute = vn.minute
        in_window = (1 <= minute <= 3) or (31 <= minute <= 33)
        slot = "A" if minute < 30 else "B"
        return WindowResult(in_window=in_window, window_id=f"{vn:%Y%m%d-%H}-{slot}")
