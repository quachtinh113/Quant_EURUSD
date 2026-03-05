from __future__ import annotations

from datetime import datetime, timezone


class Watchdog:
    def __init__(self, stale_seconds: int) -> None:
        self.stale_seconds = stale_seconds

    def stale(self, status: dict) -> bool:
        ts = status.get("ts")
        if not ts:
            return True
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return True
        return (datetime.now(timezone.utc) - dt).total_seconds() > self.stale_seconds
