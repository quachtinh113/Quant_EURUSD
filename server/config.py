from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class BotConfig:
    symbol: str = "EURUSD"
    session_start_vn: int = 7
    session_end_vn: int = 15
    entry_windows: tuple[tuple[int, int], ...] = ((1, 3), (31, 33))
    basket_tp_usd: float = 10.0
    max_orders_total: int = 6
    spacing_pips: float = 15.0
    lot_ladder: list[float] = field(default_factory=lambda: [0.10, 0.15, 0.20, 0.20, 0.25, 0.30])
    max_total_lot: float = 1.20
    spread_limit_pips: float = 2.0
    adx_brake_h1: float = 25.0
    kill_switch_mae_pips: float = 60.0
    cooldown_minutes: int = 120
    daily_loss_limit_pct: float = 6.0
    max_baskets: int = 1
    heartbeat_stale_seconds: int = 20
    bridge_dir: str = "bridge"
    magic_number: int = 26032026


def _simple_yaml_parse(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line or ":" not in line:
            continue
        key, value = [x.strip() for x in line.split(":", 1)]
        if value.startswith("[") and value.endswith("]"):
            vals = [v.strip() for v in value[1:-1].split(",") if v.strip()]
            data[key] = [float(v) if "." in v else int(v) for v in vals]
        elif value.lower() in {"true", "false"}:
            data[key] = value.lower() == "true"
        else:
            try:
                data[key] = float(value) if "." in value else int(value)
            except ValueError:
                data[key] = value.strip('"')
    return data


def load_config(path: str | Path) -> BotConfig:
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    parsed: dict[str, Any]
    try:
        import yaml  # type: ignore

        parsed = yaml.safe_load(raw) or {}
    except Exception:
        parsed = _simple_yaml_parse(raw)

    cfg = BotConfig()
    for key, value in parsed.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg
