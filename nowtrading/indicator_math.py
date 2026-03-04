from __future__ import annotations

from typing import Iterable


def rsi_series(closes: Iterable[float], period: int) -> list[float | None]:
    values = list(closes)
    n = len(values)
    if n == 0 or period <= 0:
        return [None] * n

    out: list[float | None] = [None] * n
    if n <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses += -delta

    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

    for i in range(period + 1, n):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
    return out


def atr_series(highs: Iterable[float], lows: Iterable[float], closes: Iterable[float], period: int) -> list[float | None]:
    h = list(highs)
    l = list(lows)
    c = list(closes)
    n = min(len(h), len(l), len(c))
    out: list[float | None] = [None] * n
    if n == 0 or period <= 0 or n < period:
        return out

    tr = [0.0] * n
    for i in range(n):
        if i == 0:
            tr[i] = h[i] - l[i]
        else:
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

    atr = sum(tr[:period]) / period
    out[period - 1] = atr
    for i in range(period, n):
        atr = (atr * (period - 1) + tr[i]) / period
        out[i] = atr
    return out


def adx_series(highs: Iterable[float], lows: Iterable[float], closes: Iterable[float], period: int) -> list[float | None]:
    h = list(highs)
    l = list(lows)
    c = list(closes)
    n = min(len(h), len(l), len(c))
    out: list[float | None] = [None] * n
    if n < (period * 2) or period <= 0:
        return out

    tr = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    for i in range(1, n):
        up_move = h[i] - h[i - 1]
        down_move = l[i - 1] - l[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > 0 else 0.0
        minus_dm[i] = down_move if down_move > up_move and down_move > 0 else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

    tr14 = sum(tr[1 : period + 1])
    plus14 = sum(plus_dm[1 : period + 1])
    minus14 = sum(minus_dm[1 : period + 1])

    dx: list[float | None] = [None] * n
    for i in range(period, n):
        if i > period:
            tr14 = tr14 - (tr14 / period) + tr[i]
            plus14 = plus14 - (plus14 / period) + plus_dm[i]
            minus14 = minus14 - (minus14 / period) + minus_dm[i]

        if tr14 == 0:
            continue
        plus_di = 100.0 * (plus14 / tr14)
        minus_di = 100.0 * (minus14 / tr14)
        denom = plus_di + minus_di
        if denom == 0:
            continue
        dx[i] = 100.0 * abs(plus_di - minus_di) / denom

    first_adx_index = (period * 2) - 1
    first_window = [v for v in dx[period:first_adx_index + 1] if v is not None]
    if len(first_window) < period:
        return out

    adx = sum(first_window) / period
    out[first_adx_index] = adx
    for i in range(first_adx_index + 1, n):
        if dx[i] is None:
            out[i] = adx
            continue
        adx = ((adx * (period - 1)) + dx[i]) / period
        out[i] = adx
    return out

