# Live drawdown 2026-10-19 → 10-22: what happened in the market

Read-only look at the live DB (EC2, pulled 2026-10-22 22:10 IST) and the day's market news. No trading change made.

## The book

| | |
|---|---|
| Open positions | 10, **all red**, ₹3.99L deployed |
| Unrealised | ≈ −₹21.6k (ADFFOODS −5.7k, ACMESOLAR −4.0k, ENGINERSIN −4.0k, CUMMINSIND −2.4k, …) |
| Today, open book MTM | −₹5.3k (−1.3 % of deployed) |
| Today, realised | TIPSMUSIC −₹1.9k (STALE), RADICO −₹1.3k (STALE) |
| 21 Oct, realised | QUESS −₹2.0k (STALE_REARM), THANGAMAYL −₹1.9k (STALE) |
| 3 sessions since the 19 Oct close | ≈ −₹23k all-in |
| `cumulative_pnl` | −₹5.9k |

Exits fired by design: every loss was a stale exit, and nothing hit the 20 % hard stop. Today the loss re-entry block refused
12 rebuys (TIPSMUSIC ×7, THANGAMAYL, RADICO, QUESS). The add-on pool is 0 (equity is below base, so 35
`addon_budget_exhausted`), which means no doubling down into the slide. See TD-022.

## The market: this was a small/mid-cap sell-off, not a large-cap one

Index closes from the bot's own candles:

| Index | 1 Sep | 23 Sep | 22 Oct | 23 Sep → 22 Oct |
|---|---|---|---|---|
| Nifty 50 | 24,056 | 23,447 | 22,688 | −3.2 % |
| Nifty Midcap 100 | 63,335 | 62,396 | 57,062 | −8.5 % |
| Nifty Smallcap 250 | 18,363 | 18,411 | 16,842 | −8.5 % |

The equal-weight watchlist (26 names) fell 1.1 %, 1.6 % and 1.0 % on 19, 21 and 22 Oct. Most holdings are 10–20 % off
their 1-month high: ENGINERSIN −20 %, M&MFIN −18 %, ADFFOODS −16 %, ACMESOLAR −15 %, CUPID −13 %, QUESS −13 %,
THANGAMAYL −13 %. Today's open-book −1.3 % is almost exactly the Smallcap 250's −1.2 %, so the loss is market beta
and not a model malfunction.

Drivers reported for 21–22 Oct:
- **Oil / Middle East.** Houthi strikes in Saudi Arabia and attacks on vessels near the Strait of Hormuz pushed Brent
  to about $112, a 5-month high. India imports most of its crude, so this raises worries about inflation, margins and rates.
- **Small/mid caps hit hardest.** Expensive valuations and thin liquidity meant profit-taking fell on them first.
  21 Oct breadth: 2,988 decliners vs 608 advancers, and 362 52-week lows vs 44 highs. 22 Oct: 15 of 16 sectors red.
- **19 Oct.** Large private banks dragged after their Q2 results.
- **India VIX 15.8,** up about 43 % in a month.

Sources: 5paisa "Midcap, smallcap stocks fall over 1% for second day" (22 Oct); Business Standard "Oil price surge keeps
Nifty in red, Sensex sheds 460 points" (22 Oct); HDFC Sky "Brent tops $110".

## Why the strategy is bleeding

LRExtrema buys capitulation dips and expects mean reversion. Through October the small-cap tape kept falling without
bouncing. Entries from 5–19 Oct (ACMESOLAR, ADFFOODS, CHENNPETRO, CGPOWER, CUMMINSIND, ENGINERSIN, MAYURUNIQ) were dips
inside a falling market, and the stale exits are now harvesting them. This is the same shape as the 2025-H1 correction,
the regime that the stale ×2 runway and the loss block were validated against.
Prior-day VIX vs its trailing year is the one market signal that ranks entries (AUC 0.638). Gating or sizing on it
failed the plateau check (TD-018, `exp/regime`), so no rule change follows from this episode.

## Watch

- The stale tier-1 checks will exit more of the book if there's no bounce: ADFFOODS (−14 %), ENGINERSIN, ACMESOLAR.
- Oil headlines and the VIX. A de-escalation bounce is the scenario where these dip entries pay.
- Loss-block countdowns (state): RADICO 2, TIPSMUSIC 2, QUESS 1, THANGAMAYL 1 sessions.

## Addendum 2026-10-22 — realised P&L (FIFO match of live fills, gross; charges via `trader.costs`)

| Window | Realised (gross) | Note |
|---|---|---|
| 21 Oct | −₹3,939 | QUESS −2,041, THANGAMAYL −1,898 |
| 22 Oct | −₹3,231 | TIPSMUSIC −1,943, RADICO −1,288 |
| Since 17 Oct (= `cumulative_pnl` −₹5,872) | −₹5,872 | 19 Oct +₹1,298 offsets; the state key was 0.0 at the ISS-04 fix, so it only counts from then |
| October to date | +₹9,898 | ≈ +₹8.0k after ₹1.9k charges |
| Lifetime (since 28 Apr) | +₹47,043 | excludes 1,222 sold shares with no matching buy (early test orders with null prices) |

Charges add about ₹100 per round trip. The larger exposure is the −₹21.6k unrealised on the 10 open positions.
