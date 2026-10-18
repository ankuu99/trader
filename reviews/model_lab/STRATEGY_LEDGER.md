# Strategy ledger (TD-023) — every portfolio-simulation configuration, registered before it runs

Simulator: `research/model_lab/portfolio.py`. Every config is run with three score sources on identical rows, slots and
exits — the model, a coin (`ref:coin`) and production P(min) (`ref:prod_pmin`). Universe survivor-biased (TD-022):
read ₹ relative to the coin. **No configuration is promoted while the model is not frozen** (docs/04): these are
studies of the framework, not tuning.

## SC1 — capacity (owner: "Try all three options", 2026-10-18)

Problem (`S0_first_sims_20261018.md`): A01's picks bunch on sell-off days → 38 % of capital idle at 15 × ₹40k.
Common: run `A01_day_logit_t1z5`, day bars, ₹6L, exit = sell after 20 bars (the clean exit; stop/trail is a separate
study), costs `trader.costs`. Read: capital in use, net ₹, ₹/trade, money-weighted win %, max DD, Calmar, model vs
coin vs production; per year in the reports.

| ID | Option | Config | Status |
|---|---|---|---|
| SC1-0 | baseline | 15 × ₹40k, top-1 % causal threshold | DONE — ₹7.28 L (= coin median, 11/21), Calmar 0.22 (17/21), DD 34 % vs coin 51 %, use 62 % |
| SC1-1a | fewer, bigger slots | 7 × ₹80k, top-1 % | DONE — worse: ₹3.85 L, Calmar 0.07 (beats 4/21 coins); capital use 66 % |
| SC1-1b | fewer, bigger slots | 5 × ₹1.2L, top-1 % | DONE — worse: ₹5.59 L, Calmar 0.09 (8/21); use 74 % |
| SC1-2a | carry-over queue | 15 × ₹40k, top-1 %, queue 3 bars, drop if close > signal close +2 % | DONE — no help: ₹6.18 L, Calmar 0.15 (9/21); use 63 % |
| SC1-2b | carry-over queue | as 2a, queue 5 bars | DONE — no help: ₹6.57 L, Calmar 0.18 (12/21); use 64 % |
| SC1-3a | top-K per day | 15 × ₹40k, the best 1 score each day (no threshold) | DONE — ₹7.73 L, Calmar 0.24 (18/21); use 72 % |
| SC1-3b | top-K per day | best 2 each day | DONE — **best**: ₹10.40 L (19/21 coins), Calmar 0.27 (20/21), use 90 %; production same config ₹11.60 L / 0.30 |
| SC1-3c | top-K per day | best 3 each day | DONE — ₹10.15 L (19/21), Calmar 0.22 (19/21), use 93 %; production ₹11.34 L / 0.27 |

Luck band: each config also run with 20 extra coin seeds (`coin:101…120`) + the stored coin = 21 draws; "x/21" = coins the model beats. Results and reading: `reviews/model_lab/SC1_capacity_20261018.md`.

## SC2 — hold duration (owner: "Try different hold durations", 2026-10-18)

Day: SC1-3b framework (A01, ₹6L, 15 × ₹40k, best 2 per day, no stop/target/trail), exit = sell after H bars.
15m: A05, ₹6L, 15 × ₹40k, top-1 % causal threshold (the S0 baseline; top-K per 15m bar would trade ~50 a day),
sell after H bars. Each with model, production P(min) and coins (day 21 draws, 15m 11 draws).

| ID | TF | H (bars) | ≈ | Status |
|---|---|---|---|---|
| SC2-d5 | day | 5 | 1 week | DONE — all lose (costs); A01 −₹0.74 L, prod +₹5.70 L |
| SC2-d10 | day | 10 | 2 weeks | DONE — A01 ₹4.17 L (15/21), prod ₹9.29 L |
| SC2-d20 | day | 20 | 1 month (= SC1-3b) | DONE — A01 ₹10.40 L (19/21), Calmar 0.27 (20/21); prod ₹11.60 L / 0.30 — A01's best H |
| SC2-d40 | day | 40 | 2 months | DONE — A01 ₹7.15 L (4/21) fades; prod ₹12.31 L / 0.32 |
| SC2-d60 | day | 60 | 3 months | DONE — A01 ₹4.31 L (1/21), DD 70 %; **prod ₹11.54 L, Calmar 0.39, DD 31 %** |
| SC2-m25 | 15m | 25 | 1 session | DONE — everyone loses heavily (cost churn, 18k trades) |
| SC2-m125 | 15m | 125 | 1 week (= S0 15m) | DONE — A05 −₹4.77 L (0/11), prod −₹2.15 L |
| SC2-m500 | 15m | 500 | 1 month | DONE — **A05 ₹6.27 L, Calmar 0.36 (11/11 coins), DD 31 % vs coin 52 %**; prod ₹3.95 L / 0.11 |

SC2 results and reading: `reviews/model_lab/SC2_hold_20261018.md`.

## SC3 — exits on the two best SC2 frameworks (owner: "Do all three", 2026-10-18)

Frameworks: **P60** = production P(min) score, day, best 2 per day, max hold 60 bars; **M500** = A05 score, 15m,
top-1 % causal threshold, max hold 500 bars. ₹6L, 15 × ₹40k. Each exit set run with the framework's score and 11
coin draws (stored + seeds 101–110); P60 also with A01's score, M500 also with production's (cross-reference).
Fractions: stop/target vs entry price; trail = drop from the highest close since entry, active once that close is
≥ entry × (1 + activate).

| ID | Exit set | Status |
|---|---|---|
| SC3-x0 | none (time only) = SC2 baseline | DONE — P60 ₹11.54 L / Calmar 0.39; M500 ₹6.27 L / 0.36 |
| SC3-x1 | stop −20 % (production's black-swan stop) | DONE — P60 ₹12.05 L / 0.35; M500 ₹5.15 L / 0.17 |
| SC3-x2 | stop −10 % | DONE — kills both: P60 ₹4.14 L / 0.08; M500 ₹4.05 L / 0.13 |
| SC3-x3 | trail 10 % after +10 % | DONE — P60 ₹12.13 L / 0.42; **M500 ₹7.56 L / 0.37 (best 15m)** |
| SC3-x4 | trail 15 % after +10 % | DONE — P60 ₹12.94 L / 0.44; M500 ₹3.58 L / 0.13 |
| SC3-x5 | target +20 % | DONE — **P60 ₹14.57 L / Calmar 0.50, DD 31 %, 11/11 coins (best overall)**; M500 ₹3.94 L / 0.16 |
| SC3-x6 | stop −20 % + trail 10 % after +10 % | DONE — P60 ₹13.90 L / 0.36; M500 ₹5.60 L / 0.26 |

## SC4 — combined ranking, per-pick hold (owner, 2026-10-18; needs simulator S0c)

Day, ₹6L, 15 × ₹40k, best 2 per day from one pooled ranking of A01 and production P(min); each score converted to its
causal percentile (vs its own previous 60 sessions); a pick holds 20 bars if it came from A01, 60 if from production.
Controls: same with coin percentiles; and the two sleeves split (7 slots A01/20d + 8 slots production/60d, summed).

| ID | Config | Status |
|---|---|---|
| SC4-a | pooled A01 (hold 20) + production (hold 60), best 2/day | DONE — ₹11.26 L / Calmar 0.34 (9/10 coins); production picks ₹8.70 L, A01 picks ₹2.56 L — no better than production alone (₹11.54 L / 0.39) |
| SC4-b | split sleeves: 7 × ₹40k A01 best-1/day hold 20 + 8 × ₹40k production best-1/day hold 60 | DONE — worse: ₹7.31 L / 0.18 (2/10 coins) |

SC3/SC4 results and reading: `reviews/model_lab/SC3_SC4_exits_combined_20261018.md`.

## SC5 — A11 scores in the strategy frameworks (main session, 2026-10-19; informational)

A11 (`t5_edgez_H20`, reward-minus-pain ÷ usual move) FAILED its pre-registered magnitude rule (vs vol), but its
top-1 % picks show +4.28 % 20-day net vs production +2.73 % (10/16 yrs), and they are calm quality names (daily vol
1.3 % vs 2.5 %, prior 3-month −6.5 %, 18 % under ₹50; HDFCBANK, COLPAL, NESTLEIND…) — the profile survivorship
flatters LEAST. Checked in the frameworks already used, against 11 coin draws; a FAILED arm stays failed, this is
informational only.

| ID | Config | Status |
|---|---|---|
| SC5-a | A11 score, day, best 2/day, hold 20 | DONE — ₹6.36 L / Calmar 0.18 (2/11 coins ₹, 9/11 Calmar); capital use 59 % |
| SC5-b | A11 score, day, best 2/day, hold 60 | DONE — ₹12.91 L / 0.32 (9/11, 9/11); production same ₹11.54 L / 0.39 |
| SC5-c | A11 score, day, best 2/day, hold 60, target +20 % | DONE — ₹10.84 L / 0.28 (9/11, 6/11); production same ₹14.57 L / 0.50 |

## SC6 — lab strategies vs the full production system on the same window (owner, 2026-10-19)

Window = the campaign FULL window 2025-01-01 → 2026-10-16, ₹6L, 15 × ₹40k (production: ₹6L, ₹40k per stock).
Reference: production backtest FULL (TD-018 post-ISS-14 baseline) ₹439.2k, max DD 5.8 %, Calmar 6.18, weighted
win 63.9 % — the full LR-Extrema system (watchlist, per-stock params/TFs, 15m exits).
Lab side on day bars, entries only from 2025-01-01, metrics on the window only; scores for the watchlist names come
from a re-run of the A01 / A11 recipes on PIT top-200 ∪ the 21 watchlist names (only 5 of 21 are in the top-200),
production P(min) refs replayed for the missing watchlist names. Each with 11 coin draws.

| ID | Universe | Strategy | Status |
|---|---|---|---|
| SC6-L1-wl / -all | watchlist only / whole universe | A01 score, best 2/day, hold 20 | DONE — wl ₹2.35 L / DD 8.9 % / Calmar 2.46 (coins ₹3.41 L median, beats 0/11 ₹); all ₹0.96 L / 14.9 % / 0.60 (beats 10/11) |
| SC6-L2-wl / -all | watchlist only / whole universe | production-score ranker, best 2/day, hold 60, target +20 % | DONE — wl ₹3.28 L / 12.4 % / 2.46 (coins ₹3.44 L, 4/11); all ₹0.71 L / 15.6 % / 0.43 (10/11) |
| SC6-L3-wl / -all | watchlist only / whole universe | A11 score, best 2/day, hold 60 | DONE — wl ₹4.00 L / 9.0 % / 4.15 (coins ₹4.47 L, 2/11 ₹, 11/11 Calmar); all −₹0.27 L (0/11). **None beats production ₹4.39 L / 5.8 % / 6.18; random picks on the watchlist make ₹2.8–4.8 L = hindsight selection.** `SC6_vs_production_20261019.md` |

## PB-LONG — the current production setup backtested from 2015 (owner, 2026-10-19)

The full production system (`config/config.yaml` as on this branch: watchlist, per-stock params/TFs, all exits,
scale-in, loss block) through the campaign backtest engine (cache-only), window 2015-07-01 → 2026-10-16 (Kite 15m
history starts 2015-02; 2011 is impossible on 15m). **Runs on a scratch COPY of `data/market.db`** with pre-2017-12
15m candles filled from the lab store; the real cache is read once to copy and never written. Caveat up front: the
watchlist and per-stock settings were chosen in 2025–26, so earlier years are hindsight-selected names.

| ID | Window | Status |
|---|---|---|
| PB-LONG | 2015-07-01 → 2026-10-16, per-year breakdown | DONE — ₹27.9 L total (P&L reinvested); worst drop −48 % of peak equity (Jan 2018 → Mar 2020, recovered Jun 2021); 2018/19/20 −9.3/−6.7/−1.6 %, 2021–26 every year +12…+38 %; liquid names lost ₹2.05 L over 2015–20, early profit came from untradeable thin names (TIPSMUSIC/THANGAMAYL); real cache md5 unchanged. `PB_LONG_prod_2015_20261019.md` |

## SN — the strategy frameworks on the survivorship-free universe (TD-022, main session 2026-10-19)

Same simulator, capital and slots as SC1–SC5 (₹6L, 15 × ₹40k, best 2/day, next-open fills, `trader.costs`), but on
`dayn` (NSE bhavcopy, delisted names included) with the ML-A01n / ML-A11n runs. Whole test span (2011→2026-10-16),
per calendar year, ex-2020; 11 coin draws each. Read-out: the ₹ / Calmar drop vs the same config on `day` (today's
survivors) = the survivorship inflation of SC1–SC5, and whether the model still beats coins once crashed names are in.

| ID | Config | Same config on `day` (survivors) | Status |
|---|---|---|---|
| SN-1 | A01n score, hold 20 | SC1 best 2/day: ₹10.4 L | DONE — ₹3.10 L / DD 55 % / Calmar 0.06; coins ₹4.25 L median, beats 4/11 ₹, 5/11 Calmar → no edge once crashed names are in |
| SN-2 | production-score ranker (prod_pmin replay on dayn), hold 60, target +20 % | SC3-x5: ₹14.57 L / Calmar 0.50 | DONE — ₹7.07 L / 42 % / 0.18; coins ₹7.74 L, beats 3/11 ₹, 7/11 Calmar → no edge |
| SN-4 | A07n score (potential: max rise in 20 days), hold 20 — added 2026-10-19 after ML-A07n, before running | SC-none (A07 never simulated on day) | DONE — ₹1.61 L, **worst drop 89 %**, Calmar 0.02; ex-2020 −₹1.33 L; beats 0/11 coins → high per-pick mean is skew from a few crashed-name rebounds, untradeable as a 2/day ranker |
| SN-3 | A11n score, hold 60 | SC5-b: ₹12.91 L / 0.32 | DONE — **₹15.96 L / 42 % / 0.40; coins ₹8.36 L, beats 11/11 ₹ and Calmar**; ex-2020 ₹11.07 L; ≥ ₹20 entries alone ₹13.76 L > every coin. `SN_survivorship_free_20261019.md` |

## WF-1 — walk-forward choice of hold/exit settings (main session 2026-10-19; informational, post-hoc on SC2/SC3 sims)

| ID | Score | Result |
|---|---|---|
| WF-1 | production ranker / A01, 11 settings each, yearly pick from prior years (by ₹ and by Calmar) | DONE — prod ranker: by Calmar ₹13.34 L vs hindsight-best ₹14.54 L (picks target +20 % every year from 2014) → robust; by ₹ ₹9.90 L. A01: ₹7.06 / ₹5.89 L < median setting ₹8.52 L → exit choice is noise, use a fixed hold 20. `WF1_exit_selection_20261019.md` |
