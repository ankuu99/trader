---
description: Missed-opportunity audit against the live EC2 bot — detects every confirmed swing dip and peak on each watchlist stock's own strategy timeframe from the remote candle history, cross-references actual live fills/signals/model scores to classify each as captured vs missed (and why), and renders a per-stock chart. Use when the user asks "what dips/peaks did we miss", "how much upside did the bot leave on the table", or wants the missed-opportunity graph refreshed. Advisory only, remote reads are read-only.
argument-hint: [--days N] [--min-move PCT] [--cached] [--symbols NSE:X ...]
---

Quantify how many real, tradeable swings the live bot missed, and why.

## Hard rules

- **Remote is READ-ONLY.** The script's single ssh call opens the DB with `?mode=ro` and only SELECTs. Never modify the remote box, config, or service from this skill.
- **Advisory only.** Never change `config.yaml`, the watchlist, or thresholds here — point to `/calibrate`, `/replay`, or `/watchlist-review` and act only on explicit request.

## Step 1 — Run the analysis

```bash
.venv/bin/python scripts/missed_opportunities.py $ARGUMENTS 2>&1
```

Flags (all optional):
- `--days N` — analysis window, default 90 (auto-clamped to the start of live order history)
- `--min-move PCT` — minimum % bounce (dip) / drop (peak) to count as actionable, default 3.0 (matches `sell_min_pct`)
- `--cached` — reuse `data/missed_opp_snapshot.json` instead of re-fetching from EC2 (use when iterating on parameters, or when the user says skip refresh)
- `--symbols NSE:X ...` — restrict to specific names (default: live watchlist, read from the remote config)
- `--tolerance-bars K` — strategy-TF bars before an extremum within which a fill still counts as captured (default 3)
- `--json PATH` — also dump per-dip/per-peak detail

Stdout is a JSON summary; the chart PNG lands in `reviews/missed_opportunities_YYYYMMDD.png`. View the PNG with Read to verify it rendered, and show the user its path.

## What the script does (so you can explain it)

1. One read-only ssh fetch: 15m candles, `model_scores`, orders, signals, and the live `config.yaml` (watchlist + per-stock params). Cached locally.
2. Aggregates each stock's candles to **its own strategy timeframe** (day = 09:15–15:15, 4hour = 09:15–13:15 + 13:15–15:15, frozen boundaries) and finds confirmed local minima/maxima with that stock's `extrema_order` — the same definition the strategy trains on.
3. A dip is **actionable** if the bounce to the next confirmed peak ≥ `--min-move`; a peak if the drop to the next trough ≥ `--min-move`.
4. Each actionable dip is classified:
   - **captured** — a COMPLETE BUY fill between (dip − tolerance) and the following peak
   - **in_position** — already holding, so the entry was structurally impossible (scale-in disabled)
   - **below_threshold** — recorded `p_min` at the dip bar < that stock's entry threshold (model wasn't confident)
   - **blocked** — a risk/broker-rejected signal near the dip, or gates look passed on record but no order exists (investigate individually)
   - **no_score** — no model score recorded at that time (the `model_scores` table keeps only the last 500 rows per instrument) · **vetoed** — `p_max` ≥ veto threshold
5. Each actionable peak **while holding** is either an exit taken near the peak or a **missed peak** (rode the drop).

## Step 2 — Present the findings

Lead with the totals line: actionable dips, captured vs missed, average missed bounce %, peaks-while-holding missed, and the estimated foregone ₹. Then a compact per-stock table (symbol, TF, dips captured/missed, dominant miss reason, peaks missed) sorted by missed count. Reference the chart path.

## Step 3 — Interpret honestly (caveats are mandatory)

- **The foregone ₹ is a gross upper bound, not achievable P&L.** It assumes every missed dip was bought with a full per-stock allocation at the trough and sold at the peak — no strategy achieves that, and capturing more dips would change capital availability for the ones actually taken. Never present it as "lost profit".
- **`in_position` misses are a scale-in question, not a threshold question.** They are the add-on counterfactual (see memory: real expectancy, but 3–4× worse bad quarters — regime brake is prerequisite). Don't recommend loosening thresholds for these.
- **`below_threshold` misses are calibration candidates** — if one stock dominates, suggest `/replay` on specific dips or `/calibrate`, and remember higher thresholds were often deliberately calibrated; missing shallow dips is the accepted cost of avoiding falling knives (knife-state entries were the BEST bucket historically — the enemy is stale-in-uptrend, not the dip itself).
- **`no_score` dominance is a data-retention artifact** (500-row trim), not a model failure — the model may or may not have fired; the record simply doesn't exist. Treat those counts as "unknown", and note that raising the trim would make future audits sharper.
- **Missed peaks while holding** overlap with known, deliberately-accepted tradeoffs (trend-day shakeouts, trailing floors). Cross-check `/review-live-trades` on a specific episode before calling anything a bug.
- **Go-live blindness**: the audit cannot see when a stock joined live trading (e.g. MAYURUNIQ ran on day TF only from 2026-07-05) — misses before a stock's go-live show up as `blocked`/`no_score` but are artifacts. Cross-check `git log -S NSE:SYM -- config/config.yaml` or `journalctl` before acting on a `blocked` anomaly.
- **`blocked` anomalies are often broker rejections, not model failures** — check the orders table for REJECTED and the EC2 journal for "Insufficient funds" (2026-08 forensics: 62 rejections; the model called the KPL/MAYURUNIQ dips at p_min 0.87–0.98 and the orders died on margin).
- Dip/peak detection is **hindsight** — a confirmed extremum needs `extrema_order` bars of future data. This audit measures the ceiling, not what any causal strategy could reach. Never use per-exit-reason win rates here (circular).

## Step 4 — Suggest next steps (do not execute unprompted)

Typical follow-ups to offer: `/replay NSE:X` on the largest missed dips, `/calibrate NSE:X` where `below_threshold` dominates, `/review-live-trades NSE:X` for missed peaks, or a deeper look at any `blocked` anomaly (signals vs orders around that timestamp).
