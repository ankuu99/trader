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
**Strategies:** RSI, ORB (with volume + gap filters), VWAP Reversion, VWAP Pullback, Supertrend, Bollinger, EMA Pullback (+ strategy groups)
**Product type:** MIS — positions auto-close at 3:15 PM

### Run (paper or live)
```
python main.py
```
Mode is controlled by `env:` in `config/config.yaml` (`paper` or `live`).

### Backtest — Isolated mode (default)
```
python scripts/backtest.py
python scripts/backtest.py --from 2026-01-01 --to 2026-03-31
python scripts/backtest.py --from 2026-01-01 --save      # saves per-strategy CSVs to backtest_results/
```
Runs each (symbol × strategy) combination independently with full capital. Results are additive but do not model shared capital. Use for strategy-level performance analysis and calibration.

### Backtest — Portfolio mode
```
python scripts/backtest.py --portfolio
python scripts/backtest.py --portfolio --from 2026-01-01
python scripts/backtest.py --portfolio --from 2026-01-01 --save   # saves backtest_results/portfolio.csv
```
Replays all symbols simultaneously with a **shared** `RiskManager` and **shared** capital — exactly how live/paper trading works. Enforces `max_open_positions` across the entire watchlist. Produces a single portfolio equity curve with per-symbol breakdown.

**When to use which:**

| | Isolated (default) | Portfolio (`--portfolio`) |
|---|---|---|
| Capital | Full budget per symbol | Single shared pool |
| Position limits | Per run (not realistic) | Portfolio-wide (realistic) |
| Use for | Calibrating individual strategies | Simulating actual live trading |
| Output | One report per strategy | One combined portfolio report |

Defaults to the last 90 days (from `historical_cache_days` in config).

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
--strategy     rsi | orb | vwap | vwap_pullback | supertrend | bollinger | ema_pullback
               orb_supertrend | orb_adx | orb_ema_pullback
               rsi_bollinger | rsi_supertrend | rsi_vwap
               vwap_pullback_adx | ema_pullback_adx
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

# Calibrate VWAP Pullback Continuation
python scripts/calibrate.py --strategy vwap_pullback --from 2026-01-01 --iterations 20

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

## Risk Controls

The following risk controls are configured in `config/config.yaml` under the `risk:` block:

| Control | Config key | Default | Description |
|---|---|---|---|
| Daily loss limit | `capital.daily_loss_limit_pct` | 2% | Halt all new entries for the day once realised loss hits this % of capital |
| Weekly circuit breaker | `risk.weekly_loss_limit_pct` | 4% | Halt new entries for the rest of the week when weekly loss exceeds this. Resets Monday. Set `0` to disable. |
| Regime overlay | `risk.regime_filter.enabled` | false | Block entries when NIFTY is below its 200 DMA or has drawn down >15% from 52w high |
| Max open positions | `risk.max_open_positions` | varies | Cap on simultaneous open positions across all instruments |
| ATR-based sizing | `risk.position_sizing.atr_based` | false | Size positions using `risk_amount / (atr_multiplier × ATR_14)` instead of fixed SL distance |
| Position cap | `risk.position_sizing.max_position_pct` | 8% | Max % of capital in a single position (applies to both sizing methods) |
| Chandelier trailing SL | `risk.trailing_stop.enabled` | false | Backtest only: trail SL as `highest_high − 3 × ATR_22`, ratchets up only |

---

## VWAP Pullback Strategy

A trend-continuation intraday strategy. Different from the existing VWAP Reversion strategy.

**3-step entry logic:**
1. Close is above the SMA (default 50-period) — confirms the stock is in an uptrend
2. Previous close was above VWAP; current candle's low touches VWAP (within tolerance) and close stays near VWAP — the pullback touch
3. The next candle closes above the pullback candle's high — trend resumes → **BUY signal**

**Exit:** Close falls below VWAP — trend support broken.

**How to enable** (`config/config.yaml`):
```yaml
strategies:
  vwap_pullback:
    enabled: true
    sma_period: 50
    vwap_touch_tolerance_pct: 0.2   # how close low/close must be to VWAP (%)
```

**Flow impact:**
- State is maintained across candles within a day: `watching` → `awaiting_resume` → entry signal
- If price crashes through VWAP after the touch (close < VWAP × (1 − 3×tolerance)), state resets to `watching` — no entry
- SMA accumulates across days (cross-day window); VWAP and pullback state reset each morning
- Calibratable: `python scripts/calibrate.py --strategy vwap_pullback --from 2026-01-01 --iterations 20`

---

## ORB Signal Quality Filters

Configured under `strategies.orb` in `config/config.yaml`:

```yaml
strategies:
  orb:
    range_minutes: 15
    volume_filter: true
    volume_lookback: 20       # days of range-volume history to build average
    volume_multiplier: 1.5    # entry blocked if range volume < 1.5× 20-day avg
    gap_filter: true
    gap_pct: 2.0              # entry blocked if open gaps > 2% vs previous close
```

**Volume filter flow:**
- ORB accumulates the first-15-min cumulative volume for each trading day
- From day 6 onward: if today's range volume < `volume_multiplier × 20-day avg`, the breakout signal is suppressed
- Days 1–5: filter bypasses automatically (insufficient history) — trades still fire

**Gap filter flow:**
- On each new day, computes `|today's open / yesterday's close − 1|`
- If gap > `gap_pct`, the entire day's ORB signals are skipped
- Day 1 (no previous close): gap filter bypasses automatically

**Why these matter:** Low-volume breakouts have higher false positive rates. Large gap days have different opening dynamics that the standard ORB range doesn't capture well.

---

## Strategy Groups

Strategy groups combine a primary signal strategy with one or more filter strategies using AND-logic.

**Available groups:**

| Group | Primary | Filter | What it does |
|---|---|---|---|
| `orb_supertrend` | ORB | Supertrend | ORB breakout only when Supertrend is trending in the same direction |
| `orb_adx` | ORB | ADX | ORB breakout only when ADX confirms sufficient trend strength (no ranging) |
| `orb_ema_pullback` | ORB | EMA Pullback | ORB breakout only when stock is already above its slow EMA |
| `rsi_bollinger` | RSI | Bollinger | RSI oversold entry only when price is also at/below the lower Bollinger Band |
| `rsi_supertrend` | RSI | Supertrend | RSI oversold only when Supertrend is bullish — avoids buying into downtrends |
| `rsi_vwap` | RSI | VWAP | RSI oversold + price below VWAP — double mean-reversion confirmation |
| `vwap_pullback_adx` | VWAP Pullback | ADX | VWAP pullback entry only when ADX confirms the trend has sufficient strength |
| `ema_pullback_adx` | EMA Pullback | ADX | EMA pullback entry only when ADX confirms trend strength |
| `ema_adx` | EMA Crossover | ADX | Interday: EMA crossover only when ADX confirms trend momentum |

**How it works:**
- The primary strategy's `on_candle()` generates the signal
- Each filter's `on_candle()` runs every bar to keep its indicators current
- On an ENTRY signal: all filters must return `confirm_entry() = True` or the signal is dropped
- EXIT signals always pass through — filters never block exits

**Calibrating a group:**
```
python scripts/calibrate.py --strategy orb_supertrend --from 2026-01-01 --iterations 30
```
Both primary and filter parameters are searched together and displayed with prefixed names (e.g. `orb__period`, `supertrend__multiplier`).

---

## Regime Overlay

Prevents new entries during unfavourable broad market conditions.

**How to enable** (`config/config.yaml`):
```yaml
risk:
  regime_filter:
    enabled: true
    index_symbol: "NSE:NIFTY 50"
    dma_period: 200
    max_drawdown_pct: 15.0
```

**Flow impact:**
- Pre-market, the system computes NIFTY 50's 200-day SMA and 52-week high
- If NIFTY close < 200 DMA **or** NIFTY is down > 15% from its 52-week high → `RiskManager.update_regime(False)` is called
- While regime is blocked: all ENTRY signals are rejected with reason `"regime_filter"` (logged to the signals table)
- EXIT signals are never blocked by regime — existing positions can always be closed
- Regime check is portfolio-level — applies to all instruments simultaneously
- When regime clears (NIFTY recovers above 200 DMA): `update_regime(True)` re-enables entries

---

## Weekly Circuit Breaker

Protects against persistent losing streaks across multiple days in the same week.

**How to enable** (`config/config.yaml`, intraday only):
```yaml
risk:
  weekly_loss_limit_pct: 4.0   # halt if weekly loss exceeds 4% of total capital
                                # set to 0 to disable
```

**Flow:**
- RiskManager accumulates realised P&L across all trades within the week
- When `weekly_realised_pnl < −(capital × weekly_loss_limit_pct / 100)` → `_weekly_halted = True`
- All ENTRY signals are rejected for the rest of the week; EXIT signals still pass
- On Monday: `reset_day(is_monday=True)` resets the weekly counter and clears the halt flag
- The daily loss limit (`daily_loss_limit_pct`) operates independently — either can halt entries on any given day

---

## ATR-Based Position Sizing

Sizes positions relative to recent volatility instead of a fixed stop-loss distance.

**How to enable** (`config/config.yaml`):
```yaml
risk:
  position_sizing:
    atr_based: true
    atr_multiplier: 2.0       # quantity = risk_amount / (multiplier × ATR_14)
    max_position_pct: 8.0     # hard cap: no single position > 8% of total capital
```

**Two sizing modes:**

| Mode | Formula | When to use |
|---|---|---|
| Default (SL-distance) | `qty = risk_amount / sl_distance` | Fixed, predictable risk per trade |
| ATR-based | `qty = risk_amount / (atr_multiplier × ATR_14)` | Sizes down automatically in volatile conditions |

Both modes respect `max_position_pct` — the calculated quantity is capped so the total position value never exceeds that % of capital.

**Flow impact:** No change to signal generation or order placement flow. Only the quantity attached to each order changes.

---

## Chandelier Trailing Stop (Backtest)

Trails the stop-loss upward as the trade moves in your favour. Only active in backtests — live trailing SL management is not yet implemented.

**Per-run (override config):**
```python
from trader.backtest.engine import Backtest
bt = Backtest(store, strategy, capital=200000.0, chandelier=True)
```

**Via config** (`config/config.yaml`):
```yaml
risk:
  trailing_stop:
    enabled: true       # applies to all backtest runs using default chandelier=None
    period: 22          # look-back for ATR and highest-high
    multiplier: 3.0     # SL = highest_high_since_entry − (3 × ATR_22)
```

**How it works:**
- On entry fill: starts tracking the highest candle high since entry
- Each subsequent candle: `chandelier_sl = highest_high − multiplier × ATR_22`
- SL only ratchets **up** — it never moves down even if price pulls back
- When `chandelier_sl > current stop_loss` → `trade.stop_loss` is updated
- Trade exits when `candle.low ≤ stop_loss` (same SL-hit logic as fixed SL)

**CLI backtest flag:**
```
python scripts/backtest.py --chandelier        # enable for this run
python scripts/backtest.py --no-chandelier     # disable regardless of config
```

---

## Signal Audit Log

Every signal the system generates — accepted or rejected — is written to the `signals` table in the SQLite database.

**Schema:**
```
id, logged_at, instrument, strategy, direction, signal_type, price_hint, accepted, reject_reason
```

**Rejection reasons written to the log:**
- `"daily_limit"` — daily loss limit hit
- `"weekly_limit"` — weekly circuit breaker active
- `"regime_filter"` — regime overlay blocking entries
- `"max_positions"` — at max open position count
- `"duplicate"` — already have an open position in this instrument
- `"zero_quantity"` — sizing formula produced qty = 0 (SL too wide)

**How to query (example):**
```python
import sqlite3, pandas as pd
conn = sqlite3.connect("data/market.db")
df = pd.read_sql("SELECT * FROM signals ORDER BY logged_at DESC LIMIT 100", conn)
print(df[df["accepted"] == 0].groupby("reject_reason").size())  # rejection breakdown
```

**Note:** Signal logging is only active in live/paper mode when `RiskManager` is constructed with `signal_logger=store.log_signal`. Backtest runs do not write to the signals table by default.

---

## Notes on Capital

- `capital.total` is the **total account capital**, not per-stock.
- Position sizing is derived from `max_risk_per_trade_pct` × total capital.
  - Default: Quantity = risk amount ÷ stop-loss distance in rupees
  - ATR mode (when `atr_based: true`): Quantity = risk amount ÷ (`atr_multiplier` × ATR_14), capped at `max_position_pct` of capital
- In **live/paper mode**, one risk manager is shared across all instruments — they compete for the same capital and `max_open_positions` slots.
- In **backtesting**, each instrument/strategy is run independently with the full capital. The combined "Overall P&L" is additive and does not model capital allocation across instruments.
