from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

from nowtrading.ea import NowTradingBasketEA, NtEaConfig
from nowtrading.mt5_adapter import Mt5BrokerAdapter, Mt5ConnectionConfig
from nowtrading.types import NtLogLevel, NtTpMode


def write_log(log_path: Path, message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fp:
        fp.write(f"[{ts}] {message}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NowTrading EA live on MT5.")
    parser.add_argument("--login", required=True, type=int)
    parser.add_argument("--password", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument(
        "--terminal-path",
        default=r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    )
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--base-lots", type=float, default=0.01)
    parser.add_argument("--pending-lots", type=float, default=0.0)
    parser.add_argument("--dca-lots", type=float, default=0.01)
    parser.add_argument("--target-profit-usd", type=float, default=10.0)
    parser.add_argument("--tp-mode", choices=("money", "atr"), default="money")
    parser.add_argument("--atr-multiplier-tp", type=float, default=1.5)
    parser.add_argument("--loop-seconds", type=float, default=1.0)
    parser.add_argument("--duration-minutes", type=float, default=0.0)
    parser.add_argument("--magic", type=int, default=3001001)
    parser.add_argument("--max-spread-points", type=int, default=25)
    parser.add_argument("--disable-session-filter", action="store_true")
    parser.add_argument("--log-level", choices=("error", "info", "debug"), default="info")
    parser.add_argument("--log-path", default="nowtrading/live_runner.log")
    args = parser.parse_args()

    log_path = Path(args.log_path)
    write_log(log_path, "Starting live runner")

    conn = Mt5ConnectionConfig(
        login=args.login,
        password=args.password,
        server=args.server,
        terminal_path=args.terminal_path,
    )
    adapter = Mt5BrokerAdapter(connection=conn, symbol=args.symbol, magic=args.magic)
    if not adapter.connect():
        write_log(log_path, f"MT5 connect failed: {adapter.last_error()}")
        return 1

    try:
        config = NtEaConfig()
        config.magic = args.magic
        config.base_lots_total = args.base_lots
        config.pending_lots = args.pending_lots
        config.use_pending_limit = args.pending_lots > 0.0
        config.dca_lots = args.dca_lots
        config.max_spread_points = args.max_spread_points
        config.target_profit_usd = args.target_profit_usd
        config.tp_mode = NtTpMode.MONEY if args.tp_mode == "money" else NtTpMode.ATR
        config.atr_multiplier_tp = args.atr_multiplier_tp
        if args.disable_session_filter:
            config.enable_london_ny_only = False

        config.log_level = (
            NtLogLevel.DEBUG
            if args.log_level == "debug"
            else NtLogLevel.INFO
            if args.log_level == "info"
            else NtLogLevel.ERROR
        )

        ea = NowTradingBasketEA(
            symbol=adapter.symbol,
            indicator_source=adapter,
            broker=adapter,
            account_source=adapter,
            config=config,
            log_dir=".",
            now_provider=adapter.now,
        )
        ea.init()
        write_log(
            log_path,
            (
                f"EA initialized symbol={adapter.symbol} base_lots={args.base_lots:.2f} "
                f"pending_lots={args.pending_lots:.2f} tp_mode={args.tp_mode} "
                f"target_profit_usd={args.target_profit_usd:.2f} log_level={args.log_level}"
            ),
        )

        start = time.time()
        ticks = 0
        while True:
            ea.on_tick()
            ticks += 1
            if args.duration_minutes > 0 and (time.time() - start) >= args.duration_minutes * 60:
                break
            time.sleep(max(0.2, args.loop_seconds))

        write_log(log_path, f"Runner stopped cleanly ticks={ticks}")
        return 0
    except KeyboardInterrupt:
        write_log(log_path, "Runner stopped by keyboard interrupt")
        return 0
    except Exception as exc:
        write_log(log_path, f"Runner exception: {exc}")
        return 1
    finally:
        adapter.shutdown()
        write_log(log_path, "MT5 shutdown complete")


if __name__ == "__main__":
    raise SystemExit(main())
