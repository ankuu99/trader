# Integration Test Fixture Data

## candles.csv — format spec

```
timestamp,open,high,low,close,volume
2025-01-02 09:15:00,500.00,503.00,498.00,502.00,90000
```

| Column | Type | Notes |
|--------|------|-------|
| `timestamp` | `YYYY-MM-DD HH:MM:SS` | Candle close time (IST) |
| `open` | float | Opening price |
| `high` | float | Candle high |
| `low` | float | Candle low |
| `close` | float | Closing price |
| `volume` | int | Volume traded |

## Generating real data

To replace the synthetic file with a real month of data, export candles from Kite
historical API and save in the same CSV format. The integration test reads this file
and feeds candles in order through the full pipeline.

Recommended period: 1–3 months of 5-minute candles for a liquid stock.
Minimum for the strategy to train: `warmup_bars` candles (10 in test params).
