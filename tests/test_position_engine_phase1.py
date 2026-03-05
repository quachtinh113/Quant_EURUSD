from datetime import datetime, timezone

from server.config import BotConfig
from server.models import RuntimeState
from server.position_engine import PositionEngine


def test_slot_lock_after_entry() -> None:
    cfg = BotConfig()
    pe = PositionEngine(cfg)
    st = RuntimeState()
    d = pe.enter_basket(st, side="BUY", price=1.1, now=datetime(2026, 1, 1, tzinfo=timezone.utc), window_id="20260101-07-A")

    assert d.action == "OPEN"
    assert st.last_window_id == "20260101-07-A"


def test_dca_spacing_and_ladder_limit() -> None:
    cfg = BotConfig()
    pe = PositionEngine(cfg)
    st = RuntimeState()
    pe.enter_basket(st, side="BUY", price=1.1000, now=datetime(2026, 1, 1, tzinfo=timezone.utc), window_id="w")
    basket = st.current_basket
    assert basket is not None

    assert pe.can_add_dca(basket, current_price=1.0984) is True
    assert pe.next_lot(basket) == 0.15
