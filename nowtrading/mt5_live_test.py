from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import MetaTrader5 as mt5


def write_log(log_path: Path, message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"[{timestamp}] {message}\n")


def resolve_symbol(requested: str) -> str | None:
    info = mt5.symbol_info(requested)
    if info and mt5.symbol_select(requested, True):
        return requested

    candidates = mt5.symbols_get(f"{requested}*") or []
    for candidate in candidates:
        if mt5.symbol_select(candidate.name, True):
            return candidate.name

    return None


def send_market_order(
    symbol: str,
    lot: float,
    side: int,
    magic: int,
    comment: str,
    position_ticket: int | None = None,
) -> mt5.OrderSendResult:
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise RuntimeError(f"Cannot get tick for symbol {symbol}")

    price = tick.ask if side == mt5.ORDER_TYPE_BUY else tick.bid
    fill_modes = [mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN]
    last_result = None

    for fill_mode in fill_modes:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": side,
            "price": price,
            "deviation": 20,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fill_mode,
        }
        if position_ticket is not None:
            request["position"] = position_ticket
        last_result = mt5.order_send(request)
        if last_result is not None and last_result.retcode == mt5.TRADE_RETCODE_DONE:
            return last_result

    if last_result is None:
        raise RuntimeError("order_send returned None")
    return last_result


def find_open_position(symbol: str, magic: int, comment: str, deal_ticket: int | None):
    if deal_ticket:
        deal_rows = mt5.history_deals_get(ticket=deal_ticket) or []
        if deal_rows:
            position_id = deal_rows[0].position_id
            pos_rows = mt5.positions_get(ticket=position_id) or []
            if pos_rows:
                return pos_rows[0]

    positions = mt5.positions_get(symbol=symbol) or []
    for pos in positions:
        if pos.magic == magic and (pos.comment == comment or not pos.comment):
            return pos
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live MT5 open/close test.")
    parser.add_argument("--login", required=True, type=int)
    parser.add_argument("--password", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument(
        "--terminal-path",
        default=r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    )
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--hold-seconds", type=int, default=5)
    parser.add_argument("--magic", type=int, default=9026001)
    parser.add_argument("--log-path", default="nowtrading/mt5_live_test.log")
    args = parser.parse_args()

    log_path = Path(args.log_path)
    write_log(log_path, "Starting MT5 live test runner")

    initialized = mt5.initialize(
        path=args.terminal_path,
        login=args.login,
        password=args.password,
        server=args.server,
    )
    if not initialized:
        write_log(log_path, f"MT5 initialize failed: {mt5.last_error()}")
        return 1

    try:
        info = mt5.account_info()
        if info is None:
            write_log(log_path, "Account info is None after initialize")
            return 1
        write_log(log_path, f"Connected account={info.login} server={info.server}")

        symbol = resolve_symbol(args.symbol)
        if symbol is None:
            write_log(log_path, f"Cannot resolve tradable symbol for {args.symbol}")
            return 1
        write_log(log_path, f"Using symbol={symbol}, lot={args.lot:.2f}")

        comment = f"NT_PY_TEST_{int(time.time())}"
        open_result = send_market_order(
            symbol=symbol,
            lot=args.lot,
            side=mt5.ORDER_TYPE_BUY,
            magic=args.magic,
            comment=comment,
        )
        write_log(
            log_path,
            f"Open order retcode={open_result.retcode} order={open_result.order} deal={open_result.deal}",
        )
        if open_result.retcode != mt5.TRADE_RETCODE_DONE:
            if open_result.retcode == mt5.TRADE_RETCODE_CLIENT_DISABLES_AT:
                write_log(log_path, "Client terminal blocks algo trading (AutoTrading/Python API disabled)")
            return 1

        time.sleep(max(1, args.hold_seconds))

        position = find_open_position(
            symbol=symbol,
            magic=args.magic,
            comment=comment,
            deal_ticket=getattr(open_result, "deal", None),
        )
        if position is None:
            write_log(log_path, "Open position not found for close step")
            return 1

        close_result = send_market_order(
            symbol=symbol,
            lot=position.volume,
            side=mt5.ORDER_TYPE_SELL,
            magic=args.magic,
            comment=comment,
            position_ticket=position.ticket,
        )
        write_log(
            log_path,
            f"Close order retcode={close_result.retcode} order={close_result.order} deal={close_result.deal}",
        )
        write_log(log_path, "Live test completed successfully")
        return 0
    finally:
        mt5.shutdown()
        write_log(log_path, "MT5 shutdown complete")


if __name__ == "__main__":
    sys.exit(main())
