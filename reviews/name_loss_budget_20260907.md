# Per-stock rolling loss budget — stratification, 2026-09-07

**Trigger:** QUESS live 2026-09-07 — STALE_REARM exit at 341.60 (−9.2% on the 09-01 lot,
stop was 301.04) and a re-entry 30 min later at 341.51 with a fresh 20% stop at 272.96. The
hard stop re-anchors on every lot, so nothing caps how much one name can lose across
repeated rounds.

**Proposal (user):** each stock carries a loss budget of 20% of lot notional over a rolling
quarter. Realised losses consume it; a new lot's hard stop is tightened to the REMAINING
budget (entry × (1 − remaining%)); entries are blocked once the budget is exhausted. Two
ledger variants: losses-only (wins don't restore) and drawdown (giveback from the name's
rolling high-water mark, wins restore).

**Method:** `scripts/name_loss_budget_study.py` on the ₹6L post-REDTAPE baseline
(`backtest_results/portfolio_20250101_20260903_15m_20260904_005215.csv`, 819 lots →
589 rounds, ₹482.0k net, 2025-01 → 2026-09). Step 1: bucket every round by remaining
budget at entry and read its ACTUAL P&L (is the low-budget bucket negative-EV?). Step 2:
static replay against the 15m candle cache — tighten the stop / block the entry and
recompute. Static: freed capital not redeployed, ledger not recomputed with the tightened
losses.

## Step 1 — is the next entry worse after the name has lost money?

No. Every bucket is positive under both ledgers, and the nearly-exhausted bucket is the
BEST one.

| Remaining budget at entry (90d, 20%) | losses-only: rounds / P&L / avg / win% | drawdown: rounds / P&L / avg / win% |
|---|---|---|
| untouched | 98 / ₹107.0k / ₹1,092 / 61.2 | 237 / ₹246.5k / ₹1,040 / 63.7 |
| 75–100% left | 72 / ₹38.2k / ₹530 / 55.6 | 131 / ₹46.6k / ₹356 / 54.2 |
| 50–75% left | 114 / ₹79.2k / ₹694 / 54.4 | 115 / ₹65.7k / ₹571 / 53.0 |
| 25–50% left | 129 / ₹94.8k / ₹735 / 58.9 | 63 / ₹67.3k / ₹1,068 / 68.3 |
| **0–25% left** | 63 / ₹102.7k / **₹1,630** / **71.4** | 24 / ₹42.3k / **₹1,761** / 54.2 |
| exhausted (≤0) | 113 / ₹60.0k / ₹531 / 59.3 | 19 / ₹13.6k / ₹718 / 57.9 |

Control (same shape as the falsified loss-re-entry block): rounds entered right after a
losing round avg ₹660 (53.6% win, 224 rounds) vs ₹935 after a win — lower, but clearly
positive. There is no bucket where blocking helps.

## Step 2 — static replay of the rule

| Setting | losses-only Δ | drawdown Δ |
|---|---|---|
| **90 d, 20%, floor 3%** (the proposal) | **−₹117.9k** (144 blocked, 31 stopped early) | **−₹28.0k** (28 blocked, 17 stopped) |
| 30 d, 20% | −₹47.3k | −₹6.7k |
| 180 d, 20% | −₹275.1k | −₹77.5k |
| 90 d, 30% | −₹59.1k | −₹6.2k |
| 90 d, 15% | −₹240.6k | −₹136.7k |
| 90 d, 20%, floor 0 (stop-tighten only, block only at ≤0) | −₹113.5k | −₹28.7k |

Monotone in strictness, negative at every point, both ledgers. The stop-tightening half
loses on its own (drawdown ledger: 17 rounds stopped early, −₹20.9k, 4 of them actual
winners) — same finding as the 10%/15% hard-stop falsification of 2026-07-05: the dips
that go −8% and recover are the ones a tighter stop converts into realised losses.

**QUESS is the worst case for the rule (losses-only: ₹38.5k → ₹11.2k over 74 rounds).**
Its backtest pattern is exactly today's: Jan–Feb 2025 stacks −5.0/−3.6/−3.3/−2.5/−4.9%
and exhausts the budget, then Mar–Apr 2025 runs +4.6/+3.3/+3.4/+8.5/+10.0% — every one
of those recovery rounds is blocked. Mar–Jun 2026 repeats it (−7.4% then +4.6/+3.7/+4.2/
+2.7/+3.9/+4.7/+7.7% all blocked). Other big losers under the rule: CGPOWER −₹16.7k,
ADFFOODS −₹13.8k, CHENNPETRO −₹12.5k. Only ACMESOLAR gains (+₹5.7k).

## Verdict

**FALSIFIED — do not build.** The per-name loss stack the user is worried about is real
(QUESS, THANGAMAYL, ADFFOODS all show 3–5 losing rounds in a row), but the rounds that
follow it are the strategy's best entries, not its worst. This is the fourth guard in the
"don't rebuy after a loss" family to fail (blanket cooldown, loss-re-entry block,
re-entry discount, now the rolling budget) and the second tighter-stop rule to fail, and
both halves fail for the same reason each time: a mean-reversion strategy's edge lives in
the rebuy after the drawdown. A per-name budget removes it precisely when it is largest.

What actually bounds the per-name loss today: the rolling stale re-arm (bar-40 check at
the −2% floor on every lot), not the 20% stop. The 272.96 line on the new QUESS lot is a
gap-crash circuit breaker, not the expected exit.

If the user still wants a per-name kill switch it should be discretionary (the dashboard
pause flag), not a rule — every rule-shaped version of it tested negative.
