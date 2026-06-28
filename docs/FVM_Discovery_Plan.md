# Fundamental-Fingerprint Discovery — Plan

**Status:** PLAN (not built). Written 2026-06-29. Companion to the fund-panel integration
(`scripts/fund_panel.py`) and the existing price/fit-based `discover` skill.

## Goal
A **new discovery axis**: find LRExtrema candidates by *fundamental similarity to stocks that
already trade well*, rather than by price-shape fit alone. The user's framing: "see which stocks
perform well in backtest, look at their fundamentals on Trendlyne, and find more *similar* stocks
that could do well on LRExtrema." This complements `discover` (which ranks by mean-reversion fit
on price candles) by adding a fundamental look-alike signal.

## Core hypothesis — and the trap it must survive
**Hypothesis:** stocks LRExtrema trades profitably share a *fundamental fingerprint* — the
quality/stability that makes a dip recover rather than continue (the two-sided insight: quality
is what causes mean-reversion; CUPID is the motivating case). If true, scoring the universe by
similarity to that fingerprint surfaces look-alikes worth gating.

**Why this is dangerous and how the plan defends against it:**
- **Small-N winners.** Only ~34 names clear a modest bar in `results/screen_2024_2026.csv`
  (ret>5%, WR≥50%, trades≥3); **0** clear a strong bar. A fingerprint learned over ~250
  correlated Trendlyne factors on a few dozen names is pure overfit. → **≤10 interpretable
  factors, robust stats, out-of-sample validation, ready to report a null result.**
- **Regime-blind backtest.** A "winner" may be a survivor of one regime. → the fingerprint only
  *proposes*; the **forward gates dispose** (trend_guard + fund_panel + qualify).
- **The meta-labeling lesson** (`project_meta_labeling.md`): a secondary filter once *worsened*
  outcomes. → treat this skeptically; if validation (Step 5) fails, **stop and keep fund_panel as
  a pure gate** — do not ship an unvalidated fingerprint.

## Data reality (grounding)
- **Winner pool sources:** `results/screen_2024_2026.csv` (~34 modest winners, global params) ∪
  the 15 calibrated `per_stock_params` names (de-facto winners someone bothered to tune/keep) ∪
  live-confirmed names (via `live-review`). Pool ≈ 40–50 after dedup. Weak signal — acknowledge it.
- **Fundamentals:** ~40 symbols ingested + on-demand fetch (`fund_panel` / `fvm_ingest --symbols`),
  bounded by the Trendlyne 50/day budget. Scoring a 500-name universe needs fundamentals for all
  of them → coverage is the gating prerequisite (Step 0).
- **PIT correctness:** a 2024 winner must be fingerprinted on its *2024* fundamentals, not today's
  (`factors.all_factors(..., asof=<trade period>)`). The store is already point-in-time.

---

## Plan (ordered)

### Step 0 — Prerequisite: fundamentals coverage
Fetch FVM fundamentals for (a) the entire winner pool (small, do first via `fvm_ingest --symbols`)
and (b) the candidate universe (Nifty500, via the daily ingest). Gate Steps 2+ on having
fundamentals for ≥~80% of both. Cheap reuse: the daily ingest is already filling the universe.

### Step 1 — Define winner / loser labels  (`scripts/fingerprint_label.py`)
- **Winner:** pooled from the three sources above; explicit, conservative bar; record N and the
  trade period per name (for PIT fingerprinting).
- **Loser / baseline:** names with adequate trades but poor metrics (ret<0 **or** WR<35%), **plus**
  a random universe baseline (to distinguish "winner trait" from "any-stock trait").
- If N_winner < ~25, widen the window or relax the bar but **flag low statistical power** loudly.

### Step 2 — Compute fundamental fingerprints
- Small interpretable factor subset from `trader/fvm/factors.py` (~10): `yoy_profit_growth`,
  `growth_acceleration`, `earnings_consistency`, `opm_trend`, `roce`, `roce_trend`,
  `debt_to_equity`, `cfo_to_np`, `pledge`, `promoter_trend` (+ optional `ev_ebitda`).
- Per name, compute the **PIT factor vector as-of its trade period**. Winsorize; missing → neutral.
- Reuse `factors.py` — do **not** reimplement (FVM hard rule).

### Step 3 — Find DISCRIMINATING factors (the honest core)
- Compare winner vs loser/baseline distributions **per factor** (standardized mean difference /
  Mann–Whitney). Keep only factors where winners *reliably* differ; weight by discriminative power.
- **If no factor separates → the hypothesis fails. Report the null and STOP.** This is the
  meta-labeling guardrail made concrete: we do not proceed on a fingerprint that doesn't exist.
- Output: a weighted, signed factor profile (the "fingerprint") + a plain-English description
  (e.g. "winners cluster on high+rising ROCE, low D/E, accelerating profit, no pledge").

### Step 4 — Similarity-score the universe
- For each universe candidate (PIT today), compute weighted distance to the winner profile on the
  discriminating factors → `fundamental_similarity` ∈ [0,1], with per-factor contributions
  (interpretable, like `fund_panel` drivers / the UI's explainability tooltip).

### Step 5 — Validate before trusting (critical, do not skip)
- **Out-of-sample test:** build the fingerprint on pre-2025 winners; check whether *high*-similarity
  names had materially better LRExtrema backtest performance in 2025 than *low*-similarity names
  (or leave-one-out across winners). Reuse `trader/backtest/engine.py` cache-only.
- **Decision:** high-similarity ⇒ better forward performance → proceed to Step 6. Otherwise →
  **null result; the fundamental axis adds nothing beyond fund_panel as a gate; stop and document.**

### Step 6 — Wire into discovery (only if Step 5 validates)
- New `--mode fingerprint` on `scripts/discover.py` (or a thin `scripts/fvm_discover.py`): rank the
  universe by `fundamental_similarity`, then funnel the top names through the **existing forward
  gates** — liquidity, `trend_guard`, `fund_panel`, `qualify`. Discovery proposes; gates dispose.
- Extend the `discover` skill with the new mode; advisory-only; same report contract.

### Step 7 — Report & follow-up
- `reviews/discover_fingerprint_YYYYMMDD.md`: the learned fingerprint (factors + weights +
  description), the validation result (incl. a null if that's what happened), the ranked
  similar candidates with their gate verdicts, and the 1–3 strongest to `/calibrate` then
  paper-trade for 2–4 weeks before promoting. **Never edit the watchlist automatically.**

---

## Guardrails (carry through every step)
- **Small-N discipline:** ≤10 factors, robust stats (median/IQR, winsorize), OOS validation, loud
  low-power flags. No ML/black-box similarity (meta-labeling lesson).
- **PIT correctness:** fingerprint winners on their trade-period fundamentals, not today's.
- **Skepticism:** a null result in Step 3 or 5 is a *valid and likely* outcome — report it, don't
  tune around it.
- **Reuse, don't reinvent:** `factors.py`, `vetoes.py`, `fund_panel.py`, `trend_guard.py`,
  `qualify` — discovery orchestrates them.
- **Advisory only:** never touches `config.yaml`/watchlist without explicit confirmation.

## Relationship to existing tools
| Tool | Axis | Role here |
|------|------|-----------|
| `discover` (price/fit) | mean-reversion *shape* on candles | parallel discovery axis; shares the forward gates |
| `fund_panel` | per-stock fundamental veto + quality | the per-name gate inside Step 6 |
| `fingerprint` (this plan) | fundamental *similarity to winners* | new candidate-generation axis |
| `trend_guard` / `qualify` | structural + qualitative disqualifier | the dispose half of "propose vs dispose" |
