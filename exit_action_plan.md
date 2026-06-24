# Plan — Exit-action redesign for LRExtremaStrategy

_Forward plan, June 2026. Experimental log + evidence lives in
`exit_mechanism_learnings.md`. This file is the plan of record; update statuses as
steps complete._

---

## Objective

Improve realized P&L **without** sacrificing drawdown control, by changing the
**exit action** (not peak detection). Evidence (`exit_mechanism_learnings.md`,
Findings 1–5) established:

- Peak detection is already high-precision / FN-dominated at the live threshold —
  not the bottleneck.
- Exiting **at** the model's pattern-top (direct, no trailing) is **worse** than
  trailing when pattern-top actually drives exits (@0.85: ₹307k vs ₹424k) — it cuts
  winners short.
- The apparent gains at high `sell_threshold` are a **confound**: they come from
  *holding longer* (pattern-top disabled → ride to `hold_bars`/stale) in a strong
  2023–25 bull, not better timing.
- Trailing's real value is **drawdown protection** (Calmar 2.018 beats every
  direct-exit variant except 0.90).

**Thesis:** both trailing (tight, 2%) and direct pattern-top exit leave money on the
table by exiting early; the win is to **combine upside-capture with
drawdown-protection** — looser/confidence-sized trailing and/or partial scale-out.

---

## Baselines & references (2023-06-01 → 2025-06-01, 15m, full watchlist, cache-only)

| reference | P&L | Return | Win% | Sharpe* | Calmar |
|---|---|---|---|---|---|
| **Trailing baseline** (current prod config) | ₹424k | 169.7% | 54.8% | 0.169 | **2.018** |
| Direct @0.95 (best abs P&L, clean-ish) | ₹466k | 186.4% | 53.1% | 0.201 | 1.499 |
| Direct @0.97 (hold-longer confound) | ₹521k | 208.3% | 49.6% | 0.202 | 1.342 |

**Primary metrics:** Total P&L, Sharpe\*, Calmar (return/max-DD), max drawdown.
**Guardrails:** win rate, trade count, total costs.
**A config "wins" only if it beats the trailing baseline on P&L OR Sharpe WITHOUT
worsening Calmar/max-DD materially (>~10%).**

---

## Validation methodology (applies to every step)

1. **In-sample**: the 2023–25 window above (fast iteration).
2. **Regime control (mandatory before trusting any winner)**: the 2023–25 window is
   a strong bull and flatters "hold longer". Re-run finalists on:
   - `scripts/backtest_rolling.py` over the **full** available cached range
     (`--window 6 --step 3`) — look at *consistency* across windows, not just the
     sum.
   - At least one weak slice (flat/down sub-period) if identifiable in cache.
   A finalist must hold up out-of-regime, not just in the bull.
3. **No look-ahead / no live-divergence**: changes live in `ExtremaExitPolicy`, which
   is shared by backtest and live; keep all new params behind backward-compatible
   toggles (defaults preserve current behaviour).
4. **Decision recorded** in `exit_mechanism_learnings.md` after each step.

---

## Step 0 — Control for the confound: is trailing just too tight? (config-only)

**Question:** how much of the "direct@0.95/0.97" advantage is recoverable by simply
**loosening the existing trailing** (keeping its drawdown protection)? If a looser
trailing reaches ~direct@0.95 P&L (₹466k) **with** Calmar ≥ baseline (2.018), the
answer is "trailing was too tight" and we may stop without writing exit code.

**No code.** Vary existing params only: `trailing.trail_pct`, `trailing.profit_pct`,
`hold_bars`. Trailing stays ON; `direct_exit` stays OFF.

**Method (OFAT first, then a focused grid):**
- Phase A — one-factor-at-a-time around baseline to isolate each effect:
  - `trail_pct`: 2 (base), 3, 4, 5, 6
  - `profit_pct`: 3, 5 (base), 8
  - `hold_bars`: 200 (base), 300, 400
  (~11 runs)
- Phase B — small focused grid around the best 1–2 values from Phase A
  (~6–9 runs).

**Execution:** a throwaway in-memory sweep driver (does **not** touch live
`config.yaml`): load config, deep-copy, override the params per combo, call
`run_backtest()` + `compute_metrics()` (the same engine `backtest.py` uses), print a
portfolio metrics row per combo. Run with INFO logging suppressed (engine cache-only,
`kite=None`). Watchlist + date range identical to the baselines above.

**Decision rule:**
- If a looser-trailing config hits **P&L ≥ ~₹460k AND Calmar ≥ 2.0** → trailing was
  too tight; validate out-of-regime (Step 0 validation), then likely adopt and stop.
- If P&L rises but **Calmar drops below ~1.7** → looseness = unprotected risk;
  proceed to Step 1 (confidence-sized trailing).
- If nothing materially beats baseline → proceed to Step 1.

**Deliverable:** sweep table + decision appended to `exit_mechanism_learnings.md`.

---

## Step 1 — Confidence-sized trailing distance (moderate code)

**Idea:** make the trailing distance a function of current `P(max)` — loose when the
model is unsure a top is near (let it run), tight as `P(max)` rises (lock in before
the drop). Keeps trailing's drawdown protection while front-running confirmed tops.

**Mechanism:**
`trail_pct_eff = lerp(trail_loose, trail_tight, clamp((p_max - a)/(b - a), 0, 1))`
with config: `trailing.confidence_sizing: { enabled, trail_loose, trail_tight, p_lo:a, p_hi:b }`.

**Implementation notes:**
- `tick_exit` currently has no `p_max` — thread the latest `p_max` to the tick path.
  Cheapest: cache `p_max` on `PositionState` whenever `candle_exit` computes it
  (it already does, in the pattern-top block), and read it in `tick_exit`. Note
  staleness (updated at candle granularity) — acceptable; document it.
- Backward-compatible: `enabled: false` → fixed `trail_pct` (today's behaviour).

**Success:** beats baseline P&L/Sharpe with Calmar ≥ baseline, and holds out-of-regime.

---

## Step 2 — Partial / scaled exit at pattern-top (largest change, biggest upside)

**Idea:** on a high-confidence pattern-top, sell a FRACTION (e.g. 50%) and trail the
remainder. Banks profit at the top (win-rate/locked-gain benefit) while keeping
exposure for the patience upside. Optionally scale the fraction by `P(max)`.

**Plumbing required (does not exist today — exits are all-or-nothing):**
- `RiskManager.close_position`: partial-quantity close + remaining-qty tracking in
  `_open_positions` / `_position_values`.
- Strategy / `PositionState`: track remaining qty; keep re-entry gated while
  partially open; preserve `_entry_price`/`fill_price` for the remainder.
- Signal contract: a way to express partial-exit quantity (fraction or qty on the
  EXIT `Signal`).
- Backtest engine: partial-fill accounting in the trade record (one entry → multiple
  exits); costs computed per partial.
- Config: `exits.pattern_top.scale_out: { enabled, fraction, by_confidence }`.

**Risk:** most invasive; touches risk + engine + signal contract. Gate hard behind
`enabled` and add flow tests before trusting numbers.

**Success:** beats Step 1 on P&L AND Calmar, holds out-of-regime.

---

## Step 3 (optional) — Confidence-gated FULL exit on top of trailing

Keep trailing as the default downside manager, but allow an immediate **full** exit
only when `P(max) >= ~0.95` (very confident top). Hybrid of the two shipped toggles;
cheap once Step 1 has threaded `p_max` to the exit path.

---

## Toggles already shipped (2026-06-24)

- `exits.trailing.enabled` (default `true`) — master switch for all trailing.
- `exits.pattern_top.direct_exit` (default `false`) — immediate exit at candle close
  on pattern-top instead of arming trailing.

Backward-compatible; live config unchanged. `tests/test_parity_golden.py` was
already failing on clean HEAD before this work (stale golden, unrelated).

---

## Status

- [x] #8 diagnostic (peak-detection measurement) — shipped, `training_diagnostics` flag.
- [x] Exit toggles (`trailing.enabled`, `pattern_top.direct_exit`) — shipped.
- [x] Strict pattern-top characterization — done (Findings 3–5).
- [x] **Backtest EOD force-close fix** (Finding 6) — engine now honours `force_close_time`;
      trailing no longer rides overnight. Honest baseline 2025-26 = ₹57.4k.
- [x] **Step 0 — trailing-tightness sweep** — trailing too tight; adopted `trail_pct=3,
      profit_pct=10` (+29% P&L, Calmar 1.13→1.62). Tested on 2025-01→2026-06.
- [x] **Step 1 — confidence-sized trailing** — NEGATIVE (₹61k < ₹74k static). Shipped
      behind `confidence_sizing` toggle, default OFF.
- [ ] Step 2 — partial / scaled exit ← in progress.
- [ ] Step 3 — confidence-gated full exit (optional).

### Overnight-trailing future workstream (from user discussion)
Overnight hold beats same-day on P&L+Calmar but needs trailing-state persistence
(`trailing_active`/`peak_close`/`max_gain_pct`) + restart bootstrap before it is safe in
live. Toggle already exists (`force_close_time: null`). Not implemented — documented only.
