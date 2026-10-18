# TD-023 S0 — first framework-check simulations, 2026-10-18

Simulator: `research/model_lab/portfolio.py` (guide `to_develop/completed/2026-10-18_TD-023_S0-*`). One sleeve, ₹6L in
15 × ₹40k slots, entries = scores above the causal top-1 % threshold (previous 60 sessions), next-bar-open fills,
`trader.costs` charges. Each config run three times on identical rows/slots/exits: the model's score, a coin, and
production P(min) replayed on the same bars. **Framework check, not tuning** — two untuned exit sets, chosen before
running. Survivor-biased universe (TD-022): the absolute ₹ numbers include the listed-only market drift and are
inflated; the comparisons between the three score sources are the readable part.

Reports: `reviews/model_lab/portfolios/S0_*.md`.

## Day bars, A01 (logistic, deep swing lows), 2011–2026

| exits | score | net ₹ | trades | avg ₹/trade | money-wtd win % | max DD | Calmar | capital in use |
|---|---|---|---|---|---|---|---|---|
| sell after 20 days | **A01** | 7.28 L | 1,934 | **377** | **55.4** | **34 %** | **0.22** | 62 % |
| | coin | 7.57 L | 2,814 | 269 | 54.2 | 57 % | 0.14 | 90 % |
| | production | 6.38 L | 2,218 | 288 | 54.4 | 42 % | 0.16 | 71 % |
| stop −10 %, trail 5 % after +5 %, max 20 days | A01 | 3.81 L | 2,730 | 139 | 52.3 | 46 % | 0.09 | 59 % |
| | coin | 7.21 L | 3,521 | 205 | 53.5 | 62 % | 0.12 | 86 % |
| | production | 7.29 L | 3,020 | 242 | 53.9 | 52 % | 0.15 | 68 % |

- With a plain 20-day hold, A01's trades are clearly better (₹377 vs ₹269 random, ₹288 production; DD 34 % vs 57 % /
  42 %), and per rupee actually deployed it earns 12.7 %/yr vs 9.0 % for random. Total ₹ only ties the coin because
  **A01 keeps 38 % of the capital idle**: its picks bunch on sell-off days (signals on 1,045 days vs 2,087 for the
  coin; up to 14 entries a day; the busiest 5 % of days carry 23 % of entries), so slots overflow on crash days and
  sit empty on calm ones.
- The stop/trail set **halves** A01 (₹7.3 L → ₹3.8 L) while barely touching the coin: A01 buys deep lows, which keep
  falling for a while (pain before the peak), and a tight stop/trail shakes them out before the rebound — the same
  failure as LR-Extrema detection arms under the production exit stack (TD-018).
- Ex-2020: A01 ₹8.75 L / Calmar 0.29 (2020 cost it ₹1.46 L).

## 15m bars, A05 (A01 recipe), sell after 125 bars (≈ 5 days), 2017–2026

| score | net ₹ | trades | avg ₹/trade | money-wtd win % | max DD |
|---|---|---|---|---|---|
| A05 | **−4.77 L** | 6,007 | −79 | 47.4 | 84 % |
| coin | +0.69 L | 6,538 | +11 | 50.4 | 72 % |
| production (global 15m params) | −2.15 L | 5,583 | −39 | 48.8 | 68 % |

Every 15m score loses at a 5-day hold; A05 loses most. Its 15m lows are real (A05 detection PASS) but shallow, and
with costs on every trade they lose money — consistent with the A05 after-pick table (+0.14 % gross-of-slot, below
round-trip charges on ₹40k).

## What this tells the framework design (docs/04)

1. **Capacity is a first-class design problem**: a good low-finder fires in bursts. Options for S1: rank across the
   burst and keep the best only (already done), fewer bigger slots vs many small, a carry-over queue (enter
   tomorrow if still above threshold), or a lower threshold on calm days (top-K mode).
2. **Exits must suit the model**: A01's picks need room (pain before the peak). Exits should be set from the model's
   own pain / hold forecasts (S3) — not the generic stop/trail and not LR-Extrema's stack.
3. **15m is not viable as "buy the low, hold 5 days"** with these scores; 15m needs a move-size model first (docs/04
   S1 note), or a different holding style.
4. Random entries earn ~8 %/yr here — the survivor-biased market drift. Any ₹ claim must be read relative to the coin
   until TD-022.
