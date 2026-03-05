# Phase-1 MVP: EURUSD Basket Bot (MT5 EA + Python Server)

## Architecture

- `server/`: decisioning, risk, state machine, logs, bridge I/O.
- `mql5_ea/`: MT5 execution EA (`QuantEURUSDBasketEA.mq5`).
- `configs/eurusd.yaml`: all tunables.
- `bridge/`: file bridge between server and EA (`intent.json`, `status.json`, `fills.json`).

## Strategy / Risk (implemented)

- Symbol: **EURUSD only**.
- Entry windows (terminal/VN session logic on server): minute **01-03** and **31-33**.
- Session gate (VN): **07:00-15:00**.
- Max one basket per 30-min slot (`window_id` lock).
- Basket TP: **+10 USD** closes all.
- DCA: spacing 15 pips, lot ladder `[0.10, 0.15, 0.20, 0.20, 0.25, 0.30]`, max total lot 1.20, max orders 6.
- RiskGuard:
  - spread limit 2.0 pips blocks entry + DCA.
  - ADX H1 > 25 blocks DCA.
  - kill switch MAE >= 60 pips closes basket and starts 120-minute cooldown.
  - daily loss >= 6% blocks entries for day.
- Fail-safe default on error: disable entries and DCA, emit alert/log.

## Run server

```bash
python -m server.main
```

- Server reads `bridge/status.json` and writes `bridge/intent.json`.
- Logs are in `server/logs/decisions.jsonl`.

## Attach EA

1. Open `mql5_ea/QuantEURUSDBasketEA.mq5` in MetaEditor and compile.
2. Attach EA to **EURUSD** chart only.
3. Ensure Common Files bridge folder exists and path matches `InpBridgeFolder` (default `bridge`).
4. Enable Algo Trading.

EA behavior:
- On every tick writes `status.json`.
- Reads `intent.json` and executes `OPEN`, `DCA`, `CLOSE_ALL`.
- If no intent exists, EA does nothing except logging idle message.

## Forward test loop

1. Start EA in MT5 terminal.
2. Start server loop (external scheduler or repeated `python -m server.main`).
3. Verify bridge files update and check `server/logs/decisions.jsonl`.
4. Confirm one basket per slot and RiskGuard behavior under spread/ADX/drawdown conditions.
