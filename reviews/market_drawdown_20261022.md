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

## Addendum 2026-10-31 — the week of 26–30 Oct (partial rebound)

**Market:** the Smallcap 250 bottomed on 23 Oct (16,385, −11.5 % from the 8 Sep high), rose four sessions to 17,101 on
29 Oct (+4.4 %), then fell 2.0 % on 30 Oct to 16,765 (−9.5 % from the high, +2.3 % off the low). Nifty 50 held up
(22,600 → 23,053). Source: Kite daily index candles (`fetch_idx.py`).

**Account (mark-to-market, gross, `live_eq.py`):**

| Close | Realised since May | Unrealised | Equity vs May | Positions / deployed |
|---|---|---|---|---|
| 14 Oct (peak) | ₹51.9k | +₹5.8k | ₹57.8k | 12 / ₹3.45L |
| 23 Oct (low) | ₹32.5k | −₹16.1k | ₹16.3k | 11 / ₹3.29L |
| 27 Oct | ₹31.9k | −₹1.8k | ₹30.1k | 10 / ₹2.87L |
| 30 Oct | ₹26.3k | −₹4.5k | ₹21.8k | 13 / ₹3.99L |

Drawdown from the peak is now −₹36.0k (≈ −5.5 % of account value at the peak), against −₹41.4k (−6.3 %) at the 23 Oct low.
The account recovered about 13 % of its drawdown, and the Smallcap 250 about 18 % of its fall. `cumulative_pnl` (net,
realised since 17 Oct) is −₹26.6k (−₹20.4k on 23 Oct).

**Realised this week: −₹6.2k gross.**

| Exit | Reason | P&L | Note |
|---|---|---|---|
| STYLAMIND (from 16 Sep) | STALE_REARM | −₹5,395 | the week's whole loss; on the loss block for 2 sessions |
| ACMESOLAR (from 5 Oct) | STALE_REARM | −₹2,109 | re-bought 30 Oct at 404 |
| CUMMINSIND (from 14 Oct) | STALE | −₹1,962 | |
| ATHERENERG (from 21 Oct) | STALE_REARM | −₹991 | see below |
| CUPID (from 22 Oct) | STALE | −₹549 | |
| TIPSMUSIC (27 Oct → 28 Oct) | PATTERN_TOP_PARTIAL + TRAILING_EOD_CLOSE | +₹2,239 | first entry after its loss block expired |
| KPL (23 Oct → 26 Oct) | PATTERN_TOP_PARTIAL + TRAILING | +₹1,297 | |
| THANGAMAYL (26 Oct → 27 Oct) | PATTERN_TOP_PARTIAL + TRAILING_EOD_CLOSE | +₹1,256 | exposed ISS-16 |

The stale exits were losses already showing on 23 Oct; this week's wins all came from new entries made during the
rebound (THANGAMAYL, TIPSMUSIC, KPL). New entries on 30 Oct (QUESS, CGPOWER, ACMESOLAR, KPL) took the book back
to 13 positions on the day the index fell 2 %.

**ATHERENERG (hindsight, an upper bound, not a lost profit):** the stale re-arm sold 27 shares at 1,399.5 at 12:30 on
26 Oct. The stock closed that day at 1,575 (low 1,346, high 1,613) and closed at 1,756 on 30 Oct, about ₹9.6k above
the exit for the lot. The −₹991 exit armed the loss block, which refused 8 re-entry signals at 1,645–1,674 on 27–28 Oct.
An add-on at 1,357.9 at 09:15 on 26 Oct was refused for the empty pool. One case; stale exits are validated over
4/4 half-year windows (ATHERENERG's 28 Aug forensic is the opposite case: the stale exit dodged −7 %).

**Add-on pool still unfunded (TD-013, TD-022):** no pay-in all week (`intraday_payin=0` every morning); the pool logged
`funded=0 of cap=60000` at every boot (sleeve ₹5.79–5.81L). 15 add-on signals were refused `addon_budget_exhausted`
(TIPSMUSIC 7, RADICO 2, STYLAMIND 2, THANGAMAYL 2, ATHERENERG 1, CHENNPETRO 1). Other refusals: 10 `loss_reentry_block`
(ATHERENERG 8, TIPSMUSIC 2 on 26 Oct, before its block expired), 7 `addon_spacing`, 1 `stock_paused` (ADFFOODS).

**Field checks from the 17 Oct fixes:**
- ISS-01 **passes**: the "Kite margins |" line tracks every same-day trade. On 27 Oct, `net` rose by the ACMESOLAR sale
  proceeds (285,003 → 323,488), then fell by the TIPSMUSIC buy (→ 285,374). On 30 Oct it fell by the QUESS buy
  (287,355 → 248,848), the CGPOWER buy (→ 210,863) and the ACMESOLAR buy (→ 172,469).
- TD-001: not exercised yet, since cash was ₹1.7–3.2L all week and no entry was short.

**New issue — ISS-16:** on 27 Oct a THANGAMAYL scale-out decided at the 15:29:15 pre-close flush armed the remainder
trail after the 15:25 trailing force-close time, so the next tick emitted a full EOD close for 8 shares while the 4-share
partial sell was still pending. Kite refused it twice ("Insufficient stock holding … pending sell orders"). The 4-share
remainder sold at 15:29:20, after the partial filled. That was 40 s before the 15:30 cutoff. A slower fill would have left
it overnight.
