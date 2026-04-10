# Usage Instructions

## Prerequisites

1. Activate the virtual environment:
   ```
   source .venv/bin/activate
   ```

2. Ensure `config/.env` has valid Kite credentials:
   ```
   KITE_API_KEY=...
   KITE_API_SECRET=...
   KITE_ACCESS_TOKEN=...
   ```

3. If the access token is expired or missing, run the login script:
   ```
   python scripts/login.py
   ```
   It opens a browser for Kite OAuth and writes the new token to `config/.env`.

---

## Intraday Trading

**Config:** `config/config.yaml`
**Strategies:** RSI mean reversion, Opening Range Breakout (ORB)
**Product type:** MIS — positions auto-close at 3:15 PM

### Run (paper or live)
```
python main.py
```
Mode is controlled by `env:` in `config/config.yaml` (`paper` or `live`).

### Backtest
```
python scripts/backtest.py
python scripts/backtest.py --from 2026-01-01 --to 2024-06-30
python scripts/backtest.py --from 2026-01-01 --save      # saves CSVs to backtest_results/
```
Defaults to the last 90 days (from `historical_cache_days` in config).

---

## Interday Trading (Positional / Swing)

**Config:** `config/config_interday.yaml`
**Strategy:** EMA crossover on daily candles
**Product type:** CNC — positions hold overnight until an exit signal

### Run (paper or live)
```
python main_interday.py
```
Mode is controlled by `env:` in `config/config_interday.yaml`.

### Backtest
```
python scripts/backtest.py --config config/config_interday.yaml
python scripts/backtest.py --config config/config_interday.yaml --from 2024-01-01 --save
```

---

## Parameter Calibration

Finds the best strategy parameters by running backtests across a parameter search space and ranking results.

**Requires cached candle data** — run `main.py` or `scripts/backtest.py` first to warm up the SQLite DB.

### Basic usage
```
python scripts/calibrate.py --strategy rsi --from 2026-03-01 --iterations 20
```
Runs 20 random parameter combinations for RSI across all watchlist symbols, ranked by Sharpe ratio.

### Options
```
--strategy     rsi | orb | vwap | supertrend | bollinger | ema_pullback
               orb_supertrend | rsi_bollinger
--symbols      NSE:XXX NSE:YYY   (default: config.watchlist)
--from         Start date YYYY-MM-DD  (required)
--to           End date YYYY-MM-DD    (default: today)
--iterations   How many combinations to test in random mode (default: 20)
--metric       sharpe | total_pnl | win_rate | max_drawdown  (default: sharpe)
--mode         random (default) | grid (all combinations)
--seed         Integer seed for reproducible random search
--top          Rows to show in ranked table (default: 10)
--update-config  Write best params back to config.yaml after calibration
```

### Examples
```
# Full grid search for VWAP (6 combinations), write best params to config
python scripts/calibrate.py --strategy vwap --from 2026-03-01 --mode grid --update-config

# Calibrate ORB+Supertrend group, optimise for total P&L
python scripts/calibrate.py --strategy orb_supertrend --from 2026-03-01 --iterations 20 --metric total_pnl

# Calibrate on a single stock only
python scripts/calibrate.py --strategy supertrend --from 2026-03-01 --symbols NSE:INDHOTEL --mode grid

# Interday config
python scripts/calibrate.py --config config/config_interday.yaml --strategy ema_pullback --from 2025-01-01
```

### Output
- Progress line per iteration showing params and metric value
- Ranked table of top 10 results with all params + sharpe, P&L, win rate, drawdown
- Best params summary with per-symbol breakdown
- `--update-config` rewrites the strategy block in config.yaml (note: YAML comments are removed on rewrite)

---

## Key Config Files

| File | Purpose |
|---|---|
| `config/config.yaml` | Intraday settings (capital, watchlist, strategies, risk) |
| `config/config_interday.yaml` | Interday settings (CNC, daily candles, EMA params) |
| `config/.env` | Kite API credentials and access token (never commit this) |

---

## Notes on Capital

- `capital.total` is the **total account capital**, not per-stock.
- Position sizing is derived from `max_risk_per_trade_pct` × total capital.
  - Example: ₹20,000 × 2% = ₹400 max loss per trade
  - Quantity = ₹400 ÷ stop-loss distance in rupees
- In **live/paper mode**, one risk manager is shared across all instruments — they compete for the same capital and `max_open_positions` slots.
- In **backtesting**, each instrument/strategy is run independently with the full capital. The combined "Overall P&L" is additive and does not model capital allocation across instruments.
