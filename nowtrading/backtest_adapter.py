from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta

from nowtrading.indicator_math import adx_series, atr_series, rsi_series
from nowtrading.types import NtAccountState, NtDirection, NtOrder, NtPosition


@dataclass(slots=True)
class _TfSeries:
    times: list[datetime]
    highs: list[float]
    lows: list[float]
    closes: list[float]
    spreads: list[int]
    rsi14: list[float | None]
    adx14: list[float | None]
    atr14: list[float | None]


@dataclass(slots=True)
class _PendingOrder:
    ticket: int
    direction: NtDirection
    symbol: str
    magic: int
    comment: str
    volume: float
    price: float


@dataclass(slots=True)
class _SimPosition:
    ticket: int
    direction: NtDirection
    symbol: str
    magic: int
    comment: str
    volume: float
    open_price: float
    open_time: datetime


class BacktestAdapter:
    def __init__(
        self,
        symbol: str,
        magic: int,
        digits: int,
        point: float,
        contract_size: float,
        initial_balance: float,
        data: dict[str, _TfSeries],
    ) -> None:
        self._symbol = symbol
        self._magic = magic
        self._digits = digits
        self._point = point
        self._contract_size = contract_size
        self._data = data

        self._now = data["M1"].times[0] + timedelta(minutes=1)
        self._current_bid = data["M1"].closes[0]
        self._current_ask = data["M1"].closes[0] + max(1, data["M1"].spreads[0]) * point
        self._current_high = data["M1"].highs[0]
        self._current_low = data["M1"].lows[0]

        self._balance = initial_balance
        self._realized_profit = 0.0
        self._positions: list[_SimPosition] = []
        self._pending_orders: list[_PendingOrder] = []
        self._next_ticket = 1
        self._closed_positions = 0
        self._opened_positions = 0

    @property
    def realized_profit(self) -> float:
        return self._realized_profit

    @property
    def closed_positions(self) -> int:
        return self._closed_positions

    @property
    def opened_positions(self) -> int:
        return self._opened_positions

    def now(self) -> datetime:
        return self._now

    def digits(self, symbol: str) -> int:
        return self._digits

    def point(self, symbol: str) -> float:
        return self._point

    def bid(self, symbol: str) -> float:
        return self._current_bid

    def ask(self, symbol: str) -> float:
        return self._current_ask

    def volume_limits(self, symbol: str) -> tuple[float, float, float]:
        return 0.01, 100.0, 0.01

    def _floating_profit(self) -> float:
        total = 0.0
        for p in self._positions:
            if p.direction == NtDirection.BUY:
                total += (self._current_bid - p.open_price) * p.volume * self._contract_size
            else:
                total += (p.open_price - self._current_ask) * p.volume * self._contract_size
        return total

    def account_state(self) -> NtAccountState:
        floating = self._floating_profit()
        equity = self._balance + floating
        return NtAccountState(
            equity=equity,
            balance=self._balance,
            margin=0.0,
            free_margin=equity,
        )

    def _position_profit(self, p: _SimPosition) -> float:
        if p.direction == NtDirection.BUY:
            return (self._current_bid - p.open_price) * p.volume * self._contract_size
        return (p.open_price - self._current_ask) * p.volume * self._contract_size

    def get_positions(self, symbol: str, magic: int) -> list[NtPosition]:
        out: list[NtPosition] = []
        for p in self._positions:
            if p.symbol != symbol or p.magic != magic:
                continue
            out.append(
                NtPosition(
                    ticket=p.ticket,
                    symbol=p.symbol,
                    magic=p.magic,
                    comment=p.comment,
                    volume=p.volume,
                    open_price=p.open_price,
                    open_time=p.open_time,
                    profit=self._position_profit(p),
                )
            )
        return out

    def get_orders(self, symbol: str, magic: int) -> list[NtOrder]:
        out: list[NtOrder] = []
        for o in self._pending_orders:
            if o.symbol != symbol or o.magic != magic:
                continue
            out.append(NtOrder(ticket=o.ticket, symbol=o.symbol, magic=o.magic, comment=o.comment))
        return out

    def place_market_order(
        self,
        direction: NtDirection,
        symbol: str,
        lots: float,
        stop_loss: float,
        comment: str,
    ) -> bool:
        if direction == NtDirection.BUY:
            price = self._current_ask
        elif direction == NtDirection.SELL:
            price = self._current_bid
        else:
            return False

        self._positions.append(
            _SimPosition(
                ticket=self._next_ticket,
                direction=direction,
                symbol=symbol,
                magic=self._magic,
                comment=comment,
                volume=lots,
                open_price=price,
                open_time=self._now,
            )
        )
        self._next_ticket += 1
        self._opened_positions += 1
        return True

    def place_limit_order(
        self,
        direction: NtDirection,
        symbol: str,
        lots: float,
        price: float,
        stop_loss: float,
        comment: str,
    ) -> bool:
        self._pending_orders.append(
            _PendingOrder(
                ticket=self._next_ticket,
                direction=direction,
                symbol=symbol,
                magic=self._magic,
                comment=comment,
                volume=lots,
                price=price,
            )
        )
        self._next_ticket += 1
        return True

    def close_position(self, ticket: int, deviation_points: int) -> bool:
        for i, p in enumerate(self._positions):
            if p.ticket != ticket:
                continue
            pnl = self._position_profit(p)
            self._realized_profit += pnl
            self._balance += pnl
            self._closed_positions += 1
            del self._positions[i]
            return True
        return False

    def cancel_order(self, ticket: int) -> bool:
        for i, o in enumerate(self._pending_orders):
            if o.ticket == ticket:
                del self._pending_orders[i]
                return True
        return False

    def _tf_indicator(self, timeframe: str, name: str, shift: int) -> float:
        tf = self._data[timeframe]
        idx = bisect_left(tf.times, self._now) - 1
        target = idx - (shift - 1)
        if target < 0:
            raise RuntimeError("Not enough history")
        arr = tf.rsi14 if name == "rsi" else tf.adx14 if name == "adx" else tf.atr14
        value = arr[target]
        if value is None:
            raise RuntimeError("Indicator value unavailable")
        return value

    def rsi(self, symbol: str, timeframe: str, period: int, shift: int) -> float:
        if period != 14:
            raise RuntimeError("Backtest adapter supports period=14 only")
        return self._tf_indicator(timeframe, "rsi", shift)

    def adx(self, symbol: str, timeframe: str, period: int, shift: int) -> float:
        if period != 14:
            raise RuntimeError("Backtest adapter supports period=14 only")
        return self._tf_indicator(timeframe, "adx", shift)

    def atr(self, symbol: str, timeframe: str, period: int, shift: int) -> float:
        if period != 14:
            raise RuntimeError("Backtest adapter supports period=14 only")
        return self._tf_indicator(timeframe, "atr", shift)

    def _process_pending_orders(self) -> None:
        if not self._pending_orders:
            return
        remaining: list[_PendingOrder] = []
        for o in self._pending_orders:
            filled = False
            if o.direction == NtDirection.BUY and self._current_low <= o.price:
                self._positions.append(
                    _SimPosition(
                        ticket=o.ticket,
                        direction=o.direction,
                        symbol=o.symbol,
                        magic=o.magic,
                        comment=o.comment,
                        volume=o.volume,
                        open_price=o.price,
                        open_time=self._now,
                    )
                )
                self._opened_positions += 1
                filled = True
            elif o.direction == NtDirection.SELL and self._current_high >= o.price:
                self._positions.append(
                    _SimPosition(
                        ticket=o.ticket,
                        direction=o.direction,
                        symbol=o.symbol,
                        magic=o.magic,
                        comment=o.comment,
                        volume=o.volume,
                        open_price=o.price,
                        open_time=self._now,
                    )
                )
                self._opened_positions += 1
                filled = True
            if not filled:
                remaining.append(o)
        self._pending_orders = remaining

    def advance_to_m1_index(self, i: int) -> None:
        m1 = self._data["M1"]
        self._now = m1.times[i] + timedelta(minutes=1)
        self._current_high = m1.highs[i]
        self._current_low = m1.lows[i]
        self._current_bid = m1.closes[i]
        spread_points = max(1, int(m1.spreads[i]))
        self._current_ask = self._current_bid + (spread_points * self._point)
        self._process_pending_orders()

    def force_close_all(self) -> None:
        for p in list(self._positions):
            self.close_position(p.ticket, 0)
        self._pending_orders.clear()

    @staticmethod
    def from_mt5_rates(
        symbol: str,
        magic: int,
        digits: int,
        point: float,
        contract_size: float,
        initial_balance: float,
        mt5_rates: dict[str, list[dict[str, float | int]]],
    ) -> "BacktestAdapter":
        data: dict[str, _TfSeries] = {}
        for tf, rows in mt5_rates.items():
            times = [datetime.fromtimestamp(int(r["time"])) for r in rows]
            highs = [float(r["high"]) for r in rows]
            lows = [float(r["low"]) for r in rows]
            closes = [float(r["close"]) for r in rows]
            spreads = [int(r.get("spread", 10)) for r in rows]
            data[tf] = _TfSeries(
                times=times,
                highs=highs,
                lows=lows,
                closes=closes,
                spreads=spreads,
                rsi14=rsi_series(closes, 14),
                adx14=adx_series(highs, lows, closes, 14),
                atr14=atr_series(highs, lows, closes, 14),
            )
        return BacktestAdapter(
            symbol=symbol,
            magic=magic,
            digits=digits,
            point=point,
            contract_size=contract_size,
            initial_balance=initial_balance,
            data=data,
        )

