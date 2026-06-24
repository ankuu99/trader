# Learnings — LRExtrema exit mechanism (peak detection → exit action)

_Experimental log + conclusions, June 2026. Companion to `meta_labeling_learnings.md`._

## The question we started with

The top (sell-side) detector "identifies way too many peaks" — could improving
top identification quality (fewer false positives **and** false negatives) improve
results? We built measurement first (#8), then tested recalibration, and the
investigation pivoted to the **exit mechanism**.

---

## #8 — Peak-detection diagnostic (shipped)

Added an opt-in out-of-sample diagnostic to `LRExtremaStrategy._train`
(`trader/strategies/lr_extrema.py`), gated behind `training_diagnostics`
(default **false**). Each retrain it does a temporal 70/30 holdout, fits a
throwaway eval model on the **earlier** slice only, and scores the held-out tail
at the live operating thresholds. Emits two `print` lines (so they survive the
backtest's `ERROR` log level):

- `DIAG <sym>` — per-class precision/recall at the operating thresholds + the
  P(max) separation (mean on true tops vs non-tops).
- `SWEEP <sym>` — pooled (across retrains) precision/recall curve over a
  `sell_threshold` grid (0.45…0.90). Holdouts overlap across retrains, so this is
  a **relative** recalibration aid, not an unbiased estimate. Take the **last**
  SWEEP line per symbol (full pooled curve).

Enable with `strategies.lr_extrema.training_diagnostics: true`, run a backtest,
`grep '^DIAG\|^SWEEP'`.

### Finding 1 — the premise was inverted

OOS across all 15 watchlist stocks (2yr daily, measured at the live
`sell_threshold=0.85`):

| metric | value | meaning |
|---|---|---|
| TOP precision | 0.97–1.00 | when it fires a top, it's almost always real → **FP already ~0** |
| TOP recall | 0.10–0.40 (≈0.25) | catches ~1 in 4 real tops → **FN-dominated** |
| P(max) separation | +0.39…+0.50 | true tops ≈0.75, non-tops ≈0.27 → discriminates well |

At the decision threshold the detector is **high-precision / low-recall** — it
*under*-fires. The "too many peaks" impression is the raw P(max) stream / the
geometric maxima labels (every local high), not the actual trading firings.

---

## Recalibrating `sell_threshold` (tested, not committed)

The PR curves show that a precision≥0.97 floor sits at a per-stock threshold of
~0.55–0.70 (vs 0.85), recovering recall to **0.6–0.9** at essentially unchanged
precision. Applied as per-stock `exits.pattern_top.sell_threshold` overrides:

| | Baseline (0.85) | Recalibrated (0.55–0.70) |
|---|---|---|
| Total P&L | ₹424,290 | ₹419,737 |
| Return | 169.7% | 167.9% |
| Sharpe* | 0.169 | 0.154 |
| Trades | 883 | 990 |
| Win rate | 54.8% | 53.5% |
| Costs | ₹81,872 | ₹93,716 |

### Finding 2 — better detection does NOT convert to P&L, because of trailing

Detection improved hugely; P&L was within ₹5k while taking **107 more trades and
₹12k more costs**. That means the recalibrated exits pulled *more gross profit* but
**trailing bled it back**: even when the model correctly flags a top, the position
arms a trailing stop instead of exiting, and gives the gain back on the pullback.

**The bottleneck is the exit ACTION, not peak detection.** `pattern_top` only
*activates trailing* (`extrema_exit.py`), gated by `sell_min_pct` / `min_hold` —
so detection quality is decoupled from realized returns.

### Implication for a split top/dip model (#7)

Lower priority. A bare two-model one-vs-rest split is also a mathematical no-op
with only {0,1} labels (`P(max) ≡ 1 − P(min)`); it would need a neutral class, and
per `meta_labeling_learnings.md` enriching the primary model has not paid off.
Model-side detection work is unlikely to move P&L until the exit action changes.

---

## Toggles introduced (for the strict pattern-top test)

Two backward-compatible switches (defaults preserve current behaviour):

- `exits.trailing.enabled` (default `true`) — master switch for ALL trailing
  (both the fixed-percent activation in `tick_exit` and pattern-top trailing in
  `candle_exit`).
- `exits.pattern_top.direct_exit` (default `false`) — when `true`, a pattern-top
  fires an immediate EXIT at the candle close instead of arming trailing.

Strict pattern-top baseline = `trailing.enabled: false` + `pattern_top.direct_exit:
true`. Keeps the hard stop (20% black-swan), `hold_bars`, and stale tiers as
failsafes. `sell_min_pct` / `min_hold` still gate pattern-top (levers).

_Note: the parity golden (`tests/test_parity_golden.py`) was already failing on
clean HEAD before this work — stale golden, unrelated._

## Results — strict pattern-top exit (no trailing)

All runs: 2023-06-01 → 2025-06-01, 15m, full watchlist, `--cache-only`. Strict =
`trailing.enabled: false` + `pattern_top.direct_exit: true`. Only `sell_threshold`
varied (global).

| variant | P&L | Return | Win% | Sharpe* | Calmar | Trades | Costs |
|---|---|---|---|---|---|---|---|
| **Trailing baseline** | ₹424k | 169.7% | 54.8% | 0.169 | **2.018** | 883 | ₹82k |
| Direct @0.85 | ₹307k | 122.9% | **57.6%** | 0.150 | 1.325 | 973 | ₹87k |
| Direct @0.90 | ₹396k | 158.3% | 55.8% | 0.178 | 2.173 | 930 | ₹86k |
| Direct @0.95 | ₹466k | 186.4% | 53.1% | 0.201 | 1.499 | 779 | ₹73k |
| Direct @0.97 | ₹521k | 208.3% | 49.6% | **0.202** | 1.342 | 788 | ₹77k |

### Finding 3 — exiting AT the model's top is worse than trailing (clean test)

Exit-reason mix shifts with threshold:
- @0.85: PATTERN_TOP **533** (dominant), STALE 353, hold_bars 85 — pattern-top is
  genuinely the exit. Result ₹307k **<** trailing ₹424k, despite higher win rate
  (57.6%): exiting at the first confident top **cuts winners short**.
- @0.97: STALE 309, hold_bars(200) **262**, PATTERN_TOP 214 — pattern-top is now
  rare.

### Finding 4 — the high-threshold "win" is mostly HOLD-LONGER, not top-timing (confound)

Raising `sell_threshold`→1.0 progressively **disables** pattern-top, converting the
strategy to "hold up to `hold_bars` (200) unless stale". The rising P&L
(₹307k→₹521k) is largely this patience effect in a strong 2023–25 bull, **not**
better top detection. Caveat: regime-dependent — must be validated on bear/sideways
slices and rolling windows before trusting.

### Finding 5 — trailing's value is drawdown protection

Calmar (return / max-drawdown) is **worse** than the trailing baseline (2.018) in
every direct-exit variant except 0.90. Removing trailing removes downside
protection on the pullback before the model calls a top — bigger drawdowns.

### Net conclusion

Two real levers, neither is "replace trailing with direct exit":
1. **Both trailing (2% — tight) and pattern-top exit too EARLY.** Patience captures
   more upside in this regime, at the cost of drawdown.
2. **Trailing provides the drawdown protection** that direct exit lacks.

The productive direction is to **combine upside-capture with drawdown-protection** —
partial scale-out and/or confidence-sized trailing — not to pick one exit.

---

## Plan — productive direction (exit action)

Sequenced cheap → expensive. Measure every step against BOTH the trailing baseline
(₹424k, Calmar 2.018) AND a rolling/out-of-regime slice (the 2023–25 bull flatters
"hold longer").

### Step 0 — control for the confound (config-only, no code)
Isolate the patience effect with trailing's protection intact: sweep
`trailing.trail_pct` (2 → 3 → 4 → 5), `trailing.profit_pct`, and `hold_bars`. If a
**looser trailing** recovers most of the direct@0.95 P&L *with* baseline Calmar,
the answer is simply "trailing is too tight" and we stop here. This tells us how
much of Findings 3–4 is just early exits vs genuine mechanism choice.

### Step 1 — confidence-sized trailing distance (moderate code)
Make `trail_pct` a function of current `P(max)`: loose when the model is unsure a
top is near (let it run), tight as `P(max)` rises (lock in before the drop). E.g.
`trail_pct = lerp(trail_loose, trail_tight, (p_max - a)/(b - a))`. Keeps trailing's
drawdown protection while front-running confirmed tops. Implement in
`extrema_exit.tick_exit` (needs current p_max threaded to the tick path, or
recomputed on the candle and cached on `pos`).

### Step 2 — partial / scaled exit at pattern-top (most code, biggest upside)
On a high-confidence pattern-top, sell a FRACTION (e.g. 50%) and trail the
remainder. Captures the win-rate/locked-profit benefit of exiting at the top while
keeping exposure for the patience upside. Requires partial-exit plumbing that does
not exist today (exits are all-or-nothing; qty is the stored entry qty):
- `RiskManager.close_position` partial-quantity support + remaining-qty tracking.
- Strategy/PositionState: track remaining qty, avoid re-entry while partially open.
- Backtest engine: partial-fill accounting in the trade record.
- Optionally scale the fraction by `P(max)` (scaled exit).

### Step 3 (optional) — confidence-gated full exit ON TOP of trailing
Keep trailing as the default downside manager, but allow an immediate **full** exit
only when `P(max) >= ~0.95` (very confident top). Hybrid of both toggles; cheap
once Step 1 plumbing exists.

### Toggles already shipped (this round)
- `exits.trailing.enabled` (default true) — master switch for all trailing.
- `exits.pattern_top.direct_exit` (default false) — immediate exit at candle close
  on pattern-top instead of arming trailing.

Both are backward-compatible; live config unchanged. The parity golden
(`tests/test_parity_golden.py`) was already failing on clean HEAD before this work.

---

## Finding 6 — BACKTEST BUG: trailing rode overnight (figures were inflated)

Live force-closes active-trailing positions intraday via `force_close_time` (15:25).
But intraday candle timestamps are **start-labelled** — the last NSE 15m bar of the day
is **15:15** (< 15:25), so the strategy's force-close **never fired from candle ticks**,
letting trailing positions ride overnight/multi-day in backtest. On 2025-01→2026-06,
**271/302 trailing exits (90%) were multi-day, contributing ₹270k of ₹292k trailing
P&L** — none of which live (same-day close) could capture.

**Fix (`engine.py`):** mark the last in-window candle of each day per symbol (`_is_eod`)
and feed an extra tick stamped at `trading_end` so the strategy's own force-close fires —
backtest now honours `force_close_time` exactly. New exit reason: `TRAILING_EOD_CLOSE`.

Effect on the baseline: **₹80.5k → ₹57.4k** (the ₹23k was overnight bloat). All prior
trailing figures in this doc above were inflated by this bug.

### Overnight vs same-day (answering "should live hold trailing overnight?")

The pre-fix figure (₹80.5k, Calmar 1.98) *is* the overnight-hold scenario; corrected
same-day is ₹57.4k, Calmar 1.13. So overnight beats same-day on **both** P&L and Calmar
(and the backtest already models overnight gap downside via gap-adjusted stop fills).
**But** overnight trailing in live needs trailing-state **persistence + restart
bootstrap** (`trailing_active`/`peak_close`/`max_gain_pct` survive systemd/token-refresh
restarts), which doesn't exist. Decision: keep same-day force-close as the safe default;
overnight is a documented future workstream (partial infra: `state` table,
`seed_position_state`, `cumulative_pnl` precedent).

---

## Step 0 (corrected engine, honest same-day, 2025-01→2026-06)

Baseline `(trail=2, profit=5, hold=200)`: ₹57.4k, Sharpe 0.085, Calmar 1.134, DD 13.3%.

| trail | profit | hold | P&L | Sharpe | Calmar | DD% |
|---|---|---|---|---|---|---|
| 2 | 5 | 200 | ₹57.4k | 0.085 | 1.134 | 13.3 | baseline |
| **3** | **10** | 200 | **₹74.0k** | 0.103 | **1.617** | **11.9** | ADOPTED |
| 4 | 5 | 200 | ₹74.8k | 0.108 | 1.482 | 13.1 | max P&L |
| 2 | 10 | 200 | ₹70.1k | 0.097 | 1.550 | 11.8 | |

**Decision:** trailing was too tight even on honest figures. Adopted `trail_pct 2→3`,
`profit_pct 5→10` in `config.yaml` (+29% P&L, Calmar 1.13→1.62, lower drawdown).

## Step 1 — confidence-sized trailing (NEGATIVE result)

Trail distance interpolated from live `P(max)` (loose when no top, tight as a top firms).
Best variant ₹61.3k vs the static `(3,10,200)` ₹74.0k — **every CS variant underperformed
static loosening**. Tightening on high `P(max)` reintroduces the early-exit problem.
Shipped behind `exits.trailing.confidence_sizing` (default OFF); left off. The lever is
"let winners run" (static), not "smart trailing."
