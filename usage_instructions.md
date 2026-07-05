# Usage Instructions

## Prerequisites

- Python 3.11+
- A Zerodha account with Kite Connect API access (kite.trade/developers)
- Dependencies installed: `pip install -r requirements.txt`

---

## One-Time Setup

### 1. Create a Kite Connect App

1. Log in at [kite.trade/developers](https://kite.trade/developers)
2. Create a new app
3. Set the **redirect URL** to: `http://127.0.0.1:8080/callback`
4. Note your **API Key** and **API Secret**

### 2. Create `config/.env`

```
KITE_API_KEY=your_api_key_here
KITE_API_SECRET=your_api_secret_here
KITE_ACCESS_TOKEN=
KITE_USER_ID=your_zerodha_user_id
KITE_PASSWORD=your_zerodha_password
KITE_TOTP_SECRET=your_totp_base32_secret
TELEGRAM_BOT_TOKEN=optional
TELEGRAM_CHAT_ID=optional
```

Leave `KITE_ACCESS_TOKEN` blank — the login script fills it in every day.

### 3. Configure `config/config.yaml`

```yaml
env: paper                  # paper (no real orders) or live (real orders)
candle_timeframe: day       # 5minute / 15minute / 30minute / 60minute / day

capital:
  total: 50000
  max_risk_per_trade_pct: 7.0
  daily_loss_limit_pct: 10.0

watchlist:
  - NSE:RELIANCE
  - NSE:INFY

interested:                 # monitored in UI but not traded
  - NSE:TCS

strategies:
  lr_extrema:
    enabled: true
    warmup_bars: 300
    lookback_bars: 600
    threshold: 0.85
    profit_pct: 10
    trail_pct: 1.5
    stop_pct: 5
    hold_bars: 300
    retrain_every: 25
    extrema_order: 5
    trading_start: "09:15"
    trading_end: "15:30"

risk:
  gtt_enabled: false
  order_type: market        # market or limit
  max_open_positions: 5
  default_sl_pct: 2
  risk_reward: 4
  max_capital_per_stock_pct: 25.0

data:
  db_path: data/market.db
  historical_cache_days: 90

logging:
  level: INFO
  dir: logs
```

---

## Every Trading Day

### Token Refresh (automated on EC2)

On EC2 the TOTP refresh runs automatically at **08:15 IST** every weekday via cron:

```bash
45 2 * * 1-5 /home/trader/.venv/bin/python /opt/trader/scripts/kite_totp_refresh.py >> /opt/trader/logs/totp_refresh.log 2>&1
```

This logs in headlessly using TOTP, saves the new token to `config/.env`, and restarts the trader service. A Telegram notification confirms success.

**Manual fallback** (if TOTP refresh fails):

```bash
python scripts/kite_auth_server.py
```

Runs an OAuth callback server on EC2. Open the printed URL in any browser, log in, and the token is saved automatically.

### Run the trader

```bash
python main.py
python main.py --config path/to/config.yaml   # alternate config
```

On startup it will:
1. Verify your Kite session
2. Fetch available Kite cash and set effective capital
3. Fetch instruments and validate watchlist
4. Refresh and warm up candle cache (last 90 days)
5. Train `LRExtremaStrategy` on cached history
6. Reconcile open positions from DB / Kite
7. Start the live WebSocket feed

At **09:00** pre-market warm-up runs. At **15:35** post-market logs P&L summary, resets daily counters, and disconnects the feed.

Press **Ctrl+C** to stop cleanly.

---

## How Orders Work

### Entry

When `LRExtremaStrategy` generates a BUY signal:
1. RiskManager checks: daily halt, max open positions, already in position, available capital
2. Sizes quantity: `max_risk_per_trade ÷ sl_distance`, capped by `max_capital_per_stock` and available capital
3. Places a **market or limit BUY order** (CNC delivery)

### Exit

Exits are managed entirely by the strategy (GTT is disabled):
- **Hard stop** — fires on every tick when `price <= entry × (1 - stop_pct/100)`
- **Trailing stop** — activates once `price >= entry × (1 + profit_pct/100)`; then exits when price pulls back `trail_pct%` from peak
- **Hold timeout** — exits at candle close after `hold_bars` candles

### Paper Mode

In `env: paper`, no real orders are placed. BUY orders fill at the **next candle's open**. Exit logic (trailing, hard stop, hold timeout) runs identically to live.

---

## Backtesting

```bash
# Backtest from a start date to today
python scripts/backtest.py --from 2025-01-01

# Specific date range
python scripts/backtest.py --from 2025-01-01 --to 2025-06-30

# Override candle timeframe
python scripts/backtest.py --from 2025-01-01 --timeframe 15minute
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--from` | required | Start date (YYYY-MM-DD) |
| `--to` | today | End date (YYYY-MM-DD) |
| `--timeframe` | from config | `5minute / 15minute / 30minute / 60minute / day` |

**Intrabar simulation** — checks each candle's low (hard SL), high (trailing peak), and close (trailing exit) so exits fire at the exact price rather than slipping to the next candle open.

### Rolling backtest

Slides a fixed-width window across a long date range — reveals how the strategy performs across different market regimes.

```bash
python scripts/backtest_rolling.py --from 2024-01-01 --to 2025-12-31
python scripts/backtest_rolling.py --from 2024-01-01 --window 6 --step 3 --symbols NSE:RELIANCE NSE:TCS
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--from` | required | Overall start date |
| `--to` | today | Overall end date |
| `--window` | 6 | Window width in months |
| `--step` | 3 | Slide step in months |
| `--symbols` | watchlist | Override instrument list |
| `--timeframe` | from config | Candle timeframe |

### Walk-forward backtest

True out-of-sample validation. Each fold trains the model on a dedicated training window, then tests on a separate non-overlapping window — the model never sees the test period during training. This is the most reliable measure of live performance.

```bash
python scripts/walk_forward.py --from 2025-01-01
python scripts/walk_forward.py --from 2024-01-01 --to 2025-12-31 --train 6 --test 3
python scripts/walk_forward.py --from 2025-01-01 --cache-only   # if candles already fetched
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--from` | required | Test period start date |
| `--to` | today | Test period end date |
| `--train` | 6 | Training window in months (pre-warmup, no trades) |
| `--test` | 3 | Test window in months; also the slide step |
| `--symbols` | watchlist | Override instrument list |
| `--timeframe` | from config | Candle timeframe |
| `--cache-only` | false | Skip Kite auth, use local SQLite data only |

**Fold structure** (`--train 6 --test 3 --from 2025-01-01`):
```
Fold 1: train Jul–Dec 2024  →  test Jan–Mar 2025
Fold 2: train Oct 2024–Mar 2025  →  test Apr–Jun 2025
Fold 3: train Jan–Jun 2025  →  test Jul–Sep 2025
...
```

**Key metric — Consistency**: percentage of folds that were profitable. Target >60%. A strategy with 80%+ consistency is robust across different market regimes.

**Interpreting the results:**
- If walk-forward return is significantly below regular backtest → rolling training buffer was seeing test-period data (expected; 10–20% degradation is normal)
- Stable profit factor >1.2 across all folds → edge is real, not period-specific
- One or two bad folds in a bear/sideways market → acceptable; check which regime they correspond to

### Visual UI (local, browser-based)

```bash
source .venv/bin/activate
streamlit run scripts/ui.py
```

Opens at `http://localhost:8501`.

| Tab | Contents |
|-----|----------|
| **Portfolio** | Metric cards (trades, money-weighted win%, P&L, return, max drawdown, avg win/loss, Sharpe*), equity curve, trade table |
| **Stock Chart** | Candlestick + volume + per-stock equity curve; ▲ entry and ▼ exit markers with exit reason and P&L on hover; optional live trades overlay from EC2 |
| **Trade Breakdown** | P&L distribution histogram, exit reasons (SL / TRAILING / STRATEGY / OPEN@END), hold duration vs P&L scatter, money-weighted win rate by instrument |

**Win rate** shown everywhere is **money-weighted**: `total_profit_from_wins / (total_profit_from_wins + total_loss_from_losses)`. A 30% trade-count win rate with large wins and small losses shows as 80%+ here.

**Cache-only mode** — if the Kite token is expired the UI falls back to SQLite-cached candles. Charts and strategy replay still work for already-fetched symbols.

---

## Calibration

Find the best `LRExtremaStrategy` parameters on your watchlist.

```bash
# Random search — 50 combinations (default, fast)
python scripts/calibrate.py --from 2024-01-01

# More iterations
python scripts/calibrate.py --from 2024-01-01 --mode random --iterations 200

# Calibrate only specific params — rest fixed at config values
python scripts/calibrate.py --from 2024-01-01 --params threshold profit_pct trail_pct

# Grid search over a subset (full grid is too large to be practical)
python scripts/calibrate.py --from 2024-01-01 --mode grid --params trail_pct stop_pct

# Override timeframe
python scripts/calibrate.py --from 2024-01-01 --timeframe 15minute
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--from` | required | Start date |
| `--to` | today | End date |
| `--mode` | random | `grid` or `random` |
| `--iterations` | 50 | Combinations to try (random mode) |
| `--params` | all | Params to vary; rest fixed at config |
| `--timeframe` | from config | Candle timeframe |

**How it works:**
1. Pre-fetches candle data for all watchlist symbols once — subsequent iterations hit SQLite cache, no API calls
2. For each combination, runs a full backtest and computes metrics
3. Prints a ranked table sorted by return %
4. Prints best params ready to paste into `config.yaml`

**Parameter search space:**

| Parameter | Values |
|-----------|--------|
| `warmup_bars` | 100, 150, 200, 300, 400 |
| `lookback_bars` | 400, 500, 600, 800 |
| `threshold` | 0.65, 0.70, 0.75, 0.80, 0.85, 0.90 |
| `profit_pct` | 3.0, 4.0, 5.0, 6.0, 8.0, 9.0, 10.0 |
| `trail_pct` | 1.0, 1.5, 2.0, 2.5 |
| `stop_pct` | 1.5, 2.0, 2.5, 3.0, 4.0, 5.0 |
| `hold_bars` | 100, 150, 200, 250, 300 |
| `retrain_every` | 25, 50, 100 |
| `extrema_order` | 3, 5, 7 |

> Full grid is ~1.5M combinations — always use `--mode random` or `--params` to restrict scope.

---

## Stock Screening

Backtest `LRExtremaStrategy` against all ~2,000 NSE EQ stocks to find where it performs best. Uses the current `lr_extrema` params from `config.yaml` — run calibration first.

```bash
python scripts/screen.py --from 2025-01-01
python scripts/screen.py --from 2025-01-01 --to 2025-06-30 --min-trades 3 --output results.csv
python scripts/screen.py --from 2025-01-01 --timeframe 15minute
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--from` | required | Start date |
| `--to` | today | End date |
| `--min-trades` | 2 | Min trades to appear in final table |
| `--output` | screen_results.csv | Output CSV path |
| `--timeframe` | from config | Candle timeframe |

**Resumable** — re-running the same command resumes from where it left off. Already-processed symbols are skipped; errored symbols are retried.

**Rate limiting** — ~3 req/sec (0.35s sleep). Full scan of ~2,000 stocks takes ~12 minutes.

**Good candidate signals:**
- `return_pct > 5%` over the period
- `win_rate >= 50%` (money-weighted)
- `total_trades >= 3`
- `avg_win / abs(avg_loss) > 1.5`

---

## File Structure

```
config/
  config.yaml           — all runtime settings
  .env                  — API credentials (never commit)

trader/
  auth/                 — Kite session management
  backtest/             — engine shared by all backtest scripts
  core/                 — config loader, logger
  costs.py              — Zerodha brokerage calculator (CNC/MIS)
  data/                 — historical fetch/cache, live WebSocket feed, SQLite store
  notifications/        — Telegram alerts
  orders/               — order placement (live + paper simulation)
  portfolio/            — position tracking
  risk/                 — signal validation, position sizing, capital tracking
  scheduler/            — pre/post market jobs (APScheduler)
  strategies/           — LRExtremaStrategy, base class, registry

scripts/
  kite_totp_refresh.py  — automated daily token refresh (runs on EC2 via cron)
  kite_auth_server.py   — manual OAuth fallback token refresh
  backtest.py           — historical replay (CLI)
  backtest_rolling.py   — sliding-window backtest across date range
  walk_forward.py       — true out-of-sample walk-forward validation
  calibrate.py          — parameter search (grid / random)
  screen.py             — backtest across all NSE EQ stocks
  ui.py                 — backtest visualisation UI (Streamlit)
  trader.service        — systemd unit file for EC2

data/
  market.db             — SQLite: candles, orders, signals, state (auto-created)

logs/                   — rotating log files (auto-created)
```

---

## Cloud Deployment (AWS EC2)

- **Instance**: t2.micro, Ubuntu 24.04 LTS, ap-south-1 (Mumbai)
- **Elastic IP**: `13.202.187.191` — whitelist in Zerodha API settings
- **SSH port**: 9654
- **Process manager**: systemd (`trader.service`) — auto-starts on boot, restarts on crash within 10s

### Deploying Code Changes

Deployments are tag-based — only explicitly tagged commits are deployed. This prevents unintended code from reaching the server.

**Step 1 — Cut a release tag (on your local machine):**
```bash
git tag release-YYYY-MM-DD <commit-sha>
git push origin release-YYYY-MM-DD
```

**Step 2 — Deploy the tag:**
```bash
./scripts/deploy.sh release-YYYY-MM-DD
```
The script will fail loudly if no tag is provided.

**Force Refresh of Kite on Remote**
```bash
ssh trader "sudo -u trader bash -c 'cd /opt/trader && .venv/bin/python scripts/kite_totp_refresh.py' && sudo systemctl restart trader && sleep 5 && sudo systemctl status trader --no-pager
```
**Rolling back** to a previous release is just:
```bash
./scripts/deploy.sh release-YYYY-MM-DD   # an earlier date
```

**Check what's running on EC2:**
```bash
ssh trader "git -C /opt/trader describe --tags"
```

### Monitoring

```bash
ssh trader "sudo systemctl status trader"
ssh trader "sudo journalctl -u trader -f"
ssh trader "sudo journalctl -u trader -n 100"
ssh trader "free -h && df -h /"
```

### Live Dashboard

```bash
# Open SSH tunnel
ssh -fN -L 8080:localhost:8080 trader

# Open in browser
open http://localhost:8080

# Close tunnel
pkill -f "ssh -fN -L 8080"
```

Enable in `config.yaml`:
```yaml
ui:
  enabled: true
  port: 8080
```

---

## Common Issues

**"Missing required environment variables"**
→ Check that `config/.env` exists and has `KITE_API_KEY` and `KITE_API_SECRET`.

**"Access token is invalid or expired"**
→ Run `python scripts/kite_auth_server.py` to refresh the token manually.

**"Instruments not found on NSE"**
→ Check symbol format in watchlist: must be `NSE:SYMBOL` e.g. `NSE:RELIANCE`.

**No signals firing**
→ Confirm `lr_extrema` has `enabled: true`. The model needs `warmup_bars` candles before it starts predicting — check logs for "TRAINED" status.

**Backtest shows no trades**
→ Widen the date range or lower `threshold`. Check that candles exist for the symbol and timeframe (`--timeframe` must match what was cached).

**TOTP refresh failed**
→ Check `logs/totp_refresh.log` on EC2. Common causes: wrong `KITE_TOTP_SECRET`, Zerodha password changed, network issue. Use `kite_auth_server.py` as fallback.
