# CLAUDE.md — Trader Project

Personal automated trading system built in Python, connected to Zerodha's Kite platform via KiteConnect API. Single user, single account. Runs on local Mac.

---

## Running Commands

Virtual environment is at `.venv/`. Always use:
```
.venv/bin/pytest tests/ -q        # run tests
.venv/bin/python <script>         # run scripts if needed
```
Or activate first: `source .venv/bin/activate`

---

## Project Structure

```
main.py                          # intraday entry point (MIS, 5-min candles)
main_interday.py                 # interday entry point (CNC, daily candles)
config/
  config.yaml                    # intraday runtime config
  config_interday.yaml           # interday runtime config
  .env                           # Kite credentials — never commit
trader/
  core/
    config.py                    # singleton `config` — import and use directly
    logger.py                    # setup() + get_logger()
  auth/session.py                # create_kite() — validates token, raises if expired
  data/
    store.py                     # SQLite interface — all raw SQL lives here only
    historical.py                # warm_up() + get_candles() with cache
    live.py                      # LiveFeed — KiteTicker WebSocket, candle assembly
  strategies/
    base.py                      # Strategy ABC, Signal, Direction, SignalType enums
    rsi.py                       # RSI mean reversion (intraday)
    orb.py                       # Opening Range Breakout (intraday)
    ema_crossover.py             # EMA crossover (interday / daily candles)
  risk/manager.py                # RiskManager — sole gatekeeper between signals and orders
  orders/manager.py              # OrderManager — live Kite calls or paper simulation
  portfolio/tracker.py           # PortfolioTracker — positions and P&L
  scheduler/jobs.py              # APScheduler jobs aligned to IST market hours
  backtest/engine.py             # Backtest — replays candles, simulates fills
  notifications/telegram.py      # Fire-and-forget Telegram alerts
scripts/
  login.py                       # OAuth flow — captures request_token, writes access token
  backtest.py                    # CLI backtest runner
  test_telegram.py               # sends all 7 notification types
tests/                           # pytest unit tests
```

---

## Architecture Rules

**Signal flow (live):** Strategy → `RiskManager.validate()` → `OrderManager.place()`. Strategies never touch orders directly.

**Signal flow (backtest):** `Backtest.run()` replays candles → calls `strategy.on_candle()` → `risk.validate()` → simulates fill at next candle open.

**Config selection:** Set `TRADER_CONFIG` env var before importing any trader module to select a different config file. `main_interday.py` does this automatically. `scripts/backtest.py` accepts `--config`.

**Timezone:** All timestamps stored in SQLite are timezone-naive (IST wall-clock). `Store._to_naive()` strips tzinfo at the DB boundary. Never store tz-aware datetimes.

**Paper mode:** Controlled by `env: paper` in config.yaml. `OrderManager` queues paper fills and fills them at the next candle's open price. No real orders are placed.

---

## Intraday vs Interday

| Concern | Intraday | Interday |
|---|---|---|
| Entry point | `main.py` | `main_interday.py` |
| Config | `config/config.yaml` | `config/config_interday.yaml` |
| Product type | MIS | CNC |
| Candle timeframe | 5-minute | Daily (390-min bucket) |
| Square-off | 3:15 PM daily | Never — hold until signal |
| DB | `data/market.db` | `data/market_interday.db` |
| Strategies | RSI, ORB | EMA crossover |
| Post-market reset | `reset_day()` + `reset_positions()` | `reset_day()` only |

---

## RiskManager Behaviour

- `reset_day()` — resets daily P&L and halt flag only. **Positions are preserved.** Call this every day for both intraday and interday.
- `reset_positions()` — clears open position tracking. Call this at intraday session end (post-market in `main.py`). Do NOT call from `main_interday.py`.
- `should_square_off_enabled` — check `config.square_off_enabled` before registering the square-off scheduler job.

---

## Backtest Notes

- Each instrument/strategy backtest runs with an independent `RiskManager` and full capital. They do not share capital or position slots.
- The "Overall P&L" in backtest output is additive across isolated runs — not a realistic portfolio simulation.
- `reset_daily=True` (default) resets daily P&L between calendar days. Set `False` for interday backtests.
- SL is anchored to actual fill price, not signal price_hint.

---

## Adding a New Strategy

1. Create `trader/strategies/my_strategy.py` subclassing `Strategy` from `base.py`
2. Implement `on_candle(candle) -> Signal | None` and `name` property
3. Add config section under `strategies:` in the relevant config yaml
4. Register in `main.py` or `main_interday.py` under the strategies list
5. Add to `_build_strategies()` in `scripts/backtest.py`
6. Write unit tests under `tests/strategies/`

---

## Key Decisions

- **Data source:** Kite API only (REST for historical, KiteTicker WebSocket for live). No external providers.
- **Storage:** SQLite for candles, orders, trades. Single unified `candles` table with `instrument` + `timeframe` columns. Separate DB files for intraday vs interday to avoid mixing timeframes.
- **Paper trading:** 2 weeks paper run before going live.
- **Starting capital:** ₹20,000. Per-trade risk 1–5% depending on mode.
- **Telegram alerts:** Deferred — implemented but optional. Skips silently if token/chat ID missing.
- **Deployment:** Local Mac. No AWS. Owner arranges static IP.

---

## Credentials

Never put secrets in source code or logs. All credentials live in `config/.env`:
- `KITE_API_KEY`
- `KITE_API_SECRET`
- `KITE_ACCESS_TOKEN` — refreshed daily via `scripts/login.py`
- `TELEGRAM_BOT_TOKEN` (optional)
- `TELEGRAM_CHAT_ID` (optional)

Token expires every day at midnight IST. Re-run `scripts/login.py` each morning before market open (or automate via launchd).
