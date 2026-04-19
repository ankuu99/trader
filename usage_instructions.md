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
```

Leave `KITE_ACCESS_TOKEN` blank — the login script fills it in every day.

### 3. Configure `config/config.yaml`

```yaml
env: paper                  # paper (no real orders) or live (real orders)
candle_timeframe: 5minute   # 5minute / 15minute / 30minute / day

capital:
  total: 50000              # your trading capital in rupees
  max_risk_per_trade_pct: 2.0   # % of capital risked per trade
  daily_loss_limit_pct: 3.0     # halt trading if daily loss exceeds this %

watchlist:
  - NSE:RELIANCE
  - NSE:INFY

strategies:
  zlmtf_macd:
    enabled: true
    fast: 12
    slow: 26
    signal: 9
    current_tf_minutes: 5   # must match candle_timeframe numerically
    htf_minutes: 15         # higher timeframe for trend confirmation
    lookback_bars: 5        # bars HTF MACD must be rising to confirm entry

risk:
  max_open_positions: 5
  default_sl_pct: 3.0       # stop-loss placed this % below entry price
  risk_reward: 2.0          # target = entry + (sl_distance × risk_reward)
```

**Important:** `current_tf_minutes` must match `candle_timeframe`:

| candle_timeframe | current_tf_minutes |
|---|---|
| 5minute | 5 |
| 15minute | 15 |
| 30minute | 30 |
| day | 390 |

---

## Every Trading Day

### Step 1 — Login (required daily, tokens expire at midnight)

```bash
python scripts/login.py
```

This opens Kite login in your browser. After you log in, Kite redirects to localhost and the token is saved to `config/.env` automatically. You will see:

```
Access token saved to .env
User: Your Name (AB1234)

You can now run: python main.py
```

### Step 2 — Run the trader

```bash
python main.py
```

On startup it will:
1. Verify your Kite session
2. Fetch the instruments list and validate your watchlist
3. Warm up the candle cache (downloads last 90 days of history if not already cached)
4. Start the live WebSocket feed
5. Process candles and fire signals as they close

At **3:35 PM** the scheduler runs a post-market task that logs your portfolio P&L summary and resets the daily loss counter.

Press **Ctrl+C** to stop cleanly.

---

## How Orders Work

### Entry

When a strategy generates a signal:
1. The risk manager checks: daily halt, max open positions, already in position
2. Calculates quantity: `max_risk_per_trade ÷ sl_distance`
3. Places a **market BUY order** (CNC delivery)
4. Places a **GTT OCO** (One Cancels Other) with two legs:
   - **Stop-loss leg** — triggers at `entry × (1 - sl_pct/100)`
   - **Target leg** — triggers at `entry + (sl_distance × risk_reward)`

Example with `default_sl_pct: 3.0` and `risk_reward: 2.0`:

| Entry | Stop-loss | Target |
|---|---|---|
| ₹100 | ₹97 | ₹106 |
| ₹500 | ₹485 | ₹515 |

When either leg fires, Kite automatically cancels the other.

### Paper Mode

In `env: paper`, no real orders are placed. Entry orders are simulated as fills at the **next candle's open price**. The GTT OCO legs are not simulated in live feed — use the backtest for full SL/target simulation.

---

## Backtesting

```bash
# Backtest from a start date to today
python scripts/backtest.py --from 2025-01-01

# Backtest a specific date range
python scripts/backtest.py --from 2025-01-01 --to 2025-06-30
```

- Uses whichever strategy has `enabled: true` in config
- Historical data is fetched from Kite and cached locally on first run
- Simulates GTT OCO: checks each candle's low (SL) and high (target)
- If both are hit in the same candle, SL is assumed (conservative)

Sample output:

```
=======================================================
  Backtest: 2025-01-01  →  2025-06-30
=======================================================
  Trades     : 12  (W:8  L:4)
  Win rate   : 66.7%
  Total P&L  : Rs.4,320.00
  Return     : 8.64%
  Avg win    : Rs.810.00
  Avg loss   : Rs.405.00

  Date                   Instrument      Entry     Exit   Qty        P&L  Reason
  ...
=======================================================
```

---

## Calibration

Find the best `LRExtremaStrategy` parameters systematically on your watchlist.

```bash
# Random search (default — 50 combinations, fast)
python scripts/calibrate.py --from 2024-01-01

# Random search with more iterations
python scripts/calibrate.py --from 2024-01-01 --to 2025-01-01 --mode random --iterations 200

# Full grid search (8,640 combinations — slow)
python scripts/calibrate.py --from 2024-01-01 --mode grid
```

**How it works:**
1. Pre-fetches candle data for all watchlist symbols once (subsequent calls hit SQLite cache)
2. For each parameter combination, runs a full backtest and computes metrics
3. Prints a ranked table sorted by return %

**Parameter search space:**

| Parameter | Values |
|-----------|--------|
| `warmup_bars` | 100, 150, 200, 300 |
| `threshold` | 0.65, 0.70, 0.75, 0.80, 0.85, 0.90 |
| `profit_pct` | 3.0, 4.0, 5.0, 6.0, 8.0 |
| `stop_pct` | 1.5, 2.0, 2.5, 3.0 |
| `hold_bars` | 50, 100, 150, 200 |
| `retrain_every` | 25, 50, 100 |
| `extrema_order` | 3, 5, 7 |

**Output:**
```
Rank  warmup  threshold  profit  stop  hold  retrain  extrema  Trades  Win%   P&L       Return%  Sharpe*
   1     150       0.80     5.0   2.0   100       50        5      12   67%   Rs.4,200    8.40%    1.24
```

After calibration, copy the best params into `config/config.yaml` under `strategies.lr_extrema`.

---

## Stock Screening

Backtest `LRExtremaStrategy` against all ~2,000 NSE EQ stocks to find where it performs best. Uses the current `lr_extrema` params from `config.yaml` — run calibration first.

```bash
# Scan all NSE EQ stocks
python scripts/screen.py --from 2025-01-01

# Custom date range, minimum trades filter, output file
python scripts/screen.py --from 2025-01-01 --to 2025-01-01 --min-trades 3 --output results.csv
```

**Flags:**

| Flag | Default | Description |
|------|---------|-------------|
| `--from` | required | Backtest start date (YYYY-MM-DD) |
| `--to` | today | Backtest end date |
| `--min-trades` | 2 | Min trades to appear in final table |
| `--output` | screen_results.csv | Output CSV path |

**Resumable:** If interrupted, re-running the same command resumes from where it left off — already-processed symbols are read from the output CSV and skipped. Stocks that errored are retried; stocks with insufficient data are permanently skipped.

**Rate limiting:** ~3 req/sec (0.35s sleep between stocks). Full scan of ~2,000 stocks takes roughly 12 minutes.

**Terminal output during scan:**
```
[  42/2134] NSE:RELIANCE         Trades=8  Win=75%  Return=12.40%
[  43/2134] NSE:INFY             SKIP (insufficient data: 45 candles, need 200)
```

**Final table** (sorted by return %, filtered by min-trades):
```
Instrument          Trades  Win%    P&L          Return%   Sharpe*
NSE:RELIANCE            8   75%   Rs.12,400      12.40%     1.31
NSE:TCS                 6   67%    Rs.8,200       8.20%     0.95
```

Add the top-performing instruments to your `watchlist` in `config.yaml`.

---

## Strategies

### RSI
Buys when RSI crosses **below** the oversold threshold (default 30). Entry only — exit via GTT.

```yaml
rsi:
  enabled: true
  period: 14      # RSI lookback period
  oversold: 30    # trigger level
```

### MACD
Buys when MACD line crosses **above** the signal line. Entry only — exit via GTT.

```yaml
macd:
  enabled: true
  fast: 12
  slow: 26
  signal: 9
```

### Zero Lag MTF MACD *(recommended)*
Standard EMA-based MACD on current timeframe, with a higher timeframe confirmation using SMA with scaled periods (`htf_period = round(htf_minutes / current_tf_minutes × period)`). Entry requires:
1. LTF MACD crosses above LTF signal line
2. HTF MACD has been rising for `lookback_bars` consecutive bars

```yaml
zlmtf_macd:
  enabled: true
  fast: 12
  slow: 26
  signal: 9
  current_tf_minutes: 5   # matches candle_timeframe
  htf_minutes: 15         # higher timeframe
  lookback_bars: 5        # bars HTF must be rising
```

Only one strategy should be `enabled: true` at a time unless you intentionally want multiple signals on the same instrument.

---

## File Structure

```
config/
  config.yaml       — all runtime settings
  .env              — API credentials (never commit this)

trader/
  auth/             — Kite session management
  core/             — config loader, logger
  data/             — historical data fetch/cache, live WebSocket feed, SQLite store
  orders/           — order placement (live + paper simulation)
  portfolio/        — position tracking
  risk/             — signal validation, position sizing, SL/target calculation
  scheduler/        — pre/post market jobs (APScheduler)
  strategies/       — RSI, MACD, ZL-MTF-MACD, base class, registry

scripts/
  login.py          — daily token refresh
  backtest.py       — historical replay

data/
  market.db         — SQLite: candles, orders, signals (auto-created)

logs/               — rotating log files (auto-created)
```

---

## Cloud Deployment (AWS EC2)

The bot can run on an AWS EC2 t2.micro (free tier) in ap-south-1 (Mumbai). Full setup details are in `aws_plan.md`. Summary below.

### Infrastructure
- **Instance**: t2.micro, Ubuntu 24.04 LTS, 20 GB gp3 — free tier
- **Static IP**: Elastic IP, free while instance is running
- **SSH port**: 9654 (non-default, key-only auth)
- **Process manager**: systemd (`trader.service`) — auto-starts on boot, restarts on crash

### Initial Deployment

```bash
# 1. On your Mac — generate SSH key
ssh-keygen -t ed25519 -f ~/.ssh/trader_ec2 -C "trader-ec2"

# 2. Add to ~/.ssh/config
# Host trader
#     HostName YOUR_ELASTIC_IP
#     User ubuntu
#     Port 9654
#     IdentityFile ~/.ssh/trader_ec2
#     ServerAliveInterval 60

# 3. On EC2 — clone repo, install deps, set up service
sudo useradd -r -s /bin/bash -m -d /opt/trader trader
sudo mkdir -p /opt/trader && sudo chown trader:trader /opt/trader
sudo -u trader bash -c "cd /opt/trader && git clone https://github.com/YOUR_REPO/trader.git ."
sudo -u trader bash -c "cd /opt/trader && python3 -m venv .venv && .venv/bin/pip install --no-cache-dir -r requirements.txt"

# 4. Copy and enable the systemd service
sudo cp /opt/trader/scripts/trader.service /etc/systemd/system/trader.service
sudo systemctl daemon-reload
sudo systemctl enable trader
```

### Daily Token Refresh (required every trading day)

Because `scripts/login.py` opens a browser (must run on your Mac, not EC2), use the helper script:

```bash
~/scripts/refresh-token.sh
```

This runs login locally, uploads `config/.env` to EC2, and restarts the service. Run before **9:15 AM IST**. The token expires at midnight IST — do not run the night before.

### Deploying Code Changes

```bash
# Push from Mac
git push origin main

# Pull and restart on EC2
ssh trader "cd /opt/trader && sudo -u trader git pull && sudo systemctl restart trader"

# If requirements.txt changed
ssh trader "cd /opt/trader && sudo -u trader git pull && sudo -u trader .venv/bin/pip install -r requirements.txt && sudo systemctl restart trader"
```

### Monitoring

```bash
# Service status
ssh trader "sudo systemctl status trader"

# Live logs
ssh trader "sudo journalctl -u trader -f"

# Last 100 lines
ssh trader "sudo journalctl -u trader -n 100"

# Memory / disk
ssh trader "free -h && df -h /"
```

### Health Signal

After `refresh-token.sh` runs successfully, the bot sends a Telegram startup notification. If you don't receive it by 9:10 AM IST, check logs:

```bash
ssh trader "sudo journalctl -u trader -n 50 --no-pager"
```

---

## Common Issues

**"Missing required environment variables"**
→ Check that `config/.env` exists and has `KITE_API_KEY` and `KITE_API_SECRET`.

**"Access token is invalid or expired"**
→ Run `python scripts/login.py` to refresh the token.

**"Instruments not found on NSE"**
→ Check the symbol format in your watchlist: must be `NSE:SYMBOL` e.g. `NSE:RELIANCE`.

**No signals firing**
→ Confirm a strategy has `enabled: true` in config. For ZL-MTF-MACD, the HTF MACD needs `lookback_bars` consecutive rising bars — this filters out a lot of candles by design.

**Backtest shows no trades**
→ The strategy may need more historical data. Increase `historical_cache_days` or widen your date range.
