---
description: Read-only forensic of a single stock's actual live trades on the EC2 bot — reconstructs each entry/exit from the live DB, explains WHY each exit fired (pattern-top, trailing, stale, hard-stop, hold timeout) against the real candle path and model scores, and quantifies upside left on the table. Use when the user asks "why did <STOCK> exit/trail/sell where it did" on the live server. Advisory only, never writes.
argument-hint: NSE:SYMBOL [--date YYYY-MM-DD]
---

Forensically explain a stock's actual **live** trades on the EC2 bot. Answer "why did it exit there?" — not aggregate performance (use `/live-review` for that).

## Hard rules

- **READ-ONLY. ALWAYS.** Every DB connection MUST be opened with `?mode=ro`:
  `sqlite3.connect('file:/opt/trader/data/market.db?mode=ro', uri=True)`.
  Only `SELECT` / `PRAGMA`. Never write, never `.bak`, never restart the service, never edit config. No exceptions even if the user later asks to "fix" something — surface findings and stop.
- The DB is owned by `trader` and lives under `/opt/trader` (perm-denied to the login user). Run every query via `ssh trader "sudo -u trader /opt/trader/.venv/bin/python -c '...'"`. The `sqlite3` CLI is **not** installed on the box — always use the venv Python's `sqlite3` module.

## Step 0 — Resolve the symbol

The user often mistypes the ticker (e.g. "AETHERENERG" → real symbol `NSE:ATHERENERG`). Before anything else, confirm the symbol exists:

```bash
ssh trader "sudo -u trader /opt/trader/.venv/bin/python -c \"
import sqlite3
c=sqlite3.connect('file:/opt/trader/data/market.db?mode=ro',uri=True)
key=''.join(ch for ch in 'SYMBOL_GUESS'.upper() if ch.isalpha())[:5]
for r in c.execute(\\\"SELECT DISTINCT instrument FROM orders WHERE instrument LIKE '%'||?||'%'\\\",(key,)): print(r[0])
\""
```

If the exact symbol returns nothing, fuzzy-match against `orders`, `signals`, and the `watchlist:` block of `config/config.yaml`. State the corrected symbol you're using before proceeding.

## Step 1 — Pull the raw trade record

For the resolved `NSE:SYMBOL` (and `--date` if given, else the most recent completed round-trip), fetch in one read-only call:

- **orders** — `order_id, direction, order_type, quantity, price, status, mode, placed_at` (last ~15). These are the real fills.
- **signals** — `logged_at, direction, signal_type, price_hint, accepted, reject_reason, exit_reason` (last ~30). `exit_reason` is the smoking gun (`PATTERN_TOP_PARTIAL`, `TRAILING`, `STALE`, `STALE_2`, `TRAILING_EOD_CLOSE`, hard-stop, `STRATEGY`).
- **open_positions** — current state if still held: `entry_price, quantity, held_bars, entry_time, peak_close, trailing_active, low_since_entry, pattern_top_trailing`.

Reconstruct the lifecycle: ENTRY fill → each EXIT fill, with qty, price, time, and exit_reason. Note scale-outs (partial SELLs that don't close the whole position).

## Step 2 — Pull the context the exit fired against

For the trade's date(s), fetch:

- **candles** — `timestamp, open, high, low, close, volume` for the day(s) of the exit. This is the actual price path.
- **model_scores** — `timestamp, p_min, p_max` for the same window. `p_max` (P(local-max)) drives pattern-top exits; `p_min` (P(local-min)) drives entries.

## Step 3 — Pull the params that govern the exits

Read the live `strategies.lr_extrema` block from `/opt/trader/config/config.yaml` AND any `per_stock_params` override for this symbol (override wins via deep-merge). The values you need to interpret exits:

- `exits.trailing.profit_pct` — gain % before the **normal** trailing activates
- `exits.trailing.trail_pct` — trailing distance from peak
- `exits.pattern_top.sell_threshold` — P(local-max) that arms pattern-top
- `exits.pattern_top.scale_out.{enabled,fraction}` — partial scale-out size
- `exits.sell_min_pct` — min gain floor for pattern-top / momentum exits
- `exits.stale.*`, `exits.stale_2.*` — progress-gate exits
- `exits.hard_stop.stop_pct`, `exits.hold_bars`

## Step 4 — Diagnose each exit (the core of this skill)

For every exit fill, prove WHY it fired by tying the recorded `exit_reason` to the candle path + model score + the governing param. Verify the arithmetic to the rupee — e.g.:

- **Pattern-top scale-out**: show `p_max >= sell_threshold` at the signal candle AND gain `>= sell_min_pct`. Show the fraction → qty sold.
- **Trailing (incl. post-scale-out remainder trail)**: identify the peak the trail anchored to, compute `peak × (1 − trail_pct/100)`, and show the candle low that touched it. Be explicit about *which* trail it was — the normal `profit_pct`-gated trail often never activates (check whether gain ever reached `profit_pct`); a same-day exit at small gain is almost always the pattern-top remainder-trail, not the normal trail.
- **Stale / stale_2 / hold_bars / hard-stop**: show the bar count or price level that crossed the threshold.

Then quantify the cost: compare realized exit prices against **hold-to-close** and **hold-to-intraday-high** for the same day. Report gross ₹ left on the table.

## Step 5 — Verdict

Classify the episode:

- **WORKING AS DESIGNED** — exit logic fired correctly per config; the "miss" is an inherent tradeoff (e.g. pattern-top + tight remainder-trail sacrificing trend-day upside for top protection). This is the common case. Name the specific tradeoff.
- **MISFIRE** — a genuine inconsistency (state corruption, phantom trailing from stale `peak_close`/`_trailing_active`, scale-out orphaning the remainder, exit_reason that doesn't match the price path). Cross-check the `MEMORY.md` known-issues (retrain-freeze, scale-out unwired live, etc.) before claiming a bug.

Present a tight table (time / action / qty / price / reason) followed by the root-cause narrative and the rupee cost. If the user wants a config change, do NOT make it here — point them to `/calibrate`, `/watchlist-review`, or a manual config edit, and only after they explicitly ask.

## Notes

- A single-stock single-day result is anecdote, not signal. Resist generalising one trend-day shakeout into "the strategy is broken" — note it, suggest checking whether it recurs across stocks before tuning.
- Timeframe is 15-minute candles; signal `logged_at` for tick-driven exits (trailing/hard-stop) is the tick time, while candle-driven exits (pattern-top/stale/hold) align to candle boundaries.
- If the position is still open, say so and report current unrealised state rather than inventing an exit.
