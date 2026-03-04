from __future__ import annotations

from nowtrading.types import NtDirection


def nt_pip_size(digits: int, point: float) -> float:
    if digits in (3, 5):
        return point * 10.0
    return point


def nt_pips_to_price(digits: int, point: float, pips: float) -> float:
    return pips * nt_pip_size(digits, point)


def nt_normalize_volume(
    volume: float, min_vol: float, max_vol: float, step: float
) -> float:
    clamped = max(min_vol, min(max_vol, volume))
    steps = round(clamped / step)
    return round(steps * step, 2)


def nt_direction_to_string(direction: NtDirection) -> str:
    if direction == NtDirection.BUY:
        return "BUY"
    if direction == NtDirection.SELL:
        return "SELL"
    return "NONE"


def nt_build_basket_comment(basket_id: int, direction: NtDirection) -> str:
    return f"NTB|{basket_id}|{nt_direction_to_string(direction)}"


def nt_parse_basket_comment(comment: str) -> tuple[int | None, NtDirection]:
    if not comment.startswith("NTB|"):
        return None, NtDirection.NONE
    parts = comment.split("|")
    if len(parts) < 3:
        return None, NtDirection.NONE
    try:
        basket_id = int(parts[1])
    except ValueError:
        return None, NtDirection.NONE
    side = parts[2]
    if side == "BUY":
        return basket_id, NtDirection.BUY
    if side == "SELL":
        return basket_id, NtDirection.SELL
    return None, NtDirection.NONE

