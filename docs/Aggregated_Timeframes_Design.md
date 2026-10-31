# Aggregated Timeframes — Design

**Status:** IMPLEMENTED 2026-07-03 (decisions 3 and 15 revised during implementation —
completion-based emission; decision-time stamping for signals/model_scores).
**Date:** 2026-07-03

## Goal

Two features, built as one mechanism:

1. **Higher timeframes (4h / day) built by aggregating 15-minute base candles**, so that
   a "day" bar covers 09:15–15:15 and the model can decide — and enter — the same day,
   ~15 minutes before close, instead of waiting for the next morning's open.
2. **Per-stock timeframes** — e.g. ATHERENERG on 15m, CUPID on 4h, another stock on day —
   all driven off the same 15m base feed.

## Why aggregate from 15m instead of using Kite native day candles

- **Actionability.** Native day candles close at 15:30 (+ closing auction); acting on them
  means next-day open and the overnight gap. A synthetic 09:15–15:15 bar leaves time to
  place a same-day CNC entry.
- **Train/live distribution consistency.** The model must train on the exact bar shape it
  sees live. Warm-up history is therefore built by aggregating cached 15m candles with the
  same truncation rule — never from Kite's native `day` interval.
- **Backtest fidelity improves.** The strategy sees aggregated bars, but the engine keeps
  checking intrabar SL/target and simulated ticks against each underlying 15m candle —
  sequence-accurate stop resolution instead of guessing within a day-wide bar.

## Architecture

One new pure component, shared by live and backtest (no divergence):

```
trader/data/aggregator.py
  CandleAggregator(target_tf)          # "15minute" = passthrough
    .add(base_15m_candle) -> completed_candle | None
    .flush() -> partial_candle | None
```

- **Live:** `LiveFeed` always assembles 15m base candles. `handle_candle` in `main.py`
  routes each base candle through the symbol's aggregator; `strategy.on_candle` fires only
  when the aggregator emits. `on_tick` (hard stop, trailing) is untouched — tick-speed,
  timeframe-agnostic. Slow entries, fast exits.
- **Backtest:** the merged chronological stream stays at 15m (portfolio simulation stays
  correct across stocks on different TFs). Per-symbol aggregators feed strategies; fills,
  intrabar SL/target, and simulated ticks run on the 15m stream.
- **Warm-up:** fetch 15m history, replay through the same aggregator class, then through
  `on_candle` as today.
- **Config:** `timeframe:` becomes a `per_stock_params` key (deep-merged like the existing
  overrides); global base feed is fixed at 15m. Default `timeframe: 15minute` = passthrough,
  zero behaviour change for existing stocks.

## Bar boundaries (truncation rule — FROZEN once caching of training history begins)

| Strategy TF | Bars | Dropped tail |
|---|---|---|
| 15minute | native base candles | — |
| 4hour | 09:15–13:15, 13:15–15:15 | 15:15–15:30 dropped from second bar |
| day | 09:15–15:15 | 15:15–15:30 dropped |

Aggregated bar `timestamp` = bucket start (matches existing convention). Volume = sum.

## Decisions

1. **Only 15m candles are persisted.** Aggregated bars are always derived in memory via the
   shared class — never written to SQLite. Cheap, single source of truth, no poisoned cache
   if a truncation rule ever changed. Also avoids a collision: the store already holds a
   `"4hour"` series for the ht_trend gate whose second bar includes 15:15–15:30 — a
   *different* bar than the strategy 4h bar.
2. **Strategy-4h ≠ ht_trend-4h, accepted.** The ht_trend gate keeps its Kite-boundary 4h
   series (coarse regime filter, not a training input). Documented here to pre-empt the
   inevitable "why are the 4h bars different?" question.
3. **Completion-based emission (revised during implementation).** A bar is emitted the
   moment its *last member* candle is added — the 15m candle whose end touches the bucket
   end (the 15:00 candle completes the day bar and the second 4h bar; the 13:00 candle
   completes the first 4h bar). Rationale: LiveFeed only emits a base candle when the next
   bucket's first tick arrives, so waiting for a "trigger" candle past the boundary would
   delay every live decision by a full base candle (the 15:15 candle completes at 15:30 —
   too late to trade). Fallbacks for missing data: a tail candle (>= 15:15, trigger-only,
   OHLCV discarded) or any candle from a later bucket/date closes out a stale partial, and
   a clock-based scheduler flush (~15:16 IST) covers stocks that print nothing after the
   last member. Side benefit: backtest fills land on the 15:15 candle's open (≈ price at
   15:15) — same-day, matching live.
4. **Partial bars on short sessions (early close, Muhurat, halts): emit anyway.** The
   aggregation code is shared, so warm-up history contains the same partial bars —
   consistent train/live.
5. **Two hold counters, never conflated.**
   - Strategy `_held_bars` counts *strategy-TF* bars (fires in `on_candle`). All exit logic
     — `hold_bars` timeout, `min_hold_before_exit`, pattern-top — runs on strategy-TF
     counts. `hold_bars: 20` on a day-TF stock = 20 trading days, exiting at a ~15:15 bar
     close.
   - Engine trade-record `held_candles` counts *base 15m* candles — reporting/UI only
     (wall-clock-comparable hold durations across stocks), drives no exits. Optionally also
     record `held_bars_tf`.
6. **Warm-up fetch depth is derived, not configured:** roughly
   `(warmup_bars + lookback_bars) × bars_per_day(timeframe) × ~1.4` calendar days of 15m
   history per stock. One-time fetch, cached.
7. **Day-TF lookback defaults are much smaller than 15m defaults.** The binding constraint
   is labeled extrema count, not calendar depth: with `extrema_order` 3–5 on daily bars,
   ~250 bars yields only ~20–40 labeled samples. Starting point `warmup_bars: 100`,
   `lookback_bars: 300–400` (~1.5 years); final values from per-stock calibration.
8. **Every TF-sensitive param must be per-stock overridden for non-15m stocks** —
   `hold_bars`, `extrema_order`, `stop_pct`, `trail_pct`, `retrain_every`, `lookback_bars`,
   `warmup_bars`, … The global defaults are 15m-calibrated and actively harmful on higher
   TFs. Add a startup validation warning: "day-TF stock using global <param>".
9. **`timeframe` is never a calibration search dimension.** Manual per-stock decision;
   searching it overfits the TF to the backtest window. `calibrate.py` reads the stock's
   `timeframe` from `per_stock_params`; `--timeframe` becomes a strategy-TF override for
   that run.
10. **Fills happen at the next *base* 15m candle open**, not the next aggregated bar. A
    day-TF entry decided at 15:15 fills at the 15:15 candle's open in paper/backtest
    (same-day, the whole point), within seconds in live.
11. **Live restart mid-day must rebuild aggregator partial state.** On startup, replay
    today's already-persisted 15m candles through the aggregator before going live —
    otherwise a restart at 12:40 makes the next day bar cover only 12:45–15:15 (corrupted
    bar fed to the model). Only 15m is persisted, so this is a pure replay.
12. **Day-TF stocks should use market orders.** Entries fire ~15:15; `order_type: limit`
    would face near-certain EOD cancellation.
13. **`model_scores` / conviction UI run in strategy-TF bars.** The 80-candle backfill and
    sparkline become 80 *days* for a day-TF stock — fine, but the dashboard must label each
    stock's TF next to the sparkline.
14. **Dashboard candle queries are unaffected** — every `candles` query in
    `trader/ui/template.py` reads `timeframe = config.candle_timeframe`, which stays
    `15minute` (the only persisted series). Price sparklines / chart page / trade markers
    keep working at 15m granularity for all stocks.
15. **Timestamp convention (revised during implementation):** aggregated bars are stamped
    at bucket start, but `model_scores` rows and `signals` rows are stamped at *decision
    time* — the triggering base candle's timestamp (or the eod-flush wall clock). This
    keeps the signals table honest (a 15:15 decision shows as 15:15, not 09:15) and the
    "Model (since entry)" sparkline query (`timestamp >= entry_time`) correct with no
    bar-duration workaround.
16. **Cadence must be visually labelled.** P(buy)/P(sell) cells and the decision badge
    update once per aggregated bar (once/day at ~15:15 for day-TF) — without a TF badge and
    an "as of <bar>" annotation this reads exactly like the retrain-freeze stale-model
    failure signature. `held_bars` and warmup "candles=N" are strategy-TF units and need
    TF-aware labels. `state.py` / `server.py` need no changes; the template reads
    `config.strategy_timeframe(sym)` directly.

## Non-changes

- `RiskManager`, `OrderManager`, `costs.py` — TF-agnostic already.
- Engine day-boundary logic (`reset_day`, LIMIT EOD cancellation) keys off timestamps.
- `on_tick` hard-stop/trailing path — unchanged, still tick-speed in live and fed
  high/close per 15m candle in backtest.
- Existing 15m watchlist stocks — passthrough aggregator, zero behaviour change.

## Known-issue interaction

The phantom-warmup **retrain-freeze bug** gets more expensive on day TF: `retrain_every: 50`
= 50 *days*, so a frozen stale model persists for months. Verify the retrain guard before
running anything live on higher TFs.

## Implementation order

1. `CandleAggregator` + tests (pure function; sanity-check against Kite's own 60m/day bars).
2. Backtest engine integration — enables per-stock day/4h calibration immediately.
3. Live path: `handle_candle` routing, warm-up replay, mid-day restart rebuild, 15:16 flush
   job in the scheduler.
4. UI: TF labels on watchlist/conviction rows; hold-duration columns.

Nothing changes for existing 15m stocks at any step.
