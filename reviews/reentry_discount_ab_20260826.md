# Same-day re-entry discount gate — A/B result (FALSIFIED)

**Date:** 2026-08-26 · **Verdict:** do not enable. Code kept config-gated, default OFF.

## Trigger

Live, 2026-08-26, NSE:QUESS:

| time | action |
|---|---|
| 09:30 | scale-out 62 @ 357.65 (`PATTERN_TOP_PARTIAL`) |
| 09:55 | trail exit 63 @ 367.10 (`TRAILING`) |
| 11:30 | fresh ENTRY 110 @ 365.45 |

Blended exit 362.41 → re-entered 0.84% **higher** 95 minutes later. Dead-weight
CNC charges on the round-tripped 63 shares: **₹51.33**. The objection is the
basis reset and re-established risk, not the ₹51.

## Live sweep (full order history to 2026-08-26)

14 distinct same-day exit→re-entry events, measured against the *blended* exit price:

- **3** re-entered ≥1.5% lower (genuine dip, value-adding) — ATHERENERG 06-10, QUESS 08-18, NATIONALUM 06-05
- **~6** round-tripped flat, within ±1.5% (pure cost/basis churn) — INFOMEDIA 04-30 ×2, CGPOWER 06-24, REDTAPE 08-12 (−0.01%), QUESS 07-02 (+0.01%), TIPSMUSIC 07-20 (+0.04%)
- **4** bought back materially **higher** in bigger size — QUESS 06-30 (+3.5%), QUESS 07-31 (+3.4%), QUESS 08-26 (+0.8%), CGPOWER 06-04

QUESS alone is 6 of the 14. The July-2026 sweep's "it also catches genuine dips"
defence has weakened (3/14, was 5/13), which is what motivated re-testing.

Because the expensive group buys back *higher*, the symmetric "within ±X%" band
recorded in `project_sameday_reentry_churn` cannot catch it. The gate built and
tested here is therefore **one-sided**: re-entry must be at least
`min_discount_pct` **below** the blended exit. `max_premium_pct` (added during the
A/B) re-opens the top of the band so both shapes are testable from one knob.

## A/B

`scripts/backtest.py --from 2025-01-01 --to 2026-08-26 --cache-only`, identical
candle cache across all arms, 22-name watchlist, capital ₹400k.

| variant | trades | P&L | return | costs | Max DD | Calmar | Sharpe* | Sortino | PF | time-avg util |
|---|---|---|---|---|---|---|---|---|---|---|
| **baseline (OFF)** | **418** | **₹303,326** | **75.83%** | ₹33,730 | ₹52,376 (13.1%) | **3.119** | 0.245 | 0.446 | 1.97 | **61.8%** |
| band ±0.10% | 377 | ₹272,052 | 68.01% | ₹29,824 | ₹52,376 (13.1%) | 2.826 | 0.241 | 0.441 | 1.95 | 59.0% |
| band ±0.25% | 370 | ₹273,046 | 68.26% | ₹29,044 | ₹49,420 (12.4%) | 3.005 | 0.246 | 0.462 | 2.00 | 56.9% |
| band ±0.50% | 332 | ₹258,210 | 64.55% | ₹25,803 | ₹47,081 (11.8%) | 2.998 | **0.253** | **0.475** | **2.01** | 53.9% |
| one-sided 1.5% | 211 | ₹126,618 | 31.65% | ₹14,510 | ₹52,306 (13.1%) | 1.389 | 0.192 | 0.345 | 1.71 | 36.7% |

`max_premium_pct: 1.5` reproduces the one-sided arm **exactly** — no backtest
re-entry is ever priced more than 1.5% above its blended exit, so at that width
the two rule shapes are the same rule.

## Why it fails

- **Monotone in width.** Every setting loses P&L; there is no threshold to tune into.
- **Charges are never the prize.** The ±0.1% band blocks only dead-flat round trips
  and still costs ₹31,274 of P&L to save ₹3,907 of charges — 8:1 against.
- **Drawdown does not improve where it matters.** ±0.1% and one-sided 1.5% leave
  Max DD at 13.1%, identical to baseline. Only the mid widths shave DD, and they
  give up more return than DD, so Calmar never beats baseline.
- **The mechanism is capital idling, not bad re-entries.** Per-trade quality holds
  (win rate 67.7% → 65.9–66.9%, avg win flat) while time-avg utilisation collapses
  61.8% → 36.7%. `TRAILING` exits — the profit engine — halve at 1.5%
  (146t/₹383k → 74t/₹195k). Blocking one re-entry amputates the whole downstream
  trade sequence, exactly the shape that killed `loss_reentry_block` (−₹69k) and
  the blanket `reentry_cooldown` (−₹63k).

## Disposition

- `risk.reentry_discount` stays in the tree, `enabled: false`, alongside the other
  falsified defensive options (`reentry_cooldown_enabled`, `loss_reentry_block`,
  `max_slow_tf_positions`). Reject reason `reentry_discount`.
- 12 unit tests in `tests/test_reentry_discount.py` (blocking, blended-exit
  weighting across scale-outs, accumulator reset on re-entry fill, `reset_day`,
  exit_price=0 eviction, inertness when disabled).
- **Do not re-tune the width.** The response is monotone across 0.1% → 1.5%.

## Loose end (out of scope here)

QUESS is the most churn-active name live (6 of 14 events) yet produces only
**2 trades / −₹3.4k** in this 20-month backtest on the same global 15m params.
That live/backtest divergence is worth its own look — a per-stock rule for QUESS
cannot be validated against a 2-trade backtest sample.
