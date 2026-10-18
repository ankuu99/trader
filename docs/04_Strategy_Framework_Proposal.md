# Strategy framework for Model Lab models (TD-023) — proposal

Written 2026-10-18 · Status: DESIGN (no build yet) · Branch: `exp/model-lab` · Depends on TD-021 (models), TD-022
(survivorship-free universe)

## Why now

The Model Lab (TD-021, `docs/03`) judges models on their own terms; the strategy was deferred "until a model wins".
The owner asked (2026-10-18) to start designing the strategy while lab runs continue. Designing the framework now is
useful because (a) the strategy's needs decide which model outputs the lab should forecast next (hold, potential,
pain), (b) A01 (day, deep swing lows) is already a stable candidate to prototype on, and (c) the framework is
model-agnostic: it consumes "a score (+ optional magnitude forecasts) per stock per bar". **What waits for a frozen
model is the tuning** (thresholds, exit levels, slot counts) — tuning around a model that is about to change is how
round 1 (TD-018) lost: better detectors died under exits co-tuned with the old one.

## Owner decisions (2026-10-18)

| # | Decision |
|---|---|
| S1 | **Both timeframes: day and 15m.** (A05: the 15m low-finder is real but its 5-day moves are near the cost line — the 15m leg needs its own magnitude work before it can pay.) |
| S2 | **Whole liquid universe** (point-in-time liquidity filter, as in the lab), minus an **exclusion list of really bad stocks** that is revisable. |
| S3 | **Runs on its own, with its own capital**, alongside LR-Extrema. After a few months, compare and switch one of them off. |

## Shape: new decision layer, same execution body

- **Reuse (unchanged):** Kite order placement, RiskManager checks and capital ledger, OrderManager, CNC/long-only,
  the closing-auction (CAS) flushes, pre-order cash check, persistence, Telegram, dashboard. None of it cares where a
  signal came from, and it carries months of live fixes.
- **New:** the decision logic. LR-Extrema's entry and exit stack (7 % trail, stale tiers, pattern-top, per-stock
  params) was co-tuned with production P(min) and is NOT inherited by default; it is one of the exit variants tested.
- **Structural change:** one pooled model scores the whole universe, so the strategy is a **daily cross-sectional
  ranking** — each decision time, rank every candidate and fill the free ₹ slots with the best ones — not a
  per-stock watchlist with per-stock calibration.

## Components (first versions → variants to compare)

| Piece | First version | Variants |
|---|---|---|
| Universe | PIT liquid top-N by trailing traded value | N = 100 / 200 / 500 |
| Exclusions | file-based list with reason + date + review date (below) | — |
| Entry | model picks above a firing-rate threshold, ranked by score, fill free slots | rank by score × predicted potential, or potential ÷ pain |
| Sizing | equal ₹ slots | shrink by predicted pain; scale-in reuse |
| Exits | neutral grid: fixed hold (day 5/20/60 bars; 15m 25/125/500), simple trail, hard stop | model-driven: target = predicted potential, stop = pain quantile, time stop = predicted hold; LR-Extrema's stack as a reference |
| Market filter | none | prior-day VIX vs its trailing year (the one robust signal from TD-018) |
| Costs | `trader/costs.py` CNC (MIS when same-day) | — |
| Fills | next bar open (as the lab's T5 targets) | — |

### Exclusion list ("really bad stocks", revisable)

A versioned file (e.g. `config/strategy_exclusions.yaml`: symbol, reason, added, review-by). Candidate rules to
populate it — each a proposal for the owner to accept or drop:
- fundamentals DISTRESS from the existing fund panel (fundamentals *gate* rather than generate — consistent with the
  fingerprint-discovery finding);
- NSE surveillance lists (ASM/GSM), trade-to-trade (BE series);
- price below a floor (e.g. ₹20) or median daily traded value below a floor;
- data-quality flags from the lab QA (unexplained > 30 % jumps).
Point-in-time in backtests: a rule applies only from the date its data was knowable.

## Evaluation (offline, before any money)

- Walk-forward on the lab's folds (same splits, no peeking): ₹ P&L, max drawdown from peak (the "giveback" framing),
  Calmar, **money-weighted win %**, capital utilisation, per calendar year, ex-2020.
- Baselines: production LR-Extrema backtest (FULL ₹439.2k, TD-018 ISS-14 fix), and the same framework fed a coin score
  (does the model carry the edge, as EXP-20/22 did for production?).
- Parameters chosen inside training windows only; reported out of sample.
- **Survivorship:** ₹ results on today's listed-only universe overstate a crashed-stock buyer most. Before trusting any
  ₹ number, either TD-022 lands or the result is bounded (e.g. price ≥ ₹50 / ex-crashed-name slices).

## Live: running separately with its own capital (open design questions)

1. **Same Kite account, two sleeves.** CNC holdings are merged per symbol at the broker; the post-market reconcile
   reads `holdings()`. If both systems may hold the same stock, positions need an owner tag (or the two systems are
   barred from overlapping symbols). Options: (a) a second bot instance (own config, own SQLite, own capital), with a
   shared ownership table; (b) one process, two strategy sleeves with separate capital in RiskManager. To decide at
   build time; (a) keeps LR-Extrema untouched.
2. **15m on the whole universe live:** ~200 instruments on one KiteTicker is within limits; factor computation every
   15 minutes for 200 names on the t2.micro needs a budget check (docs/03 §7 already requires a pretrained artefact,
   loaded not retrained, and no torch on the box).
3. **Day bars:** one decision per day on the frozen 09:15–15:15 bar (emitted ~15:14:15 for CAS names, existing flush).
4. **Paper first:** recommended — a paper period for the new sleeve before real money, as with past structural changes.
5. **Switch-off review:** a pre-registered comparison after N months (metrics above, per ₹ of capital deployed); the
   date and N to be set when it goes live.

## Phases

| Phase | What | Gate |
|---|---|---|
| S0 | Lab portfolio simulator (offline, model-agnostic: scores in, ₹ curve out; daily cross-sectional ranking, slots, costs, exit library) | unit tests + reproduce a hand-computed toy portfolio |
| S1 | Neutral-exit study on A01 (day) and A05 (15m) scores; coin control; baselines | design only — no tuning promoted until the model is frozen |
| S2 | Survivorship bound / TD-022 | before trusting ₹ |
| S3 | Model-driven exits once magnitude models pass the vol-referenced test | — |
| S4 | Live adapter (pretrained artefact, live factors, sleeve accounting), paper, then own capital | spec-first in `to_develop/` |
