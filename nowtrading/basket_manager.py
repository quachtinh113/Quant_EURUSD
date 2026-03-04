from __future__ import annotations

from nowtrading.interfaces import NtBroker
from nowtrading.types import NtBasketState, NtDirection
from nowtrading.utils import nt_build_basket_comment, nt_normalize_volume, nt_parse_basket_comment


class NtBasketManager:
    def __init__(
        self,
        broker: NtBroker,
        symbol: str,
        magic: int,
        deviation_points: int,
        retry_count: int = 3,
    ) -> None:
        self._broker = broker
        self._symbol = symbol
        self._magic = magic
        self._deviation_points = deviation_points
        self._retry_count = retry_count

    def build_basket_id(self) -> int:
        return int(self._broker.now().timestamp())

    def _retry_market_order(
        self, direction: NtDirection, lots: float, comment: str, safety_sl_price: float
    ) -> bool:
        for _ in range(self._retry_count):
            if self._broker.place_market_order(
                direction=direction,
                symbol=self._symbol,
                lots=lots,
                stop_loss=safety_sl_price if safety_sl_price > 0 else 0.0,
                comment=comment,
            ):
                return True
        return False

    def open_initial_basket(
        self,
        basket_id: int,
        direction: NtDirection,
        base_lots_total: float,
        use_pending: bool,
        pending_lots: float,
        pending_offset_pips: float,
        safety_sl_pips: float,
    ) -> bool:
        min_vol, max_vol, step = self._broker.volume_limits(self._symbol)
        digits = self._broker.digits(self._symbol)
        point = self._broker.point(self._symbol)

        each = nt_normalize_volume(base_lots_total / 2.0, min_vol, max_vol, step)
        pending = nt_normalize_volume(pending_lots, min_vol, max_vol, step)
        comment = nt_build_basket_comment(basket_id, direction)
        bid = self._broker.bid(self._symbol)
        ask = self._broker.ask(self._symbol)
        pip = point * (10.0 if digits in (3, 5) else 1.0)

        sl = 0.0
        if safety_sl_pips > 0.0:
            if direction == NtDirection.BUY:
                sl = bid - safety_sl_pips * pip
            elif direction == NtDirection.SELL:
                sl = ask + safety_sl_pips * pip

        if not self._retry_market_order(direction, each, comment, sl):
            return False
        if not self._retry_market_order(direction, each, comment, sl):
            return False

        if use_pending and pending > 0.0:
            for _ in range(self._retry_count):
                if direction == NtDirection.BUY:
                    price = round(ask - pending_offset_pips * pip, digits)
                else:
                    price = round(bid + pending_offset_pips * pip, digits)
                ok = self._broker.place_limit_order(
                    direction=direction,
                    symbol=self._symbol,
                    lots=pending,
                    price=price,
                    stop_loss=sl if sl > 0 else 0.0,
                    comment=comment,
                )
                if ok:
                    break
            else:
                return False

        return True

    def get_active_basket(self) -> NtBasketState:
        state = NtBasketState()
        weighted_notional = 0.0
        latest_open_time = None

        positions = self._broker.get_positions(self._symbol, self._magic)
        if not positions:
            return state

        for pos in positions:
            basket_id, direction = nt_parse_basket_comment(pos.comment)
            if basket_id is None or direction == NtDirection.NONE:
                continue

            state.active = True
            state.basket_id = basket_id
            state.direction = direction

            if state.first_open_time is None or pos.open_time < state.first_open_time:
                state.first_open_time = pos.open_time
            if latest_open_time is None or pos.open_time >= latest_open_time:
                latest_open_time = pos.open_time
                state.last_filled_price = pos.open_price

            weighted_notional += pos.open_price * pos.volume
            state.total_lots += pos.volume
            state.floating_profit += pos.profit
            state.position_count += 1

        if state.active and state.total_lots > 0.0:
            state.weighted_avg_price = weighted_notional / state.total_lots
            state.dca_count = max(0, state.position_count - 2)
        return state

    def close_basket(self, basket_id: int) -> bool:
        ok = True
        positions = self._broker.get_positions(self._symbol, self._magic)
        for pos in positions:
            pos_basket_id, _ = nt_parse_basket_comment(pos.comment)
            if pos_basket_id != basket_id:
                continue
            if not self._broker.close_position(pos.ticket, self._deviation_points):
                ok = False

        orders = self._broker.get_orders(self._symbol, self._magic)
        for order in orders:
            order_basket_id, _ = nt_parse_basket_comment(order.comment)
            if order_basket_id != basket_id:
                continue
            if not self._broker.cancel_order(order.ticket):
                ok = False
        return ok

    def add_dca(
        self, basket_id: int, direction: NtDirection, lots: float, safety_sl_pips: float
    ) -> bool:
        min_vol, max_vol, step = self._broker.volume_limits(self._symbol)
        digits = self._broker.digits(self._symbol)
        point = self._broker.point(self._symbol)
        bid = self._broker.bid(self._symbol)
        ask = self._broker.ask(self._symbol)
        pip = point * (10.0 if digits in (3, 5) else 1.0)

        sl = 0.0
        if safety_sl_pips > 0.0:
            if direction == NtDirection.BUY:
                sl = bid - safety_sl_pips * pip
            else:
                sl = ask + safety_sl_pips * pip

        return self._retry_market_order(
            direction=direction,
            lots=nt_normalize_volume(lots, min_vol, max_vol, step),
            comment=nt_build_basket_comment(basket_id, direction),
            safety_sl_price=sl,
        )
