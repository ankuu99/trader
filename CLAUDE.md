# Trader — Project Reference for Claude Agents

## What this is
An automated equity trading system for Indian markets (NSE) using Zerodha/Kite. Supports paper and live modes. Strategies emit signals; a risk layer sizes and places orders; a live WebSocket feed assembles candles.

---

## Running the system

```bash
python main.py                        # paper/live trading (uses config/config.yaml)
python main.py --config <path>        # alternate config
python scripts/backtest.py --from 2025-01-01
python scripts/backtest.py --from 2025-01-01 --to 2025-12-31
python scripts/login.py               # refresh Kite access token
```

---

## Project layout

```
trader/
├── main.py                        # entry point — wires everything together
├── config/
│   ├── config.yaml                # all runtime config (env, capital, strategies, risk)
│   └── .env                       # secrets: KITE_API_KEY, KITE_API_SECRET, KITE_ACCESS_TOKEN,
│                                  #          TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
├── scripts/
│   ├── backtest.py                # standalone backtest runner
│   ├── login.py                   # OAuth flow to get access token
│   └── test_telegram.py           # smoke test for Telegram notifications
└── trader/
    ├── auth/session.py            # create_kite() — authenticates and validates token
    ├── core/
    │   ├── config.py              # Config class + singleton `config`
    │   └── logger.py              # get_logger(), setup()
    ├── costs.py                   # Zerodha brokerage calculator (CNC/MIS)
    ├── data/
    │   ├── historical.py          # get_candles(), warm_up() via Kite REST
    │   ├── live.py                # LiveFeed — KiteTicker WebSocket → candle assembly
    │   └── store.py               # SQLite via Store class (candles, orders, signals tables)
    ├── notifications/telegram.py  # Telegram bot alerts (order fill, P&L, halt, error)
    ├── orders/manager.py          # OrderManager — paper fill simulation + live Kite orders + GTT
    ├── portfolio/tracker.py       # PortfolioTracker — paper position tracking / live Kite fetch
    ├── risk/manager.py            # RiskManager — signal validation, position sizing, exit routing
    ├── scheduler/jobs.py          # APScheduler — pre-market (09:00) and post-market (15:35) hooks
    └── strategies/
        ├── base.py                # Strategy ABC, Signal dataclass, Direction/SignalType enums
        ├── registry.py            # build_strategies(instrument, config) factory
        ├── rsi.py                 # RSIStrategy — entry only
        ├── macd.py                # MACDStrategy — entry only
        ├── zlmtf_macd.py          # ZeroLagMTFMACDStrategy — dual timeframe MACD
        └── lr_extrema.py          # LRExtremaStrategy — self-training logistic regression
```

---

## Config keys (config/config.yaml)

```yaml
env: paper | live
candle_timeframe: 5minute | 15minute | 30minute | 60minute | day
capital:
  total: 50000
  max_risk_per_trade_pct: 7.0
  daily_loss_limit_pct: 10.0
watchlist:
  - NSE:SYMBOL
strategies:
  <name>:
    enabled: true | false
    ...params
risk:
  gtt_enabled: true | false       # master GTT on/off switch
  max_open_positions: 5
  default_sl_pct: 2               # used for GTT SL when gtt_enabled=true
  risk_reward: 4                  # used for GTT target when gtt_enabled=true
  max_capital_per_stock_pct: 25.0
data:
  db_path: data/market.db
  historical_cache_days: 90
```

---

## Core data flow

```
LiveFeed (KiteTicker ticks)
  └─ assemble candles by timeframe
      └─ handle_candle() in main.py
          ├─ orders.on_candle()         → fills pending paper orders at open price
          └─ strategy.on_candle()       → returns Signal | None
              └─ risk.validate(signal)  → returns Order | None
                  └─ orders.place(order)
                      ├─ paper: queues in _pending_paper (fills next candle open)
                      └─ live:  kite.place_order() + optional GTT OCO

LiveFeed (KiteTicker on_order_update) [live mode only]
  └─ orders.on_kite_order_update()
      └─ _dispatch(record)
          └─ handle_order_update() in main.py
              ├─ BUY fill → risk.on_order_filled(), portfolio.on_order_filled()
              ├─ SELL fill → risk.close_position()
              ├─ telegram.notify_order_filled()
              └─ strategy.on_order_update()   → updates strategy position state
```

---

## Signal contract

`Signal` fields (from `trader/strategies/base.py`):
- `instrument`: `"NSE:SYMBOL"`
- `direction`: `Direction.BUY | Direction.SELL`
- `signal_type`: `SignalType.ENTRY | SignalType.EXIT`
- `price_hint`: float — indicative price (LTP / candle close)
- `strategy`: str — strategy name
- `atr`: float | None — optional ATR for risk sizing
- `target_price`: float | None — if set, RiskManager uses this as GTT target
- `stop_loss_hint`: float | None — if set, RiskManager uses this as GTT SL price

**EXIT signals** bypass RiskManager's position-conflict check. RiskManager returns a SELL Order using the quantity stored from the original ENTRY fill.

---

## Adding a new strategy

1. Create `trader/strategies/<name>.py` — subclass `Strategy`, implement `name` property and `on_candle(candle) -> Signal | None`
2. Register in `trader/strategies/registry.py` — add to `build_strategies()`
3. Add config block under `strategies:` in `config/config.yaml`

Key rules:
- Strategies never import from `orders/` or `risk/`
- Use `self.is_flat()` to gate entries
- Override `on_order_update()` if strategy needs to track fill state (e.g. `_entry_price`)
- For strategy-driven exits: emit `Signal(direction=BUY, signal_type=EXIT, ...)`

---

## RiskManager behaviour

- ENTRY signals: checks halt, max positions, duplicate instrument → sizes quantity
- EXIT signals: skips conflict check → returns SELL Order with stored quantity
- `_open_positions: dict[str, int]` — instrument → quantity
- `on_order_filled()` adds; `close_position()` removes

---

## OrderManager behaviour

- **Paper mode**: queues orders in `_pending_paper`, fills at next candle's open price
- **Live mode**: places market order via `kite.place_order()`, optionally places GTT OCO (`gtt_enabled`), tracks submitted orders in `_live_orders` for fill enrichment
- GTT only placed on BUY/ENTRY orders, never on SELL/EXIT orders

---

## Backtest specifics (`scripts/backtest.py`)

- Uses same `RiskManager`, `OrderManager` (paper mode), and `Strategy` instances as live
- GTT simulation (check candle low vs SL, high vs target) only runs when `gtt_enabled: true`
- When `gtt_enabled: false`, exits come exclusively from strategy EXIT signals
- Trade table columns: Entry Date, Exit Date, Instrument, Entry, Exit, Qty, P&L, P&L%, Reason
- Reason values: `SL`, `TARGET` (GTT sim), `STRATEGY` (strategy EXIT signal), `OPEN@END`
- Fill model: paper fills at **next candle's open** — realistic slippage for candle-close signals

---

## LRExtremaStrategy (`trader/strategies/lr_extrema.py`)

Self-training logistic regression that identifies local price extrema.

**Config params:**
| Key | Default | Meaning |
|-----|---------|---------|
| `warmup_bars` | 200 | Candles before first training |
| `threshold` | 0.70 | Min P(local-min) to trigger BUY |
| `profit_pct` | 3.0 | Profit target % |
| `stop_pct` | 3.0 | Stop-loss % |
| `hold_bars` | 150 | Max bars to hold (~10 trading days at 60min) |
| `retrain_every` | 50 | Retrain every N new candles |
| `extrema_order` | 5 | Neighbourhood half-window for extrema detection |

**Features (6):** volume, normalised price `(close-low)/(high-low)`, linear regression slopes over 3/5/10/20 bars.
**Training labels:** local minima = class 0 (buy), local maxima = class 1 (sell). No scipy — manual extrema detection.
**Exits:** strategy-driven (not GTT). Emits `SignalType.EXIT` on profit target, stop-loss, or max hold.

---

## Costs (`trader/costs.py`)

```python
from trader.costs import order_cost, round_trip_cost
order_cost(product="CNC", side="BUY", quantity=100, price=500.0)
round_trip_cost(product="CNC", quantity=100, entry_price=500.0, exit_price=510.0)
```

Covers: brokerage, STT, NSE transaction charges, SEBI charges, GST, stamp duty. CNC brokerage = zero.

---

## Notifications (`trader/notifications/telegram.py`)

Configured via `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`. Safe to call when unconfigured (logs warning, no crash).

Functions: `notify_order_filled`, `notify_order_rejected`, `notify_daily_pnl`, `notify_halt`, `notify_error`, `notify_startup`

---

## Known design decisions

- **Product is always CNC** (delivery) — hardcoded in `Config.product`. No intraday/MIS support.
- **Long-only** — all signals are BUY direction. No short selling.
- **Paper state is in-memory** — does not survive restarts. Live mode re-fetches from Kite on startup.
- **Paper fill timing** — fills at next candle open (not at signal close). Causes ~0-2 bar slippage in backtest.
- **GTT fires not confirmed via on_order_update** if GTT was placed before a live order update arrives — this is a known edge case for GTT-triggered exits.
- **Scheduler timezone** — IST (Asia/Kolkata). Pre-market at 09:00, post-market at 15:35.

## Zerodha CNC order EOD rules (important)

| Order type | Used by this system | EOD behaviour |
|---|---|---|
| CNC Limit | No | Cancelled at 3:30 PM if unfilled |
| CNC SL / SL-M | No | Cancelled at 3:30 PM — must re-place next day |
| CNC Market | Yes (entry + exit) | Fills immediately during market hours — no cancellation risk |
| GTT (Good Till Triggered) | Yes (SL + target when `gtt_enabled: true`) | Persists across days — not cancelled at EOD |

**Paper vs live simulation mismatch for end-of-day signals:**
In live mode a market order placed at e.g. 15:15 fills within seconds (same day). In paper mode the same signal queues and fills at the **next candle's open** (next trading day 09:15 if it's the last candle of the day). This means:
- Paper mode overstates overnight gap risk for signals that fire during market hours
- Backtest P&L will be slightly more pessimistic than live for late-day signals
- This is an accepted approximation — fixing it would require intraday fill simulation
