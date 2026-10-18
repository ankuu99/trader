# SN — the models and strategy frameworks on the survivorship-free universe (TD-022)

Run 2026-10-19 (main session, autonomous; pre-registered in `LEDGER.md` ML-A01n/A11n and `STRATEGY_LEDGER.md` SN
before running) · Branch `exp/model-lab`.

## Data

- **`dayn` source:** NSE bhavcopy 2008-01 → 2026-10-16, split/bonus-adjusted from NSE corporate actions (L0c,
  signed off in `to_develop/completed/2026-10-18_TD-022_L0c-*`).
- 4,045 securities, of which **1,070 later delisted**. ETFs/fund units are excluded from the universe (ISS-17).
- **Universe:** PIT top-200 by trailing traded value, re-ranked each 1 Jan. 505 different names are members at some
  point, including UNITECH, VIDEOIND, VIJAYABANK, DHFL, GITANJALI, JETAIRWAYS, RCOM, SATYAMCOMP and HDFC.
- **Simulator:** the S0 simulator with the ISS-18 fix (a held stock whose data ends is closed at its last price after
  7 days, freeing the slot).
- **Common settings:** ₹6L, 15 × ₹40k, best 2 a day, next-open fills, `trader.costs`, 2011 → 2026-10-16.
- **Controls:** 11 coin draws per configuration.

## Models (scored on their own terms)

| Arm | Survivor `day` | Survivorship-free `dayn` |
|---|---|---|
| ML-A01 / A01n (deep swing lows) | PASS: event AP 0.295 vs prod 0.171 / coin 0.055 | **PASS: 0.293 vs 0.169 / 0.054, 32/32 folds, 16/16 years**. Detection is unaffected by survivorship |
| A01 after-pick, 1 % rate, H=20, net | 3.67 % (prod 2.73 %, coin 0.55 %) | **2.92 %** (prod 2.08 %, coin 0.50 %). About a 20 % haircut, still ahead of both |
| ML-A11 / A11n (reward net of pain) | FAIL (vs vol) | FAIL (vs vol: 0.56 folds / 0.50 years); wins vs prod, rsi, coin |

## Strategy frameworks in ₹ (2011 → 2026-10-16)

| ID | Strategy | `day` (survivors) | **`dayn` (with delisted names)** | Worst drop | Calmar | Coins: median [range] | Beats coins ₹ / Calmar |
|---|---|---|---|---|---|---|---|
| SN-1 | A01, hold 20 | ₹10.4 L (coins ₹6.9 L) | **₹3.10 L** | 55.1 % | 0.06 | ₹4.25 L [2.60–7.31] | 4/11 · 5/11 |
| SN-2 | production-score ranker, hold 60, +20 % target | ₹14.57 L (coins ₹9.9 L) | **₹7.07 L** | 42.3 % | 0.18 | ₹7.74 L [5.24–8.89] | 3/11 · 7/11 |
| SN-3 | A11, hold 60 | ₹12.91 L (coins ₹11.4 L) | **₹15.96 L** | 42.1 % | 0.40 | ₹8.36 L [5.07–11.38] | **11/11 · 11/11** |

- **Ex-2020:** SN-1 ₹2.03 L, SN-2 ₹6.46 L, SN-3 ₹11.07 L (Calmar 0.30).
- **SN-3 by year (₹ L):**

  | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | −1.56 | +3.00 | −0.69 | +2.14 | +0.53 | −0.02 | +1.92 | −0.44 | −0.22 | +4.88 | +2.92 | +0.22 | +1.53 | +2.12 | +0.07 | −0.48 |

- **Worst drops:** all three strategies' worst drops sit in 2011–13. SN-3's ran from April to December 2011 and was
  recovered by February 2012. SN-1's and SN-2's ran from late 2012/early 2013 to the second half of 2013, recovered
  by mid-2014.

**Penny-stock check.** Split by raw entry price (from the bhavcopy, on the signal day; a static split, not re-simulated):

| | Entries priced < ₹20 | Entries priced ≥ ₹20 | Coins on ≥ ₹20: median [range] |
|---|---|---|---|
| SN-1 | −₹0.36 L (99 trades) | ₹3.46 L | ₹4.41 L [2.32–6.59] |
| SN-2 | −₹0.49 L (26) | ₹7.55 L | ₹7.85 L [5.01–9.72] |
| SN-3 | +₹2.20 L (40) | **₹13.76 L** | ₹8.31 L [5.88–11.25] |

SN-3's biggest trades are bounces in distressed names: RELINFRA +279 % from March 2020, ORBITCORP, STCINDIA, DISHTV,
IDBI, RPOWER, RENUKA. The top 10 trades are 31 % of its net. Even without any sub-₹20 entry it stays above every coin
draw.

**Run-to-run sensitivity.** The first pass before the ISS-17/18 fixes gave SN-1 ₹0.93 L, SN-2 ₹5.61 L and SN-3
₹11.66 L. Freeing slots locked in dead stocks and removing ETFs moved each by ₹1.5–4.3 L, so read the ₹ to about
±₹2 L. The verdicts vs coins did not change direction.

## What this says

1. **Survivorship was hiding most of the ₹ in the survivor-only results.**
   - Random picks fall from ₹6.9–11.4 L to ₹4.3–8.4 L.
   - The deep-low strategies collapse: A01 ₹10.4 → 3.1 L; production ranker ₹14.6 → 7.1 L.
   - On the honest universe **neither beats random picks**. Their deep-dip picks include the stocks that kept
     falling: PCJEWELLER, YESBANK, FEL, EDUCOMP, DHFL, GITANJALI, MMTC. Today's-names data had removed those, or kept
     only their recovered history.
2. **A01 still finds swing lows better than anything else (detection PASS, unchanged), but that does not make money
   on its own.** A deep low in a stock that is about to be delisted looks the same as one that bounces. Detection
   needs a "will it survive" filter before it can pay. That is the exclusion list's job (TD-023 S2), or a quality/pain
   model.
3. **A11 (reward net of pain over 20 days) is the one model whose picks beat random picks on the honest universe**:
   11/11 on ₹ and Calmar, robust to removing sub-₹20 entries, positive in 11 of 16 years.
   - It failed its own magnitude test against plain volatility. As a ranker inside a strategy, though, it carries an
     edge the others don't.
   - Its absolute risk is still poor: a 42 % worst drop, Calmar 0.40, and a weak 2025–26.
4. **For TD-023:**
   - the next design work is A11-ranked entries plus a survival/quality exclusion list;
   - production's +20 % target exit (which survived WF-1 on survivors) does not rescue the production ranker here;
   - any ₹ claim must come from `dayn`.

## Caveats
- **Exits are fixed choices** made on survivor data (SC2/SC5), not re-tuned.
- **No re-run on 15m:** 15m stays survivor-only (Kite).
- **DELIST closes at the last traded price.** That is right for cash mergers and optimistic for suspensions that never
  resume (two DELIST exits in each strategy run).
- **Not comparable with the full production system:** production's 2015→2026 backtest (PB-LONG) used its hindsight
  watchlist on Kite data.

Raw: scratchpad `sn_res.json` (v1 pre-fix: `sn_res_v1_preISS17.json`); per-sim outputs `lab_data/model_lab/portfolios/SN-*`.
