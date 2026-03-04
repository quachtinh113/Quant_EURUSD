# NowTrading 30M Basket EA (Python)

Python port of the original MT5/MQL5 EURUSD basket EA.
The strategy logic is preserved: time-gated entries, RSI multi-timeframe signal stack, DCA scaling, risk guardrails, and structured CSV logging.

## Project Layout

- `nowtrading/types.py`: enums and state dataclasses.
- `nowtrading/utils.py`: pip/volume normalization and basket comment helpers.
- `nowtrading/time_engine.py`: 01/31 minute and 30-minute block gating.
- `nowtrading/indicators.py`: signal snapshot builder from a data source.
- `nowtrading/signal_gate.py`: RSI + ADX + spread entry filter.
- `nowtrading/risk_guard.py`: drawdown/free-margin/news/correlation guard checks.
- `nowtrading/basket_manager.py`: open/close basket and DCA order execution.
- `nowtrading/dca_engine.py`: spacing-based DCA trigger.
- `nowtrading/logger.py`: CSV event logging.
- `nowtrading/ea.py`: main EA orchestration class (`NowTradingBasketEA`).
- `nowtrading/mt5_adapter.py`: MT5 live broker adapter.
- `nowtrading/live_runner.py`: run EA continuously on MT5.
- `nowtrading/backtest_adapter.py`: simulation broker for historical replay.
- `nowtrading/backtest_runner.py`: backtest runner over MT5 history.
- `nowtrading/mt5_live_test.py`: one-shot open/close live test.

## Strategy Rules

### Time Engine

- Entry evaluation runs only at local minute `01` or `31`.
- One basket per 30-minute block.
- Optional session gate via `enable_london_ny_only`, `start_hour`, `end_hour`.
- Daily basket counter resets on day rollover.

### Entry Signal Stack (RSI 14 on H1/M30/M15)

All filters must pass:

1. Trend filter (H1): BUY only if `RSI_H1 > 55`; SELL only if `RSI_H1 < 45`.
2. Pullback filter (M30): BUY in `[40..50]`; SELL in `[50..60]`.
3. Trigger filter (M15 closed bars):
   - BUY cross up 40: `prev2 <= 40` and `prev1 > 40`
   - SELL cross down 60: `prev2 >= 60` and `prev1 < 60`
4. Additional filters: `spread_points <= max_spread_points` and `ADX_H1 > 22`.

### Basket Structure

- Base lots are split into 2 market orders.
- Optional pending limit order offset by `pending_offset_pips`.
- Basket identity comment format: `NTB|<basket_id>|BUY|SELL`.

## Usage

`NowTradingBasketEA` depends on adapters (interfaces) you provide:

- `NtBroker`: pricing + execution + positions/orders access.
- `NtIndicatorSource`: RSI/ADX/ATR + bid/ask/point.
- `NtAccountSource`: account equity/balance/margin/free margin.

Example:

```python
from nowtrading.ea import NowTradingBasketEA, NtEaConfig

ea = NowTradingBasketEA(
    symbol="EURUSD",
    indicator_source=my_broker_adapter,
    broker=my_broker_adapter,
    account_source=my_account_adapter,
    config=NtEaConfig(),
)
ea.init()
ea.on_tick()
```

## Run Live

Run bot live (looping):

```powershell
python -m nowtrading.live_runner `
  --login 206539306 `
  --password "YOUR_PASSWORD" `
  --server Exness-MT5Trial7 `
  --symbol EURUSD `
  --base-lots 0.01 `
  --pending-lots 0.00 `
  --duration-minutes 60
```

Run one-shot live connectivity/order test:

```powershell
python -m nowtrading.mt5_live_test `
  --login 206539306 `
  --password "YOUR_PASSWORD" `
  --server Exness-MT5Trial7 `
  --symbol EURUSD `
  --lot 0.01
```

## Run Backtest

Replay historical MT5 bars:

```powershell
python -m nowtrading.backtest_runner `
  --login 206539306 `
  --password "YOUR_PASSWORD" `
  --server Exness-MT5Trial7 `
  --symbol EURUSD `
  --start "2026-02-01" `
  --end "2026-03-01" `
  --base-lots 0.01 `
  --pending-lots 0.00 `
  --disable-session-filter
```
