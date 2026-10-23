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

## Addendum 2026-10-23 — day 4 of the slide

**Market:** fourth straight down day. Nifty 22,600 (−0.39 %), Midcap 100 −2.21 %, Smallcap 100 −2.94 %, every NSE sector red.
Nifty lost 2.4 % on the week. Brent ≈ $114 after renewed Houthi attacks on Saudi Arabia. The Jio Platforms IPO
(13.8× subscribed, $3.2 bn) reportedly drew liquidity away. Bot candles: Smallcap 250 at 16,398, −10.9 % since 23 Sep.
Sources: HDFC Sky and Kotak Neo closing reports (23 Oct), Business Standard close report (VIX +6 %).

**Book:**

| | |
|---|---|
| Realised today | **−₹14,530**: ADFFOODS −7,191 (STALE_REARM), ENGINERSIN −5,205 (STALE), CGPOWER −2,134 (`STRATEGY` = hold_bars timeout) |
| Of which already unrealised at 22 Oct close | −₹10,883, so these exits only added −₹3.6k today |
| Open-book MTM today | −₹9,618 (8 positions, ₹3.14L deployed). CUPID −3.9k, ACMESOLAR −2.9k, ATHER −1.8k; CHENNPETRO +1.1k |
| **Account move today** | **≈ −₹13.3k** |
| `cumulative_pnl` (realised since 17 Oct) | −₹20,401 |
| Still unrealised | ≈ −₹15.4k: ACMESOLAR −5.1k, CUMMINSIND −3.4k, MAYURUNIQ −2.8k, CUPID −2.0k, ATHER −1.5k |
| October realised | −₹4.6k gross (it was +₹9.9k on 22 Oct) |

- One new entry: KPL at 09:30, +₹0.5k by close.
- The loss block refused 17 rebuys. QUESS signalled at 306 → 298 and TIPSMUSIC at 716 → 704 while blocked, so both kept
  falling after the block. ADFFOODS, ENGINERSIN and CGPOWER are now blocked for 2 sessions.
- Nothing hit the 20 % hard stop.

## Addendum 2026-10-23 (evening) — vs backtest drawdowns in past corrections

**Method.** Both curves are daily mark-to-market: realised P&L plus open lots marked at the daily close, with drawdown
taken as % of account value at the peak (₹6L + profits to date).
- **Backtest:** current config, 2020-01-01 → 2026-10-16 (local candles end there), 3,226 trades, ₹60k add-on pool funded.
- **Live:** FIFO of live fills since May.
- **Normalisation:** the backtest compounds (₹15–19L deployed by 2025–26 vs ₹3–5L live), so rupee drawdowns are not
  comparable; only % of account is.
- **Corrections:** Smallcap 250 declines of ≥8 % on a zigzag, from Kite daily index data.
- **Scripts:** `reviews/market_drawdown_20261022/`.

**Live now: −6.3 % of account** (−₹41.4k, MTM peak +₹57.8k on 14 Oct → +₹16.3k on 23 Oct, 7 sessions). Smallcap 250 is −11.5 %
from its 8 Sep high.

| Small-cap correction | SC250 | Backtest account DD | Worst 7-session | Recovered (after trough) |
|---|---|---|---|---|
| COVID, Jan–Mar 2020 | −43.8 % | −36.2 % | −25.7 % | 323 d |
| Aug 2021 | −9.3 % | −5.3 % | −3.2 % | 10 d |
| Nov 2021 | −8.6 % | −4.3 % | −2.9 % | 11 d |
| Jan–Feb 2022 | −19.3 % | −8.1 % | −5.7 % | 39 d |
| Apr–Jun 2022 | −23.2 % | −9.6 % | −7.5 % | 57 d |
| Dec 2022–Mar 2023 | −13.6 % | −6.4 % | −3.9 % | 69 d |
| Feb–Mar 2024 | −12.5 % | −5.5 % | −5.5 % | 8 d |
| Oct–Nov 2024 | −10.5 % | −5.4 % | −3.1 % | 20 d |
| Dec 2024–Mar 2025 | −25.7 % | −12.4 % | −8.4 % | 77 d |
| Jul 2025–Mar 2026 | −21.1 % | −6.4 % | −4.4 % | 16 d |
| **Live, Sep–Oct 2026** | **−11.5 % so far** | **−6.3 % so far** | **−6.3 %** | — |

Reading:
- **Depth is in line.** The −10 to −14 % small-cap corrections cost the backtest 5.4–6.4 %, and live is at −6.3 %.
  The 19–26 % corrections cost 8–12 %.
- **Speed is in the tail.** Only 1.5 % of all backtest 7-session windows lost ≥6.3 %. The faster ones were COVID, Feb 2025
  (−8.4 %), May 2022 (−7.5 %) and Sep 2020 (−7.0 %).
- **If it extends.** A 2022/2025-scale slide (−20 to −26 %) implies a backtest-typical 8–12 % account DD, about ₹11k–₹40k
  more from here. Outside COVID, recovery took 8–77 days after the trough.
- **Live is likely a little milder.** Its add-on pool is unfunded (TD-022), and the backtest's funded pool amplifies bad
  quarters.
