# NowTrading Bot Flowchart

```mermaid
flowchart TD
    A[Start live_runner] --> B[Connect MT5]
    B -->|Fail| B1[Log error and exit]
    B -->|Success| C[Init EA modules]
    C --> D{Loop on_tick}

    D --> E[TimeEngine rollover check]
    E --> F[RiskGuard rollover check]
    F --> G[Build signal snapshot RSI/ATR/spread]
    G -->|Snapshot fail| D
    G --> H[Evaluate risk snapshot]

    H --> I{Active basket exists?}
    I -->|Yes| J[Evaluate basket lifecycle]
    I -->|No| N[Evaluate new entry]

    J --> J1{TP hit?}
    J1 -->|Yes| J2[Close basket + log]
    J1 -->|No| J3{Emergency exit?}
    J3 -->|Yes| J4[Close basket + log]
    J3 -->|No| J5{Can add DCA?}
    J5 -->|Yes| J6[Add DCA order + log]
    J5 -->|No| D
    J2 --> D
    J4 --> D
    J6 --> D

    N --> N1{Entry minute 01 or 31?}
    N1 -->|No| D
    N1 -->|Yes| N2{Session allowed?}
    N2 -->|No| D
    N2 -->|Yes| N3{Can open in current block?}
    N3 -->|No| D
    N3 -->|Yes| N4{Risk blocks new entries?}
    N4 -->|Yes| N5[Log ENTRY_BLOCKED_RISK]
    N4 -->|No| N6[SignalGate evaluate]
    N5 --> D

    N6 --> N7{Direction BUY/SELL?}
    N7 -->|NONE| D
    N7 -->|BUY/SELL| N8[Open initial basket: 2 market + optional limit]
    N8 -->|Success| N9[Mark basket opened + log]
    N8 -->|Fail| N10[Log BASKET_OPEN_FAIL]
    N9 --> D
    N10 --> D
```

## Notes

- Entry gate: minute `01/31`, session window, one basket per 30-minute block, daily max baskets.
- Signal stack: `RSI H1/M30/M15 alignment + M15 breakout + spread`.
- Basket management: TP mode (money/ATR), emergency exit, DCA spacing.
- Risk guard can block new entries and/or DCA.
