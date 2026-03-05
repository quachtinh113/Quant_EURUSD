from datetime import datetime, timezone

from server.config import BotConfig
from server.models import RuntimeState
from server.risk_engine import RiskEngine


def test_spread_limit_and_adx_brake_for_dca() -> None:
    cfg = BotConfig(spread_limit_pips=2.0, adx_brake_h1=25.0)
    risk = RiskEngine(cfg)
    st = RuntimeState()

    assert risk.dca_allowed(spread_pips=1.8, adx_h1=20.0, state=st) is True
    assert risk.dca_allowed(spread_pips=2.1, adx_h1=20.0, state=st) is False
    assert risk.dca_allowed(spread_pips=1.5, adx_h1=26.0, state=st) is False


def test_daily_loss_limit_blocks_entries() -> None:
    cfg = BotConfig(daily_loss_limit_pct=6.0)
    risk = RiskEngine(cfg)
    st = RuntimeState()
    now = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)

    assert risk.daily_loss_blocked(st, balance=1000.0, now=now) is False
    assert risk.daily_loss_blocked(st, balance=939.0, now=now) is True
