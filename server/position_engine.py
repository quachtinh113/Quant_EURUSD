from __future__ import annotations

from datetime import datetime

from server.config import BotConfig
from server.models import Basket, BotState, Decision, RuntimeState


class PositionEngine:
    def __init__(self, cfg: BotConfig) -> None:
        self.cfg = cfg

    def basket_profit_hit(self, basket: Basket) -> bool:
        return basket.realized_pnl_usd + basket.floating_pnl_usd >= self.cfg.basket_tp_usd

    def next_lot(self, basket: Basket | None) -> float:
        idx = 0 if basket is None else basket.order_count
        if idx >= len(self.cfg.lot_ladder):
            return 0.0
        return float(self.cfg.lot_ladder[idx])

    def can_add_dca(self, basket: Basket, current_price: float) -> bool:
        if basket.order_count >= self.cfg.max_orders_total:
            return False
        if basket.total_lot >= self.cfg.max_total_lot:
            return False
        if basket.side == "BUY":
            return (basket.last_fill_price - current_price) >= self.cfg.spacing_pips * 0.0001
        return (current_price - basket.last_fill_price) >= self.cfg.spacing_pips * 0.0001

    def enter_basket(self, state: RuntimeState, side: str, price: float, now: datetime, window_id: str) -> Decision:
        basket = Basket(
            basket_id=f"B{now:%Y%m%d%H%M%S}",
            side=side,
            open_time=now,
            first_entry_price=price,
            last_fill_price=price,
            total_lot=self.cfg.lot_ladder[0],
            order_count=1,
        )
        state.current_basket = basket
        state.state = BotState.IN_BASKET
        state.last_window_id = window_id
        return Decision(action="OPEN", reason="entry_signal", side=side, lot=self.cfg.lot_ladder[0], window_id=window_id, basket_id=basket.basket_id)

    def close_basket(self, state: RuntimeState, reason: str) -> Decision:
        basket_id = state.current_basket.basket_id if state.current_basket else ""
        state.current_basket = None
        state.state = BotState.COOLDOWN
        return Decision(action="CLOSE_ALL", reason=reason, basket_id=basket_id)
