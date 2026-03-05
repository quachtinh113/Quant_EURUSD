from datetime import datetime

from nowtrading.dca_engine import NtDcaEngine
from nowtrading.signal_gate import NtSignalGate
from nowtrading.time_engine import NtTimeEngine
from nowtrading.types import NtBasketState, NtDirection, NtSignalSnapshot


class DummyPriceSource:
    def __init__(self, bid_value: float, ask_value: float, point_value: float = 0.00001):
        self._bid = bid_value
        self._ask = ask_value
        self._point = point_value

    def bid(self, symbol: str) -> float:  # noqa: ARG002
        return self._bid

    def ask(self, symbol: str) -> float:  # noqa: ARG002
        return self._ask

    def point(self, symbol: str) -> float:  # noqa: ARG002
        return self._point


def test_signal_gate_buy_and_sell_paths() -> None:
    gate = NtSignalGate()

    buy_sig = NtSignalSnapshot(
        rsi_h1=55,
        rsi_m30=57,
        rsi_m15_prev1=56,
        m15_close_prev1=1.1021,
        m15_high_prev2=1.1019,
        spread_points=10,
    )
    assert gate.evaluate(buy_sig, max_spread_points=20) == NtDirection.BUY

    sell_sig = NtSignalSnapshot(
        rsi_h1=45,
        rsi_m30=43,
        rsi_m15_prev1=44,
        m15_close_prev1=1.1010,
        m15_low_prev2=1.1012,
        spread_points=10,
    )
    assert gate.evaluate(sell_sig, max_spread_points=20) == NtDirection.SELL


def test_time_engine_blocks_repeat_entries_in_same_half_hour_block() -> None:
    now = datetime(2026, 3, 1, 10, 1)
    engine = NtTimeEngine(now_provider=lambda: now)

    assert engine.is_entry_minute() is True
    assert engine.can_open_in_current_block(daily_max_baskets=3) is True

    engine.mark_basket_opened()
    assert engine.can_open_in_current_block(daily_max_baskets=3) is False


def test_dca_engine_spacing_trigger_for_buy_and_sell() -> None:
    buy_source = DummyPriceSource(bid_value=1.0988, ask_value=1.0990)
    buy_engine = NtDcaEngine(source=buy_source, symbol="EURUSD", digits=5)
    buy_basket = NtBasketState(active=True, direction=NtDirection.BUY, last_filled_price=1.1000)
    assert buy_engine.should_add(buy_basket, spacing_pips=10) is True

    sell_source = DummyPriceSource(bid_value=1.1010, ask_value=1.1012)
    sell_engine = NtDcaEngine(source=sell_source, symbol="EURUSD", digits=5)
    sell_basket = NtBasketState(active=True, direction=NtDirection.SELL, last_filled_price=1.1000)
    assert sell_engine.should_add(sell_basket, spacing_pips=10) is True
