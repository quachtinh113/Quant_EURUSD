from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import MetaTrader5 as mt5

from nowtrading.backtest_adapter import BacktestAdapter
from nowtrading.ea import NowTradingBasketEA, NtEaConfig
from nowtrading.mt5_adapter import Mt5BrokerAdapter, Mt5ConnectionConfig, TIMEFRAME_MAP


def parse_datetime(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError("Invalid datetime format, use YYYY-MM-DD or YYYY-MM-DD HH:MM")


def rates_to_rows(rates) -> list[dict[str, float | int]]:
    rows: list[dict[str, float | int]] = []
    if rates is None:
        return rows
    for r in rates:
        rows.append(
            {
                "time": int(r["time"]),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "spread": int(r["spread"]),
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest NowTrading EA by replaying MT5 historical bars.")
    parser.add_argument("--login", required=True, type=int)
    parser.add_argument("--password", required=True)
    parser.add_argument("--server", required=True)
    parser.add_argument(
        "--terminal-path",
        default=r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe",
    )
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--start", required=True, type=parse_datetime)
    parser.add_argument("--end", required=True, type=parse_datetime)
    parser.add_argument("--initial-balance", type=float, default=10000.0)
    parser.add_argument("--base-lots", type=float, default=0.01)
    parser.add_argument("--pending-lots", type=float, default=0.0)
    parser.add_argument("--dca-lots", type=float, default=0.01)
    parser.add_argument("--magic", type=int, default=3001001)
    parser.add_argument("--max-spread-points", type=int, default=25)
    parser.add_argument("--disable-session-filter", action="store_true")
    args = parser.parse_args()

    if args.end <= args.start:
        print("ERROR: --end must be after --start")
        return 1

    conn = Mt5ConnectionConfig(
        login=args.login,
        password=args.password,
        server=args.server,
        terminal_path=args.terminal_path,
    )
    live = Mt5BrokerAdapter(connection=conn, symbol=args.symbol, magic=args.magic)
    if not live.connect():
        print(f"ERROR: MT5 connect failed: {live.last_error()}")
        return 1

    try:
        symbol = live.symbol
        info = mt5.symbol_info(symbol)
        if info is None:
            print("ERROR: symbol_info unavailable")
            return 1

        warmup_start = args.start - timedelta(days=60)
        mt5_rates: dict[str, list[dict[str, float | int]]] = {}
        for tf_name in ("M1", "M15", "M30", "H1", "H4", "D1"):
            rates = mt5.copy_rates_range(symbol, TIMEFRAME_MAP[tf_name], warmup_start, args.end)
            rows = rates_to_rows(rates)
            if not rows:
                print(f"ERROR: no rates for timeframe {tf_name}")
                return 1
            mt5_rates[tf_name] = rows

        adapter = BacktestAdapter.from_mt5_rates(
            symbol=symbol,
            magic=args.magic,
            digits=int(info.digits),
            point=float(info.point),
            contract_size=float(getattr(info, "trade_contract_size", 100000.0) or 100000.0),
            initial_balance=args.initial_balance,
            mt5_rates=mt5_rates,
        )

        cfg = NtEaConfig()
        cfg.magic = args.magic
        cfg.base_lots_total = args.base_lots
        cfg.pending_lots = args.pending_lots
        cfg.use_pending_limit = args.pending_lots > 0.0
        cfg.dca_lots = args.dca_lots
        cfg.max_spread_points = args.max_spread_points
        if args.disable_session_filter:
            cfg.enable_london_ny_only = False

        ea = NowTradingBasketEA(
            symbol=symbol,
            indicator_source=adapter,
            broker=adapter,
            account_source=adapter,
            config=cfg,
            log_dir=".",
            now_provider=adapter.now,
        )
        ea.init()

        m1_rows = mt5_rates["M1"]
        m1_times = [datetime.fromtimestamp(int(r["time"])) for r in m1_rows]
        start_idx = next((i for i, t in enumerate(m1_times) if t >= args.start), -1)
        end_idx = next((i for i, t in enumerate(m1_times) if t > args.end), len(m1_rows)) - 1
        if start_idx < 0 or end_idx < start_idx:
            print("ERROR: no M1 bars in requested date range")
            return 1

        for i in range(start_idx, end_idx + 1):
            adapter.advance_to_m1_index(i)
            ea.on_tick()

        adapter.force_close_all()
        acct = adapter.account_state()
        print("BACKTEST_DONE")
        print(f"symbol={symbol}")
        print(f"range={args.start} -> {args.end}")
        print(f"start_balance={args.initial_balance:.2f}")
        print(f"end_balance={acct.balance:.2f}")
        print(f"realized_pnl={adapter.realized_profit:.2f}")
        print(f"opened_positions={adapter.opened_positions}")
        print(f"closed_positions={adapter.closed_positions}")
        return 0
    finally:
        live.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())

