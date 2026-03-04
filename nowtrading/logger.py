from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from nowtrading.interfaces import NtAccountSource
from nowtrading.types import NtDirection, NtLogLevel, NtRiskSnapshot, NtSignalSnapshot
from nowtrading.utils import nt_direction_to_string


class NtLogger:
    def __init__(self, account_source: NtAccountSource) -> None:
        self._account_source = account_source
        self._log_level = NtLogLevel.INFO
        self._symbol = ""
        self._file_name: Path | None = None
        self._digits = 5

    def init(self, log_level: int, symbol: str, digits: int, base_dir: str = ".") -> None:
        self._log_level = NtLogLevel(log_level)
        self._symbol = symbol
        self._digits = digits

        folder = Path(base_dir) / "NowTrading"
        folder.mkdir(parents=True, exist_ok=True)
        self._file_name = folder / f"{symbol}_basket_log.csv"

        if not self._file_name.exists():
            with self._file_name.open("w", newline="", encoding="utf-8") as fp:
                writer = csv.writer(fp)
                writer.writerow(
                    [
                        "timestamp",
                        "symbol",
                        "basket_id",
                        "event_type",
                        "direction",
                        "lots",
                        "price",
                        "rsi_h1",
                        "rsi_m30",
                        "rsi_m15_prev2",
                        "rsi_m15_prev1",
                        "rsi_h4",
                        "rsi_d1",
                        "adx_h1",
                        "atr_m15",
                        "spread",
                        "equity",
                        "free_margin",
                        "dd_daily",
                        "dd_floating",
                        "note",
                    ]
                )

    def log(
        self,
        level: NtLogLevel,
        event_type: str,
        basket_id: int,
        direction: NtDirection,
        lots: float,
        price: float,
        sig: NtSignalSnapshot,
        risk: NtRiskSnapshot,
        note: str,
    ) -> None:
        if level > self._log_level or self._file_name is None:
            return

        acct = self._account_source.account_state()
        with self._file_name.open("a", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    self._symbol,
                    str(basket_id),
                    event_type,
                    nt_direction_to_string(direction),
                    f"{lots:.2f}",
                    f"{price:.{self._digits}f}",
                    f"{sig.rsi_h1:.2f}",
                    f"{sig.rsi_m30:.2f}",
                    f"{sig.rsi_m15_prev2:.2f}",
                    f"{sig.rsi_m15_prev1:.2f}",
                    f"{sig.rsi_h4:.2f}",
                    f"{sig.rsi_d1:.2f}",
                    f"{sig.adx_h1:.2f}",
                    f"{sig.atr_m15:.{self._digits}f}",
                    f"{sig.spread_points:.1f}",
                    f"{acct.equity:.2f}",
                    f"{acct.free_margin:.2f}",
                    f"{risk.dd_daily_percent:.2f}",
                    f"{risk.dd_floating_percent:.2f}",
                    note,
                ]
            )

