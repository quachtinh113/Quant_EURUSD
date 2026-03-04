from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import MetaTrader5 as mt5

from nowtrading.indicator_math import adx_series, atr_series, rsi_series
from nowtrading.types import NtAccountState, NtDirection, NtOrder, NtPosition


TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


@dataclass(slots=True)
class Mt5ConnectionConfig:
    login: int
    password: str
    server: str
    terminal_path: str = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"


class Mt5BrokerAdapter:
    def __init__(self, connection: Mt5ConnectionConfig, symbol: str, magic: int = 3001001) -> None:
        self._connection = connection
        self._requested_symbol = symbol
        self.symbol = symbol
        self._magic = int(magic)
        self._connected = False

    def connect(self) -> bool:
        ok = mt5.initialize(
            path=self._connection.terminal_path,
            login=self._connection.login,
            password=self._connection.password,
            server=self._connection.server,
        )
        if not ok:
            return False
        resolved = self.resolve_symbol(self._requested_symbol)
        if resolved is None:
            mt5.shutdown()
            return False
        self.symbol = resolved
        self._connected = True
        return True

    @staticmethod
    def resolve_symbol(requested: str) -> str | None:
        info = mt5.symbol_info(requested)
        if info and mt5.symbol_select(requested, True):
            return requested
        candidates = mt5.symbols_get(f"{requested}*") or []
        for c in candidates:
            if mt5.symbol_select(c.name, True):
                return c.name
        return None

    @staticmethod
    def last_error() -> tuple[int, str]:
        return mt5.last_error()

    def shutdown(self) -> None:
        if self._connected:
            mt5.shutdown()
        self._connected = False

    def _rates(self, symbol: str, timeframe: str, bars: int) -> Any:
        tf = TIMEFRAME_MAP[timeframe]
        return mt5.copy_rates_from_pos(symbol, tf, 0, bars)

    @staticmethod
    def _ensure_value(values: list[float | None], shift: int) -> float:
        target = len(values) - shift - 1
        if target < 0 or target >= len(values):
            raise RuntimeError("Not enough bars for requested shift")
        value = values[target]
        if value is None:
            raise RuntimeError("Indicator value unavailable for requested shift")
        return float(value)

    def rsi(self, symbol: str, timeframe: str, period: int, shift: int) -> float:
        bars = max(period + shift + 120, 300)
        rates = self._rates(symbol, timeframe, bars)
        if rates is None or len(rates) == 0:
            raise RuntimeError("No rates data for RSI")
        closes = [float(r["close"]) for r in rates]
        values = rsi_series(closes, period)
        return self._ensure_value(values, shift)

    def adx(self, symbol: str, timeframe: str, period: int, shift: int) -> float:
        bars = max((period * 3) + shift + 120, 400)
        rates = self._rates(symbol, timeframe, bars)
        if rates is None or len(rates) == 0:
            raise RuntimeError("No rates data for ADX")
        highs = [float(r["high"]) for r in rates]
        lows = [float(r["low"]) for r in rates]
        closes = [float(r["close"]) for r in rates]
        values = adx_series(highs, lows, closes, period)
        return self._ensure_value(values, shift)

    def atr(self, symbol: str, timeframe: str, period: int, shift: int) -> float:
        bars = max(period + shift + 120, 300)
        rates = self._rates(symbol, timeframe, bars)
        if rates is None or len(rates) == 0:
            raise RuntimeError("No rates data for ATR")
        highs = [float(r["high"]) for r in rates]
        lows = [float(r["low"]) for r in rates]
        closes = [float(r["close"]) for r in rates]
        values = atr_series(highs, lows, closes, period)
        return self._ensure_value(values, shift)

    @staticmethod
    def bid(symbol: str) -> float:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick data")
        return float(tick.bid)

    @staticmethod
    def ask(symbol: str) -> float:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError("No tick data")
        return float(tick.ask)

    @staticmethod
    def point(symbol: str) -> float:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError("No symbol info")
        return float(info.point)

    @staticmethod
    def digits(symbol: str) -> int:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError("No symbol info")
        return int(info.digits)

    @staticmethod
    def volume_limits(symbol: str) -> tuple[float, float, float]:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError("No symbol info")
        return float(info.volume_min), float(info.volume_max), float(info.volume_step)

    @staticmethod
    def _send_with_fill_fallback(request: dict[str, Any]) -> bool:
        for fill_mode in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            payload = dict(request)
            payload["type_filling"] = fill_mode
            res = mt5.order_send(payload)
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                return True
        return False

    def place_market_order(
        self,
        direction: NtDirection,
        symbol: str,
        lots: float,
        stop_loss: float,
        comment: str,
    ) -> bool:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return False

        if direction == NtDirection.BUY:
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)
        elif direction == NtDirection.SELL:
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)
        else:
            return False

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lots),
            "type": order_type,
            "price": price,
            "sl": float(stop_loss) if stop_loss > 0 else 0.0,
            "deviation": 20,
            "magic": self._magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
        }
        return self._send_with_fill_fallback(request)

    def place_limit_order(
        self,
        direction: NtDirection,
        symbol: str,
        lots: float,
        price: float,
        stop_loss: float,
        comment: str,
    ) -> bool:
        if direction == NtDirection.BUY:
            order_type = mt5.ORDER_TYPE_BUY_LIMIT
        elif direction == NtDirection.SELL:
            order_type = mt5.ORDER_TYPE_SELL_LIMIT
        else:
            return False

        request = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": float(lots),
            "type": order_type,
            "price": float(price),
            "sl": float(stop_loss) if stop_loss > 0 else 0.0,
            "deviation": 20,
            "magic": self._magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }
        res = mt5.order_send(request)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    @staticmethod
    def get_positions(symbol: str, magic: int) -> list[NtPosition]:
        rows = mt5.positions_get(symbol=symbol) or []
        out: list[NtPosition] = []
        for p in rows:
            if int(p.magic) != int(magic):
                continue
            out.append(
                NtPosition(
                    ticket=int(p.ticket),
                    symbol=p.symbol,
                    magic=int(p.magic),
                    comment=p.comment or "",
                    volume=float(p.volume),
                    open_price=float(p.price_open),
                    open_time=datetime.fromtimestamp(int(p.time)),
                    profit=float(p.profit),
                )
            )
        return out

    @staticmethod
    def get_orders(symbol: str, magic: int) -> list[NtOrder]:
        rows = mt5.orders_get(symbol=symbol) or []
        out: list[NtOrder] = []
        for o in rows:
            if int(o.magic) != int(magic):
                continue
            out.append(
                NtOrder(
                    ticket=int(o.ticket),
                    symbol=o.symbol,
                    magic=int(o.magic),
                    comment=o.comment or "",
                )
            )
        return out

    def close_position(self, ticket: int, deviation_points: int) -> bool:
        rows = mt5.positions_get(ticket=ticket) or []
        if not rows:
            return False
        p = rows[0]
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None:
            return False

        if int(p.type) == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": p.symbol,
            "volume": float(p.volume),
            "type": order_type,
            "position": int(p.ticket),
            "price": price,
            "deviation": int(deviation_points),
            "magic": int(p.magic),
            "comment": p.comment or "NT_CLOSE",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        return self._send_with_fill_fallback(request)

    @staticmethod
    def cancel_order(ticket: int) -> bool:
        request = {"action": mt5.TRADE_ACTION_REMOVE, "order": int(ticket)}
        res = mt5.order_send(request)
        return res is not None and res.retcode == mt5.TRADE_RETCODE_DONE

    @staticmethod
    def account_state() -> NtAccountState:
        info = mt5.account_info()
        if info is None:
            raise RuntimeError("Account info unavailable")
        return NtAccountState(
            equity=float(info.equity),
            balance=float(info.balance),
            margin=float(info.margin),
            free_margin=float(info.margin_free),
        )

    @staticmethod
    def now() -> datetime:
        return datetime.now()
