# Is the portfolio's own drawdown a good entry signal? — 2026-09-08

**Question (user):** the live bot is in an active giveback; are drawdowns typically good
entry points — is there a correlation between the portfolio's drawdown state and the
outcome of entries taken in it?

**Method:** `scripts/dd_entry_study.py <trades.csv> <capital> <label>`. Rounds =
instrument + entry_date (lots summed). Portfolio net-P&L equity by exit time → running
high-water mark → giveback (₹, % of capital, days under water) as of the last exit
strictly before each round's entry. Rounds bucketed by giveback-at-entry; outcome =
round net P&L and % on notional. Spearman, Mann-Whitney (>2% giveback vs at-high) and a
4000-draw permutation null on the bucket difference. Plus forward portfolio P&L over the
next 10/20/40 trading days from every day in each giveback state.

## Live state (EC2 DB pulled 2026-09-08 21:38 IST, post-close)

- Realised net since April: ₹19.8k (gross ₹25.3k, 125 matched slices). Peak ₹29.2k on
  2026-08-31; now ₹9.4k below it (1.56% of ₹6L config / 2.0% of the ₹468.8k effective
  capital), 8 days under water. This is the deepest episode so far but not by much —
  ₹8.5k (Jul-31→Aug-03, recovered in 5 d), ₹6.0k ×2, ₹4.4k all recovered within 5–11 d.
  Backtest max giveback on the same config is 7.5% (₹45k), so 1.6% is inside routine noise.
- September's −₹9.4k is 7 exits, all STALE / STALE_REARM (QUESS −3.8k, ADFFOODS −1.6k,
  TVSMOTOR −2.0k, REDTAPE −1.5k ×2 — REDTAPE was removed 09-04, ATHERENERG −0.4k).
- 9 open positions, ₹356.8k deployed (59% of ₹6L). Open MTM at last close ex-SANDUMA
  ≈ +₹1.6k (GESHIP +6.4%, CHENNPETRO +4.9%, CUPID +3.8%; CUMMINSIND −6.3%, STYLAMIND −3.4%).
- Effective capital at today's startup ₹468.8k (cash ₹112k + deployed ₹357k) — 2 free slots.
- **NSE:SANDUMA (201 @ ₹198.63, ₹39.9k, 2026-09-04 09:43)** has an order row but no signal,
  no candles and is not on the watchlist: a manual Kite buy the bot ingested via the order
  stream. It occupies a slot with no price feed and no exit logic. `/purge-stock NSE:SANDUMA`
  if it was manual.
- No broker rejects in the last 10 days; feed and token healthy today.

## Backtest stratification — ₹6L post-REDTAPE baseline (589 rounds, ₹482k, 2025-01→2026-09)

| giveback at entry | n | avg ₹ | avg % | win% | avg days under water |
|---|---|---|---|---|---|
| at new high | 174 | 957 | +1.58 | 58.6 | 0 |
| 0–1% | 171 | 391 | **+0.57** | 52.0 | 7 |
| 1–2% | 99 | 1,067 | +1.95 | 64.6 | 17 |
| 2–4% | 107 | 994 | +2.25 | 64.5 | 32 |
| 4–8% | 38 | 963 | +2.62 | 68.4 | 53 |

By days under water: 0 d +1.58% · 1–7 d **+0.49%** (win 51.6) · 8–21 d +2.22% · 22–60 d
+1.68% · >60 d +3.35% (win 72.7, n=33).

Spearman(giveback%, round%) = +0.066 (p=0.11). >2% giveback vs at-high: +2.35% vs +1.58%,
Mann-Whitney p=0.19, permutation p=0.27. **Directionally yes, statistically weak.**

Robustness (same script):

| run | n | ρ | >2% vs at-high | p (perm) | worst bucket |
|---|---|---|---|---|---|
| 6L, 2025-01→10 only | 258 | +0.14 (p=.03) | +1.99 vs +0.74 | 0.20 | 0–1% / 1–7 d (−0.9%, win 37.5) |
| 6L, 2025-11→2026-09 | 331 | +0.04 | +3.04 vs +2.05 | 0.35 | 0–1% / 1–7 d |
| ₹4L old baseline (maxDD 13.4%) | 325 | **+0.15 (p=.008)** | **+3.24 vs +0.90, p=.005** | **0.019** | 0–1% / 1–7 d |
| ₹6L incl REDTAPE | 650 | +0.04 | +1.64 vs +1.30 | 0.59 | 22–60 d |
| LIVE Apr→Sep 2026 | 93 | −0.08 | (no >2% sample) | — | 0–1% / 1–7 d (+0.13%, win 50) |

The shape is the same in every run: **the first week of a giveback is the worst time to
be entering** (losses cluster — a correction hits several names' stale exits together),
and entries taken 2+ weeks / >2% into a giveback are the best bucket (higher win rate,
larger % moves — the dip-buyer buying capitulation). The effect is only significant in the
deepest-drawdown run (₹4L, more deep samples); on the current config it is a lean, not a law.

## Portfolio-level forward P&L — the hypothesis does NOT hold for "add money now"

Forward net P&L from days in each state (₹6L baseline):

| state | days | +10 d | +20 d | +40 d |
|---|---|---|---|---|
| at new high | 163 | 15.2k | 29.1k | 59.0k |
| 0–1% | 119 | 9.3k | 20.7k | 47.5k |
| 1–2% | 55 | 3.8k | 18.2k | 36.3k |
| 2–4% | 69 | 13.1k | 20.1k | 40.9k |
| 4–8% | 30 | 8.2k | 17.2k | 41.1k |

Better per-trade quality in deep givebacks does not translate into faster portfolio
recovery: fewer entries fire and capital is parked in the losers, so the equity curve
compounds *slower* from a giveback than from a high. (Also note the in-sample bias: a
profitable backtest recovers every giveback by construction, so even the forward numbers
from drawdown days are an upper bound.)

## Conclusions

1. **Weak positive correlation at the trade level** (ρ ≈ +0.04…+0.15). Entries taken >2%
   or >2 weeks into a giveback earn ~+0.8–2.3 pp more per round with a 5–10 pt higher win
   rate; only significant in the deep-drawdown run.
2. **The first week / first 1% of a giveback is consistently the worst bucket** (5/5
   runs incl. live) — losses cluster, then mean-revert. That is where the live bot is
   right now (1.6%, 8 days).
3. **No portfolio-timing edge:** forward P&L from giveback days is lower than from
   new-high days at every horizon. "Add capital in drawdown" is not supported; "keep
   trading through it" is — the system already takes every entry, which is the whole edge.
4. **Not actionable as a gate in either direction.** Reducing size in week 1 of a giveback
   is another rule that amputates trade sequences (cooldown / loss-block / discount /
   loss-budget all falsified the same way) and the shallow bucket is still net positive on
   the current config. Diagnostic only, like the market-indicator overlay
   (`reviews/giveback_market_indicators_20260901.md`).

## Addendum 2026-09-11 — how the episode actually played out (live DB, post-close Fri)

Projection made Tue night (2026-09-08) vs outcome:

| position | projected | actual |
|---|---|---|
| CUMMINSIND stale re-arm Wed 15:15 | near-certain, ≈ −₹2.4k | **fired (rolling_best −3.72%, gain −3.78%) but the SELL was REJECTED by Zerodha** — "Your order could not be converted to a After Market Order (AMO)" at 15:15:02. Position state restored; next check is bar 40 (hold timeout, 2026-09-23). Still open at −5.7% (−₹2.2k MTM), ₹0.7k worse than the rejected exit |
| STYLAMIND stale re-arm Thu 15:15 | −₹1.3k if unchanged | fired at 3303.7, **−₹2.0k** (fell further to −5.0%) |
| QUESS stale re-arm Wed ~11:15 | coin flip, floor ₹334.7 | never came near the floor — rallied, 50% pattern-top scale-out at 354.1 then EOD trail at 357.7, **+₹1.6k** |

Not projected: CHENNPETRO hit its 10% trailing floor at 09:43 Wed (+₹3.8k); ATHERENERG
and KPL both pattern-topped Fri (+₹2.1k, +₹1.6k). New entries THANGAMAYL (Wed), KPL (Thu),
CGPOWER (Fri).

**Giveback ₹9.4k → ₹2.2k in three sessions (0.37% of ₹6L; 11 days under water).**
Realised net ₹27.0k vs peak ₹29.2k; open MTM ex-SANDUMA +₹3.6k, so incl. open the book is
₹30.6k — above the old peak. September month-to-date −₹9.4k → −₹2.2k. Effective capital at
Fri startup ₹472k (cash ₹158k + deployed ₹314k).

Reading against the study: the recovery came from the winners that were already on the
book exiting (4 of the 6 September exits since Tue were profits), not from new entries
made "in the dip" — consistent with the finding that portfolio forward P&L from
drawdown days is no better than from highs. The two losers that were on the chopping
block lost more by the time the rule fired (STYLAMIND) or could not be sold at all
(CUMMINSIND).

**Open item — AMO rejection of a 15:15 market SELL.** Only 2 occurrences in the journal since June — ATHERENERG 2026-08-31 15:15:00 and
CUMMINSIND 2026-09-09 15:15:02 — both at the 15:15:00 second boundary, while other 15:15
orders (KPL 2026-09-11 15:15:01) fill fine. Intermittent, time-of-day specific. The
CUMMINSIND one is a mid-session stale exit that died with no retry
(the re-arm check only re-evaluates at the next `check_bars` multiple — for day-TF names
that is 10 sessions later). Needs a root cause (Kite session state / order variety) and a
retry-next-candle path for rejected rule exits, same family as the CAS pre-close flush.
Not a config problem.
