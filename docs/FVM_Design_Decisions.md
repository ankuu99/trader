# FVM — Design Decisions Log

Companion to `FVM_Strategy_Architecture.md`. That doc is the **what/why**; this is the
**exactly how** — every concrete mechanism decided during the design sessions, with the
rationale and the rejected alternatives.

Status: **design phase, in progress.** Pieces are worked in dependency order. Each section
records the locked decision; open items are marked `OPEN`.

Decision sequence so far: Spine → Factor library (5 pillars) → Normalization/scoring (partial).

---

## Piece 1 — The Spine

The foundation. Universe, clock, and data reality constrain every downstream mechanism.

### 1a. Data — true point-in-time (PIT)
- Source preserves **originally-reported** numbers and **declaration dates** (no restatement
  leakage, no reporting-lag leakage).
- **Consequence:** the fundamental store is **append-only / vintaged**, keyed by
  `(symbol, fiscal_quarter, knowledge_date)`. Never overwrite a number; store what was known
  as of each date. This is what makes the backtest and the ML layer trustworthy.

### 1b. Universe — liquid anchor (Nifty 500/750), financials excluded (v1)
- Anchor to a defined liquid set where PIT fundamentals and liquidity are reliable.
- **Financials excluded for v1** (banks, NBFCs, insurers, AMCs) — they break OPM, EV/EBITDA,
  and the meaning of D/E, and would need a separate factor recipe. Revisit post-v1.
- **Effect:** tradeable universe ≈ **350 non-financial liquid names**. Every survivor supports
  OPM / EV-EBITDA / D-E cleanly — no neutral-fill hacks for sector-broken factors.
- Maintain an explicit **sector-exclusion list** (AMFI/GICS financials) at the universe layer.

### 1c. Clock — hybrid, which collapses to a clean rule
- **Raw fundamental factors are a step function per stock** — change only on that stock's
  report date (lagged to its true declaration date); flat between reports. That is correct PIT,
  not staleness.
- **Cross-sectional percentile ranks recompute daily** (cheap over ~350 names).
- **Technical factors recompute daily.**
- So "hybrid" = *raw inputs step on each stock's report date; ranks + technicals recompute
  daily.* No separate monthly batch; the "uneven cross-section" worry dissolves under
  percentile ranking.

### Data-history tiers (for Pillar 1 scoreability)
- **8 quarters** → can score growth-acceleration (else neutral 0.5).
- **6 quarters** → can score OPM-trend & consistency (else neutral 0.5).
- **5 quarters** → can score simple YoY level factors.
- Below 5q: effectively no Pillar-1 score; leans on Pillars 2/4. Rare in a liquid universe.

---

## Piece 2 — Factor Library

System-wide rule established here:

> **Every factor carries an "absence type" flag:**
> - `missing` (we should know it but don't, e.g. young stock's acceleration) → **neutral 0.5**
> - `N/A` (factor doesn't exist for this stock, e.g. order book for pharma) → **drop the factor
>   and renormalize the pillar's weights** over the applicable factors.
>
> Set once, centrally — like the directionality sign convention.

### Pillar 1 — Earnings Quality & Growth (35%)

**Profit Growth Acceleration (0.30) — the crown jewel.**
- **4-point OLS slope of the YoY-growth-rate series** (the change in the *rate* of growth).
- Uses **denominator flooring** to stay unit-coherent and handle loss/near-zero bases:
  ```
  g_t = (NP_t − NP_{t-4}) / max( |NP_{t-4}| , F_t )      F_t = 1% of trailing-12m revenue
  ```
  - Healthy positive base → floor inert → ordinary YoY%.
  - Tiny-loss / near-zero base → floor takes the denominator; **numerator (Δ₹) carries sign &
    magnitude** = the chosen "fall back to Δ₹" behavior, but on the same % axis (no unit splice,
    no discontinuity).
- **Winsorize each g_t to ±200% before the slope fit.**
- Needs **8 quarters**; else neutral 0.5 (young names stay eligible elsewhere, just can't win on
  acceleration). Rejected: second-difference of profit level (seasonality-poisoned);
  exclude-on-insufficient-history (kills young momentum names).

**YoY Profit Growth (0.25)** — the *level*: latest `g_t` from the same floored formula.
Winsorize ±200%. Reuses the flooring rule, so turnarounds/base-effects handled identically.

**Revenue Growth YoY (0.20)** — `(Rev_t − Rev_{t-4})/Rev_{t-4}`. Revenue ~never negative → no
flooring; plain YoY%, winsorize ±200%.

**OPM Trend (0.15)** — slope of operating-margin series (`OpProfit/Revenue`) over **6 quarters**.
Margin is already a stationary ratio → fit slope on raw series, no flooring.

**Earnings Consistency (0.10)** — `−stdev(YoY-growth over 6q)` (e.g. `1/(1+stdev)`), ranked
cross-sectionally. Counterweight to acceleration: rewards steady compounding, punishes the lumpy
`0,0,0,+300%` pattern.

### Pillar 2 — Valuation Runway (25%)

All Pillar-2 level factors are **sector-relative** normalized.

**PEG** — `P/E ÷ min(trailing_growth%, forward_growth%)` ("cheap on both clocks"; falls back to
trailing if no analyst coverage). **z-scored** (magnitude matters; the one factor carved out of
percentile default). Degenerate cases: negative earnings → explicit *bad* score (never "cheap");
growth ≤ small floor → worst-decile. Winsorize PEG to `[0,5]`.
- *Dependency:* forward growth couples Pillar 2 to Pillar 5's analyst data (sourced once, used
  twice). If analysts forecast decline, forward<0 → `min` selects it → PEG degenerate → worst
  score. Consistent.

**P/E vs own history** — today's P/E percentile within its own **3-year** daily P/E series. Low =
re-rating runway. Mask any window slice where TTM EPS crossed zero (P/E garbage there).

**EV/EBITDA** — `(MktCap + Debt − Cash)/TTM EBITDA`. Cross-checks P/E, strips leverage. **Data
nuance:** debt/cash are balance-sheet → reliable only half-yearly/annually → EV numerator is
staler than daily P/E; stamp it with its true (semiannual) knowledge-date.

*"P/E vs sector" folded into sector-relative normalization* (not a separate factor). Pillar 2 =
**3 weighted factors** → reweight at scoring stage.

### Pillar 3 — Balance Sheet Health (10%) — mostly penalty/veto

**Structurally a slow, semiannual-refresh pillar** — cash-flow statement, full balance sheet,
ROCE all report only H1/annually in India. Accepted; stamp with true semiannual knowledge-dates.

**CFO vs Profit — crown of the pillar, two-tiered:**
- **Hard veto:** `CFO < 0 AND NetProfit > 0` (manufactured earnings).
- **Graded penalty:** `CFO/NP` in (0, ~0.7) drags the score (cash-conversion ratio, percentiled).

**D/E — two-tiered:** sector-relative normalized for the *score*; absolute *sector ceiling* for
the *veto* (`D/E > ceiling AND interest_coverage < min`).

**Interest Coverage** — `EBIT/interest`; percentiled; also second condition of the D/E veto.

**Debt Trend** — slope of debt series (annual points; coarse but direction is the signal). Falling
debt = bullish.

**ROCE (primary, not ROE)** — capital-structure-neutral; **level + "rising" slope** over annual
points. ROE rejected (leverage-flattered, partly redundant with D/E).

### Pillar 4 — Institutional & Ownership (15%) — quarterly, tight lag

LODR mandates quarterly shareholding disclosure (~21-day lag). Two more vetoes live here.

**FII-trend and DII-trend — tracked separately** (they offset in India; net hides rotations; FII
flows carry more price-impact signal). Slope over 2–4 quarters each.

**Promoter Holding — two-tiered:**
- **Conservative veto:** promoter holding down beyond a meaningful threshold (e.g. >2% QoQ) AND
  price up over the window AND **not explained by a disclosed QIP/ESOP/issuance** event. Needs a
  **corporate-actions feed** to exonerate (avoids false-killing dilution-for-growth).
- **Graded penalty:** falling promoter holding generally.

**Promoter Pledging — two-tiered:** hard veto on `pledge high AND rising`; graded penalty on level
otherwise. Clean/unambiguous signal.

**Institutional-holder count** — rising MF/FII count = broadening conviction; slope over 2–4q.
Independent of holding-% (rising count + flat % = broader-not-deeper, still bullish).

### Pillar 5 — Forward Visibility (15%)

**Analyst Estimate Revision — the workhorse.** Change in consensus forward EPS over a trailing
window (sign + magnitude). Universe-wide, continuous refresh. (Same forward number feeds PEG.)

**Order Book / Inflow Trend** — contracted future revenue; **only applies to ~4 sectors** (infra,
defense, capital goods, EPC). For others it's **N/A → drop & renormalize** (not neutral-fill).

**Sector Tailwind** — **fundamental breadth** (fraction of the sector getting forward-estimate
upgrades / aggregate sector profit-growth), NOT sector price momentum — keeps the fundamental gate
orthogonal to the technical timer (rejected price-momentum and blend for double-counting).

---

## Piece 3 — Normalization & Scoring (partial)

Decided across §3 + factor work: percentile-rank default; **z-score PEG only**; sector-relative for
valuation/leverage; winsorize 1/99; flip lower-is-better centrally so 1.0 always = good;
drop-renormalize for N/A.

### Sector taxonomy & small-bucket handling
- **AMFI/NSE macro classification** as the base taxonomy (India-native, what the market trades on).
- **Coarsen to a ≥20-names-per-bucket floor:** merge the smallest AMFI sectors into adjacent macro
  groups until every bucket has ≥20 names. Gives clean within-sector ranks (accepts some
  sub-industry mixing). Rejected: shrinkage-to-universe (more complex), min-size cliff fallback.

### Winsorization ordering (locked)
1. **Factor-specific caps first** — semantic, known-degenerate (PEG→[0,5], growth→±200%).
2. **Then universe-wide 1st/99th-percentile clip** — blanket catch-all on the rest.
3. **Then normalize** — percentile (or z for PEG); sector-relative factors use universe-wide clip
   then sector-relative *rank* (clipping and ranking serve different purposes).

### Pillar & composite weights (unchanged from architecture doc)
- Composite = `100 × Σ pillar_weight × pillar_score`; pillar weights 35/25/15/15/10
  (Earnings/Valuation/Forward/Ownership/BalanceSheet).
- Per-stock dynamic reweighting where factors are dropped (N/A).

`OPEN` — intra-pillar weight renormalization after Pillar-2 fold-in (4→3 factors); confirm at
scoring implementation.

---

## Piece 4 — Vetoes

Consolidated register (each is the *extreme* end of a two-tier factor; the *moderate* zone is a
graded penalty — so vetoes are cleanly binary, penalties cover the middle, no "soft vetoes"):

| # | Veto | Source | Data |
|---|---|---|---|
| 1 | `CFO < 0 AND NetProfit > 0` | Pillar 3 | Cash-flow (semiannual) |
| 2 | `D/E > sector_ceiling AND interest_coverage < min` | Pillar 3 | Balance sheet |
| 3 | Promoter selling into strength (conservative, corp-action-exonerated) | Pillar 4 | Shareholding + corp-actions |
| 4 | `pledge_pct high AND rising` | Pillar 4 | Shareholding |
| 5 | Manufactured earnings (see 4b) | §3 | P&L |
| 6 | Compliance: GSM / ASM / T2T | NSE surveillance | Daily NSE feed |

### 4a. Veto register = Clock 1 (thesis-break exit) — LOCKED
A hard veto firing on an **open position triggers an immediate exit**. The veto register is the
single, rules-based definition of the fundamental exit clock — no separate thesis-break logic to
invent in Piece 9. Unifies entry gate and fundamental exit.
- *Caveat for Piece 9:* vetoes are the **hard** thesis breaks and fire only as fast as their data
  refreshes (CFO semiannual, etc.). Piece 9 may add **soft thesis-decay** exits (composite falling
  below a floor, PEG exhaustion) on top of the hard veto-exits.

### 4b. Manufactured-earnings veto — LOCKED (revenue must be *falling*)
`VETO if revenue YoY < −threshold (e.g. −5%) AND profit YoY > +threshold (e.g. +30%)`. The sign on
revenue is the whole game: margin expansion (profit faster than *positive* revenue growth) is the
*best* case and must never trip it. Rejected the `revenue ≤ 0` variant (false-kills efficient
operators in a soft year) and penalty-only (lets fraud tells through the gate).

### 4c. Minimum-scoreability gate — LOCKED
Trade only if a minimum count of **core factors are genuinely present** (not neutral-filled) —
specifically at least the Pillar-1 growth level + a Pillar-2 valuation factor (PEG or P/E). Blocks
a data-poor name from masquerading as median-quality on a composite built of 0.5 fills. Rejected
coverage-weighted sizing (more complex) and no-gate (thin names can slip in).

---

## Piece 5 — Technical Layer (the TIMER)

Two framing principles:
- `Technical_Score` is **continuous [0,1]** (it multiplies, so no binary).
  `Technical_Score = Trend_Score × Timing_Score` — multiplicative (same punish-imbalance logic).
- **The trend definition's negation = Clock 2 (price-break exit).** Chosen so its break is a clean
  exit, mirroring "veto register = Clock 1."

### 5a. Timeframes — Weekly (context) + Daily (trigger). LOCKED.
Weekly sets the governing trend; daily times the entry. True positional, matches days–months hold,
cleanly distinct from LRExtrema's 15-min clock. **Governing TF = weekly** (defines exits).

### 5b. Trend confirmation — MA structure / Stage-2. LOCKED.
- **Trend_Score (weekly):** price above a *rising* **40-week MA** (≈200-day governing line) with
  **10-week > 40-week** (weekly analog of "50>200"). Continuous score from MA stacking + slopes.
  (40w/10w = the positional mapping of the doc's generic 200/50; tunable.)
- **Clock 2 exit (its negation):** weekly close below the 40-week MA, or a decisive weekly
  lower-low. Daily noise can't trigger — governing TF is weekly (§5: "the governing timeframe
  defines break"). Rejected swing-HH/HL (noisier to score) and MA+ADX (more knobs, fuzzier exit).

### 5c. Entry archetypes — both, take better-timed. LOCKED.
- **Timing_Score (daily) = max(Pullback_Score, Breakout_Score) × Extension_factor.**
  - *Pullback:* in a confirmed uptrend, proximity to rising 50-day MA / prior breakout level +
    daily reversal confirmation.
  - *Breakout:* price clears a consolidation/base high with **volume expansion**.
  - *Extension guard (anti-chase):* factor decays as price runs > N×ATR above the 50-day — the
    technical analog of PEG's "don't buy the tired stock." Operationalizes "never chase the
    vertical spike." Applies to both archetypes.
- Both archetypes scored, trigger on the cleaner. Max opportunities/trade-count (strategy wants
  volume); two patterns to calibrate. Breakout keeps it distinct from LRExtrema; pullback's mild
  mean-reversion flavor is separated by timeframe + the fundamental gate.

### Entry/exit asymmetry (intentional)
Enter on **daily** precision; exit only on **weekly** structural break. Gives winners room to run,
consistent with §5's "trail and ride."

### 5d. Scoring functions (functional forms). LOCKED.

**Trend_Score (weekly) — multiplicative soft-gates:**
`Trend_Score = g_above × g_slope × g_align`, each a smoothstep on a scale-free quantity:
- `g_above` on `(price/MA40 − 1)`
- `g_slope` on the 40-week MA slope normalized to %-per-week
- `g_align` on `(MA10 − MA40)/MA40`

Any leg failing drives the score → 0 = exactly "confirmed Stage-2 requires all three." Doubles as
the hard-gate floor (Gate B) and the ranking term. Rejected weighted-average (legs compensate —
strong slope masks price below MA) and checklist-count (coarse, magnitude-blind).

**Timing_Score (daily) = max(Pullback, Breakout) × Extension_factor**, each archetype a
**two-component product** (both halves required):
- `Pullback = proximity × reversal` — proximity ramp peaks in the support zone at the rising
  50-day / prior breakout level (falls off if far above OR decisively below); reversal = bullish
  daily turn-up (stops falling-knife pullbacks).
- `Breakout = magnitude × volume` — magnitude ramp rewards a clean clear of the base high (doesn't
  keep rising once extended — that's the guard's job); volume ramp on `volume/avg_volume`, capped
  (stops low-volume fakeouts).
- `Extension_factor` — **REVISED per stress-test R2.** NOT a graded multiplier in the ranking
  product (it double-penalized strength alongside the valuation pillar — see Stress-Test R2).
  Instead: the **valuation pillar carries "don't buy expensive"** at the fundamental gate, and the
  extension guard survives only as a **hard binary entry block** for *truly parabolic* entries
  (price > `hi×ATR` above the 50-day → no entry). No graded multiplicative timidity; just a
  catastrophe block. So `Timing_Score = max(Pullback, Breakout)`, with a parabolic-extension veto
  on top.

Rejected single-dominant (admits low-vol breakouts / knife-catches) and additive (a strong half
rescues a weak half).

**Initial protective stop — wide catastrophe breaker. REVISED per stress-test R4.**
A *tight* structural stop whipsaws a weekly-horizon strategy (daily noise hits it while the weekly
thesis is intact, and event-driven entry then blocks re-entry — Stress-Test R4). So the initial
stop is **wide**: weekly-structure-based (e.g. below a recent weekly swing low) or a large ATR
multiple — placed where **daily noise will not reach it**, functioning only as a black-swan
breaker. **Position size is computed off this wider distance** (smaller positions, accepted). It
may sit near the 40-week governing line. Honors the positional horizon; sizing no longer dictates
exit behavior. (Supersedes the earlier "structure with ATR cap / tight" decision.)
`OPEN` — smoothstep knee locations; `hi×ATR` parabolic-veto threshold; wide-stop basis (weekly
swing low vs large-ATR multiple); volume-ramp cap.

---

## Piece 6 — The Handoff (gate, then time)

Pipeline (every stage explicit):
```
~350 universe
  │ Gate A — Fundamental eligibility: composite cutoff + passes vetoes + min-scoreability
Eligible pool
  │ Gate B — Technical trend: confirmed weekly Stage-2 uptrend (Trend_Score floor)   [HARD GATE]
Trend-confirmed pool                         ← rest WAIT (never bought counter-trend)
  │ Trigger — fresh daily timing event (pullback OR breakout)   [EVENT-DRIVEN]
Entry candidates
  │ Rank — Final = within-pool fundamental percentile × Technical_Score   (multiplicative)
Prioritized → sizing (Piece 10)
```

### 6a. Fundamental gate — Hybrid (top 30% AND absolute floor). LOCKED.
`eligible if percentile ≥ 70th AND composite ≥ floor`. Strong market → percentile binds; weak
market → floor binds, pool shrinks, capital correctly sits out. Both thresholds tunable (`OPEN`).

### 6b. Technical trend — HARD GATE. LOCKED.
No entry unless in a confirmed weekly uptrend, regardless of fundamentals. A great fundamental name
in a downtrend **waits**. Faithful to "validated momentum"; never buy counter-trend.

### 6c. Entry mechanism — EVENT-DRIVEN. LOCKED.
Enter only on a fresh daily pullback/breakout trigger. Real timing, better prices; a steady grinder
with no fresh setup is patiently skipped. Trade volume comes from universe breadth + both
archetypes, not from relaxing timing. (Recycle exit in Piece 9 keeps capital cycling.)

### Scale reconciliation (default)
Product terms differ in scale (composite 0–100, technical 0–1) → use **within-eligible-pool
fundamental percentile × Technical_Score**; both rank-like [0,1], product interpretable.

`OPEN` — absolute composite floor value; percentile cut (70th nominal); Trend_Score gate floor;
N×ATR extension threshold. All set at calibration.

---

## Piece 7 — Labels

A label answers: *did this historical entry become a good trade?* Two purposes, kept separate:
(1) **validate the rules pipeline** — v1 ships rules-only, the label proves/disproves it;
(2) a **target for any future ML** (Piece 8 decides ML on merits vs the rules baseline).

> NOTE: an earlier project memory claiming "meta-labeling is the validated win" was **wrong** and
> user-corrected (meta-labeling *worsened* outcomes). ML role is decided fresh in Piece 8, not
> anchored on meta-labeling.

### 7a. Label outcome — Triple-barrier, volatility-scaled. LOCKED.
From entry, whichever hits first: upper barrier `+k·ATR` (gain) / lower `−k·ATR` (stop) / time
barrier (40–60d). Store **signed net-return-at-first-touch** as the canonical label. Path-aware,
leakage-resistant, and **independent of the exit stack** (Piece 9) — so exit tuning never
invalidates labels. Rejected fixed-horizon (path-blind) and full-exit-sim (circular until exits
frozen).

### 7b. Label population — Eligible pool, sampled daily. LOCKED.
Label every name passing the fundamental gate, daily. Lets us measure whether the technical gate +
trigger actually add value, and supports cross-sectional study/ranking. Rejected candidates-only
(selection bias — never learns what the gates wrongly rejected) and whole-universe (diluted).

### 7c. Label form — continuous, binarize on demand. DEFAULT.
Store continuous signed net-return-at-barrier; binarize (good/bad) downstream as needed.

### Methodological constraints (bind Piece 8)
- **Overlapping-label leakage:** daily sampling → same stock labeled on consecutive days with
  overlapping forward windows → autocorrelation. Training MUST use **purged + embargoed
  walk-forward CV** + uniqueness sample-weighting (or event-sample at trigger dates).
- `OPEN` — barrier multiplier `k`, time-barrier length, ATR window.

---

## Piece 8 — ML Layer

Prior to respect: added model capacity hasn't helped here before, and a meta-filter actively hurt.
Combined with §6's "ship the dumb version if ML can't beat it" → ML is **not** the default.

### 8a. ML strictly deferred from v1. LOCKED.
**v1 ships rules-only** (composite × technical + vetoes/gates) and is fully shippable. ML enters
later as a contained, **gated challenger**, never in the v1 critical path. Rejected build-into-v1
(couples v1's fate to ML, against prior experience) and parallel-opt-in (upfront cost before the
baseline is even validated).

### 8b. First ML experiment — learned factor combiner (GBT). LOCKED.
Gradient-boosted trees replace hand-set pillar/factor weights, learning conditional structure
(e.g. growth matters only when PEG < sector median). Right tool for noisy tabular fundamentals,
smallest leap from the rules frame, inspectable (feature importance / SHAP), clean A/B vs hand
weights. Learning-to-rank and fuel-left classifier are later/secondary.

### 8c. Ship bar — consistency + non-negative return. LOCKED.
Judged on **purged + embargoed walk-forward**. Ships only if it beats the rules baseline in a
majority of OOS folds AND return delta ≥ 0. Durability over headline P&L; a model that wins big in
2 folds and loses in 6 does not ship. Rejected Calmar-only and return-delta-only (both tolerate
lumpy, inconsistent outperformance).

---

## Piece 9 — Exits

Two clocks already built as duals of earlier pieces:
- **Clock 1 (thesis break)** = veto register firing on an open position (Piece 4a). Hard, fires as
  fast as the data refreshes.
- **Clock 2 (price break)** = weekly close below 40-week MA / decisive weekly lower-low (Piece 5b).
  Governing TF weekly → daily noise can't trigger.

### 9a. Soft thesis-decay — valuation-exhaustion only. LOCKED.
Add a soft exit when **PEG/valuation runs to exhaustion** (exit-side mirror of the entry gate;
§5 "valuation exhausted → trim or exit"). **Skip** growth-decel/margin-compression exits — too
noisy quarter-to-quarter; leave those to the hard veto + price break (fundamentals are right but
slow; don't false-exit winners on one wobble). Trim-vs-full → Piece 10.

### 9b. Trailing — two-stage, tighten to weekly 10-week MA. LOCKED.
Young position: wide **40-week** governing stop. Once meaningfully in profit: tighten to **exit on
a weekly close below the 10-week MA**. Structure-based, aligned with weekly governing logic, lets
winners breathe. Rejected chandelier (more shake-outs) and single-wide-stop (gives back most).

### 9c. Recycle — time-since-progress (no new high in N weeks). LOCKED.
Recycle if **no new high / no meaningful progress in N weeks** — catches both never-started and
stalled-after-moving trades; redeploy (not loss-cut) to keep capital working. Rejected
time-since-entry+dead-band (misses stalled-after-move) and no-recycle (idle-capital risk). N is a
tunable (`OPEN`).

### Exit precedence (any clock ringing = act; order sets recorded reason + trim/full)
1. Hard veto (Clock 1) → **full** exit (highest priority)
2. Price break (Clock 2) → **full** exit
3. Valuation exhaustion → trim-or-full (Piece 10)
4. Trailing stop (40-week early → 10-week in profit) → **full** exit
5. Recycle (no new high N weeks) → **full** exit
6. else **hold**

`OPEN` — N (recycle), "meaningfully in profit" threshold for trail tightening, valuation-exhaustion
PEG level.

---

## Piece 10 — Portfolio & Sizing

### 10a. Sizing — risk-based (stop-distance). LOCKED.
`qty = (risk% × sleeve_capital) / (entry − initial_stop)`. Every position risks the same rupee
amount; the stop is the unit of risk. Consistent with the existing book's risk-per-trade logic.
- **Implied stop hierarchy** (REVISED per stress-test R4 — the initial stop is now *wide*, not
  tight; sizing is computed off the wider distance → smaller positions):
  1. **Initial protective stop** — **wide** catastrophe breaker (weekly swing low / large ATR),
     placed beyond daily noise. Sizing denominator AND black-swan exit. May sit near the 40-week
     line. (`OPEN`: weekly-swing-low vs large-ATR basis.)
  2. **Trailing** — once in profit, tighten to weekly 10-week MA (Piece 9b).
  3. **Governing backstop** — 40-week break / veto / recycle (slow).

### 10b. Concentration caps — per-sector % and per-stock %. LOCKED.
- **Max per-sector %** (AMFI macro) — the key momentum protection (validated-momentum names bunch
  in hot sectors; "diversified" can be one bet).
- **Max per-stock %** — no single name dominates.
- (Not chosen: hard max-open-positions count, dry-powder/deployment cap — concurrency is implicitly
  bounded by sleeve capital ÷ per-position risk and the caps.)

### 10c. Two-strategy capital — separate sleeves. LOCKED.
FVM and LRExtrema each get a fixed allocation + own risk limits; neither starves the other. Clean
accounting, independent risk governance; FVM deploys without touching LRExtrema's capital/risk.
Accepted lower capital efficiency. (Sleeve sizes `OPEN`.)

### 10d. Trims / scale-outs — allowed. LOCKED.
Support partial exits — e.g. valuation-exhaustion trims a fraction and rides the rest to a
price/trend break. Reopens position-state complexity:
- Track **remaining qty** per position; P&L attribution across partial exits.
- **Post-trim stop adjustment** (e.g. move remainder to breakeven / tighten trail).
- `OPEN`: trim fraction (e.g. 50%); post-trim stop rule.
- *Caveat:* the existing system has known live scale-out gaps — FVM's trim path must be wired
  end-to-end (entry→partial-exit→remainder→final-exit) and not orphan the remainder.

---

## Piece 11 — Risk Governance & Regime

### 11a. Market-regime filter — light throttle. LOCKED.
Allow **new entries only when Nifty > its 40-week MA** (consistent with the weekly framing); when
risk-off, **stop initiating** but let open positions ride their own exits. Cheap insurance against
momentum crashes (snapback rallies where downtrends mimic fresh breakouts). Interacts with recycle:
in risk-off, recycled capital sits as dry powder until the regime turns — intended. Rejected
per-stock-gate-only (exposed to the crash turn) and regime+breadth (more inputs for v1).

### 11b. Sleeve circuit-breaker — trailing drawdown halt. LOCKED.
Pause new entries if the FVM sleeve's equity falls **> X% from its high-water mark**; resume on
recovery/review. The positional analog of the (meaningless-here) intraday daily-loss limit.
Rejected consecutive-loss (magnitude-blind, streak-noisy) and no-halt (no portfolio backstop). X
and the resume rule are `OPEN`.

### 11c. Earnings events — enter-blackout, hold-through. LOCKED.
**Don't initiate** a new position in the days before a scheduled result (no cushion = coin-flip
gap), but **hold existing positions through** (cushion built; earnings = the thesis catalyst; a
bad print then trips Clock 1 the normal way, post-results). Matches §5 asymmetry. Rejected
hold-through-everything (uncapped entry gap risk) and exit-before-results (sells the catalyst,
churn). Blackout window length `OPEN`. **Needs a forward earnings-calendar feed.**

---

## Piece 12 — Validation & Backtest Methodology

The validation must prove the *specific* thesis — "validated momentum > pure momentum" — not just
"did it make money."

### 12a. Walk-forward — rolling (fixed window). LOCKED.
Train on a fixed trailing window, slide forward (purged + embargoed per Piece 7). Regime-adaptive,
matches non-stationarity; each fold reflects recent conditions. Governs both parameter calibration
and the eventual GBT. Rejected anchored (mixes stale regimes) and both-compare (2× cost for v1).
Window W, step s `OPEN`.

### 12b. Benchmark — naive momentum is decisive. LOCKED.
Primary: **must beat a pure price-momentum portfolio / momentum index** — the only test that proves
the 5-pillar fundamental overlay adds alpha rather than just riding the trend. Secondary floor:
beat Nifty 500 buy-and-hold. If FVM can't beat naive momentum, the fundamental engine is dead
weight. Rejected index-buy&hold-only (doesn't isolate the fundamental contribution) and
absolute-return (regime-flattered, proves no edge).

### 12c. Go-live bar (rules-only v1) — edge-vs-momentum first. LOCKED.
Ordered gate:
1. **Beats naive momentum** on net return (the thesis test), then
2. **Profitable in a majority of walk-forward folds** (durability, same standard as Piece 8c), then
3. **Max drawdown within an acceptable ceiling.**
Rejected consistency-first and Calmar-first (both defer the thesis test; Calmar single-fold-
dominated). Drawdown ceiling `OPEN`.

---

## Architecture Stress-Test (adversarial review)

Ran a deliberate "try to break it" pass before committing. Six findings; resolutions below.

### R1 — FVM may be a more expensive, more timid momentum strategy that can't beat its own benchmark
The technical layer *is* momentum, so FVM ≈ gated/filtered momentum, highly correlated to the
naive-momentum benchmark it must beat. Valuation + extension penalize strength (timidity drag);
recycle/valuation-exhaustion/trim add turnover (cost drag, ~0.2% STT/round-trip). The decisive bar
(beat naive momentum) is exactly the one most at risk — and §6's "complex never beat simple" is the
warning. **Resolution: DEFERRED** — no Plan-B pre-committed; revisit only if validation actually
fails. (Accepted the motivated-reasoning risk of deciding later.)

### R2 — Extension/strength penalized twice → amputates momentum's best winners. RESOLVED.
Valuation pillar AND the technical extension guard both penalized "extended," compounding in the
product. **Fix:** valuation carries "don't buy expensive" at the gate; the extension guard is
demoted from a graded ranking multiplier to a **hard parabolic-entry veto only**. See Piece 5d.

### R3 — Multiplicative fusion over-stacked (~7 sub-1 terms) → rankings collapse toward 0, noise-dominated. FLAGGED.
Geometric mean at each fusion stage is the leading fix (keeps punish-imbalance, restores scale).
**Resolution: NOT decided now** — flagged to revisit during actual dry runs; **fallback = leave as
raw products**. Carry into the dry-run phase as an empirical call, not a design-time one.

### R4 — Tight initial stop whipsaws a weekly-horizon strategy. RESOLVED.
Sizing was letting a tight stop dictate exit behavior against the strategy's own timeframe. **Fix:**
wide catastrophe stop beyond daily noise; size off the wider distance (smaller positions). See
Pieces 5d + 10a.

### R5 — Volume goal vs the gate stack. FLAGGED — validate, don't redesign.
Six stacked filters (fund top-30% + floor + weekly Stage-2 + fresh trigger + regime-on + earnings
blackout + min-scoreability) may thin the intersection to a low trade count — especially since the
best uptrending names grind without pulling back, so the pullback trigger rarely fires on them.
**Resolution: measure trade count in backtest before relaxing any gate.**

### R6 — "True PIT" is far weaker for analyst estimates than for financials. FLAGGED → data-sourcing.
Forward EPS / estimate-revision databases are notoriously non-PIT (silently overwritten, no clean
as-of dates), yet they feed Pillar 2 (PEG blend) and Pillar 5 (revision workhorse). If estimates
aren't genuinely PIT, two pillars are contaminated and R1's test is corrupted. **Resolution: make
genuinely-PIT estimates a HARD requirement in the data-sourcing phase**, or down-scope those
factors.

---

## Piece 13 — Data Sourcing (inventory + plan)

Triage of every dependency by obtainability + PIT fidelity.

### Tier GREEN (easy, PIT-clean)
Daily/weekly price & volume (Kite), Nifty index level, published NSE momentum benchmark index,
AMFI sector map, earnings *dates* for backtest blackout (actual declaration dates). Build on these.

### Tier AMBER (obtainable, PIT with work)
- **Reported financials (P&L/BS/CF)** → Pillars 1, 3, trailing PEG.
- Shareholding pattern (promoter %, FII/DII, instl. count), promoter pledging → Pillar 4.
- (Compliance flags, corporate actions → see decisions below, both removed from v1 hard path.)

### Tier RED (hard / expensive / unavailable retail)
- **PIT analyst consensus forward EPS + revisions** → Pillar 2 forward-PEG leg + Pillar 5.
- **Structured order-book history** → Pillar 5 order-book factor (effectively unavailable).

### CRITICAL FINDING — Pillar 5 is almost entirely RED-dependent
All three Pillar-5 factors need RED data: analyst-revision (estimates), order-book (RED),
sector-tailwind *as defined* (estimate-upgrade breadth). So 15% of the composite + the forward-PEG
leg hinge on the expensive tier.

### Decisions

**13a. Financials PIT — announcement-date join. LOCKED.**
Cheap source for the numbers (Screener/Tijori/Capitaline-class), stamped with each result's
**exchange announcement date** as knowledge-date → kills the ~45-day lookahead leak. Accept residual
restatement leak (rare). Pragmatic PIT backbone for Pillars 1 & 3. Rejected premium-vintaged-vendor
(cost) and build-your-own-archive (zero backtest history — can't validate now).

**13b. Analyst estimates (RED) — modular Pillar 5 + parallel investigation. LOCKED approach.**
Do NOT let estimate procurement gate v1. Build **Pillar 5 in its down-scoped realized-data form**
now; the estimate-fed version is a **pluggable enhancement that must beat the realized-only
baseline to ship** (same discipline as ML in Piece 8). Down-scope spec:
- PEG → **trailing-growth only** (the `min(trailing,forward)` degrades gracefully).
- Estimate-revision factor → **dropped** (no clean substitute).
- Order-book factor → **dropped** (was N/A for most names anyway).
- Sector-tailwind → **redefined on realized data**: sector-aggregate realized profit-growth breadth
  (GREEN data). Pillar 5 shrinks 3→1 factor; **reweight** (likely fold its weight into Pillars 1/2,
  or treat sector-tailwind as a context tilt). `OPEN` — final reweight.
- **Investigation (parallel, user chose "investigate first")** must answer: (1) vendors with Indian
  forward-EPS *dated PIT vintages* (Refinitiv I/B/E/S, Bloomberg, FactSet, S&P CapIQ); (2) Nifty-500
  *tail* coverage; (3) cost/licensing (quote-only, user-led); (4) cheaper PIT-recoverable proxy
  (archive consensus target/rating changes going forward).

**13b — investigation findings (web research, Jun 2026):**
- **I/B/E/S (Refinitiv/LSEG)** = gold standard PIT: Detail History (analyst-level, daily) + Summary
  History (monthly consensus). Intl back to 1987, India covered. BUT enterprise-priced, quote-only;
  India *tail* coverage unconfirmed. Premium fallback.
- **Trendlyne Forecaster** = **pragmatic front-runner** (browser-verified Jun 2026):
  - Coverage strong — 39 analysts on a single large-cap; ~900 companies covers our ~350 universe.
  - Retains historical estimates — actual-vs-estimate time series, beat/miss flags, "3-month analyst
    upgrades" metric (⇒ sub-annual revision tracking exists).
  - **Bulk export exists**: "Stock Data Downloader" (Premium) + "Market Snapshot Data Downloader" /
    "Excel Connect" (StratQ tier).
  - **Pricing trivial**: GuruQ ₹2,190/yr, StratQ ₹5,900/yr (consensus data needs GuruQ/StratQ).
  - **Bonus**: free ASM/GSM dashboard (covers 13c live compliance veto) + free FII/DII dashboard
    (Pillar 4 inputs). Potential multi-purpose source.
  - **STILL UNVERIFIED (needs paid login):** are the historical estimates genuinely *dated PIT
    snapshots* (not silently overwritten), at what depth, and bulk-pullable historically? → a
    **₹5,900 StratQ subscription test of the Data Downloader/Forecaster history** settles it.
- **sharpely.in** = research/backtest **platform**, NOT a cheap raw-data feed (browser-verified):
  ~15yr bias-free PIT history but *inside the tool*; raw access only via Enterprise "APIs/data feeds"
  (quote-only); live-data Excel Xport on annual plans. **No analyst-estimate/forecaster product** →
  does NOT solve the RED gap. Pro ₹5,799/yr, Black ₹12,499/yr, Enterprise = contact. Use: independent
  cross-check / possible Enterprise feed if Trendlyne fails — not the estimate solution.
- **I/B/E/S (LSEG)** = premium fallback, quote-only institutional; browser adds nothing (contact sales).
- **Cheap proxy (still valid):** Trendlyne tracks broker upgrades/downgrades + target changes →
  archive going forward for a PIT revision signal even if historical vintages disappoint.

**Verdict:** Trendlyne is the front-runner — cheap, covered, has bulk export, throws in ASM/GSM +
FII/DII. The single gate is PIT-genuineness of its estimate history, resolvable by a ₹5,900 StratQ
trial. sharpely and I/B/E/S are fallbacks, both gated behind quote-only Enterprise tiers.

### 13f. Sourcing consolidation — the plan collapses to ~2 sources

The full dependency list resolves into two providers:

**A. Trendlyne (StratQ ₹5,900/yr)** — *candidate one-stop* for the entire fundamental+ownership+
compliance+earnings layer. Its stock pages expose Financials, Shareholding, Deals, Corporate
Actions tabs + Quarterly Results Tracker + free ASM/GSM + FII/DII dashboards + Forecaster estimates.
Plausibly covers **5 of 8 dependency clusters at once**:
- Analyst estimates (Pillar 2 forward-PEG + Pillar 5)
- Reported financials (Pillars 1, 3) — *announcement-date availability TBD*
- Shareholding / pledging / FII-DII / instl count (Pillar 4)
- ASM/GSM compliance flags (13c live veto)
- Earnings dates (blackout 11c + financials PIT join)

→ **One paid StratQ session tests the whole cluster** (PIT-genuineness, announcement dates, bulk
export). No free trial, so verification costs ₹5,900 — trivial if it one-stops the layer.

**B. Kite + NSE/niftyindices (free/owned)** — the GREEN independents:
- Price/volume (Kite, already in use; weekly derived) — DONE
- Nifty index level + naive-momentum benchmark (Nifty500 Momentum 50 / Nifty200 Momentum 30, from
  niftyindices) — DONE
- PIT index membership (niftyindices historical reports + reconstitution change-lists; reconstruct
  by back-applying) — DONE
- AMFI sector classification (+ our ≥20/bucket coarsening) — DONE

**Reddit note:** direct Reddit access blocked (crawler + browser); general reviews rate Trendlyne
"worth it" for retail research but don't speak to our PIT-data gate — only the StratQ session does.

Fallbacks if Trendlyne's PIT estimate history disappoints: Screener/Tijori/Capitaline for financials
(announcement-date join), I/B/E/S (premium) or sharpely-Enterprise for estimates.

### 13g. StratQ paid-session verification results (Jun 2026) — KEY OUTCOME

Purchased StratQ; drove a live verification session. Findings reshape the plan into a
**LIVE-data vs BACKTEST-data split**:

- **Estimates ARE genuine point-in-time** — the Forecaster "Revisions Estimate" tab shows consensus
  for a *fixed* target (FY27/FY28) as-of 90/60/30/7-days-ago + current, with % deltas. They
  snapshot and retain dated estimates. **BUT the Forecaster dataset is "display-only" licensed and
  CANNOT be exported on any plan** (Trendlyne FAQ, confirmed) — and the on-page history is only
  ~90 days. ⇒ **Not a viable bulk backtest feed for estimates.** Usable live (read per-stock) only.
- **Trendlyne's downloaders are current/realtime *snapshot* tools**, not historical-time-series
  archives ("Market **Snapshot** Downloader", "Excel Connect … in **realtime**"; Stock Data
  Downloader = parameters-for-a-stock-group → Excel). Financials & Shareholding are downloadable
  *parameter groups* but oriented to current values.

**⇒ Sourcing splits in two:**
- **LIVE layer — Trendlyne (StratQ ₹5,900/yr) WINS, cheaply.** Covers the running bot's daily reads:
  current financials, shareholding, FII/DII, **ASM/GSM (free, = 13c live veto — DONE)**, forward
  earnings calendar (11c), on-screen estimates. Great value for live.
- **BACKTEST layer — Trendlyne does NOT solve it.** Multi-year historical financials (+ announcement
  dates), shareholding/pledging time-series, and estimate history need a *time-series* source →
  **new task #9** (Screener/Tijori/Capitaline; estimates remain the hard gap → modular realized-only
  Pillar 5 stands, estimate enhancement is live-only or premium-for-backtest).

**Net:** Trendlyne is confirmed as the LIVE data layer (cheap win, ~5 live needs covered). The open
front is now the **backtest historical-fundamentals source** (#9), and estimate *history* for
backtest stays unsolved (acceptable — Pillar 5 was already modular/realized-only for v1).

### 13h. Screener.in — backtest historical-fundamentals source (Jun 2026, logged-in verify)

Strong fit for Task #9. Per-company page (UltraTech) delivers:
- **P&L / Balance Sheet / Cash Flow: 12 years annual (Mar 2015→2026)** incl. **CFO + CFO/OP ratio**
  (CFO/NP veto+penalty), Borrowings (debt + trend), ROCE%, OPM%, NP, EPS, Reserves/Equity.
- **Quarterly results: ~13 quarters** — enough for the 8q acceleration factor.
- **Shareholding (quarterly ~12q):** Promoters / FIIs / DIIs / Govt / Public / No. of Shareholders
  (Pillar 4: promoter %, FII/DII trend, instl-holder-count).
- **EXPORT TO EXCEL** per company (all sheets); dated **Announcements** feed; **Upcoming result
  date** (forward); annual reports FY2011→25; concall history.

**Covers backtest halves of #2 (financials), #4 (shareholding), #6 (historical result dates).**

**Caveats / open items:**
- **Announcement-date join (13a):** financial columns are *period-labelled* (Mar 2023), NOT
  declaration-date stamped. The dates exist (Announcements feed, Upcoming-result-date, filing PDFs)
  but must be *assembled* to apply true-PIT knowledge-dates. Pragmatic fallback: fixed conservative
  lag (results known ~45d after quarter-end) if exact-date assembly is heavy.
- **Restatement-PIT:** Screener shows current/restated figures (not vintaged) — residual restatement
  leak, already accepted in 13a.
- **Delisted/survivorship:** Screener centres on *listed* names; financials for *delisted* members
  are likely missing → even with PIT membership (#3), the financial-data dimension may force testing
  on currently-listed survivors (residual survivorship in data, not universe). DESIGN TRADE to flag.
- **Bulk access:** per-company Excel export → scripting ~350 exports (or unofficial API); free-tier
  export limits TBD.
- **Pledging:** not visible in the top shareholding table — needs verification (expand Promoters /
  BSE filings).

**Net:** Screener = viable, cheap/near-free backtest source for Pillars 1/3/4. Two genuine residual
gaps: delisted-name financials (survivorship in data) and pledging coverage; announcement dates are
assembly-work, not missing.

**13e. Survivorship bias — PIT index membership. NEW REQUIREMENT.**
Current Nifty-500 membership as the historical universe overstates backtest returns (~20–25% on
small-caps, less on large, but real) — delisted/demoted names vanish. Need **point-in-time index
constituents** (membership as-of each historical date, including later-dropped names; NSE publishes
historical reconstitutions). The "~350 names" set is NOT static. Must be explicit or Piece-12
validation is inflated before it runs. Tier GREEN-ish.

**13c. Compliance veto (GSM/ASM/T2T) — live-only. LOCKED.**
Apply live (current NSE lists, trivial); **omit from backtest** (historical membership patchy).
Backtest slightly overstates the universe — accepted (rare-stock veto). No historical-archive hunt.

**13d. Promoter-sell veto — penalty-only fallback. LOCKED.**
Drop the hard promoter-sell veto; falling promoter holding becomes a **strong graded Pillar-4
penalty** instead. **Eliminates the corporate-actions feed from v1 entirely.** Consequences: backtest
hard-veto register = {CFO, D/E+coverage, pledge, manufactured-earnings}; promoter-selling is no
longer a Clock-1 exit trigger (acceptable). Rejected keep-conservative-veto (messy corp-action
plumbing) and strict-veto (false-kills growth dilutions).

---

## Piece 14 — Field-by-Field Source Map

Every factor input → raw fields → source → cadence → PIT method. **BT** = backtest, **LV** = live.
Sources: **SCR** = Screener.in, **TL** = Trendlyne StratQ, **KITE** = Zerodha, **NSE** = NSE/niftyindices,
**AMFI** = sector map. Newly-surfaced gaps flagged ⚠.

### Pillar 1 — Earnings (quarterly P&L)
| Factor | Raw fields | Source | Cadence / PIT |
|---|---|---|---|
| Growth Acceleration | Net Profit ×8q, Revenue (TTM, for floor F_t) | SCR (BT) / TL (LV) | Quarterly; announce-date stamp or 45d-lag |
| YoY Profit Growth | Net Profit, Revenue (floor) | SCR / TL | Quarterly |
| Revenue Growth | Sales/Revenue | SCR / TL | Quarterly |
| OPM Trend | Operating Profit, Revenue (6q) | SCR / TL | Quarterly |
| Earnings Consistency | Net Profit YoY-series (6–8q) | SCR / TL | Quarterly |

### Pillar 2 — Valuation
| Factor | Raw fields | Source | Cadence / PIT |
|---|---|---|---|
| PEG | Price; TTM EPS; trailing growth; **forward growth** | KITE (price) + SCR (EPS/growth); forward = TL **LV-only** | Price daily; EPS quarterly; **BT → trailing-only (no forward)** |
| P/E vs own history (3y) | Daily price; TTM EPS | KITE + SCR | Daily P/E over 3y; mask EPS<0 slices |
| EV/EBITDA | MktCap (price×shares); **Debt**; **Cash**; TTM EBITDA | KITE + SCR (BS) | BS annual → EV staler. ⚠ **Cash not isolated in SCR summary BS** (folded in "Other Assets") → use gross-debt EV or pull raw BS |

### Pillar 3 — Balance Sheet (annual / semiannual)
| Factor | Raw fields | Source | Cadence / PIT |
|---|---|---|---|
| CFO/NP (veto+penalty) | CFO, Net Profit | SCR (Cash Flow; has CFO + CFO/OP) | **Annual** (SCR CF) |
| D/E (norm + veto) | Borrowings, Equity+Reserves | SCR (BS) | Annual |
| Interest Coverage | EBIT (≈Op Profit), Interest | SCR (P&L) | Quarterly/annual |
| Debt Trend | Borrowings series | SCR (BS) | Annual slope |
| ROCE (level+slope) | ROCE% (given) | SCR (Ratios) | Annual |

### Pillar 4 — Ownership (quarterly shareholding)
| Factor | Raw fields | Source | Cadence / PIT |
|---|---|---|---|
| FII trend | FII % | SCR / TL | Quarterly, filing-dated |
| DII trend | DII % | SCR / TL | Quarterly |
| Promoter holding (penalty) | Promoter % | SCR / TL | Quarterly |
| Pledging (veto+penalty) | Pledged % | SCR ("Pledged percentage") | Quarterly; ⚠ historical-depth TBD |
| **Institutional-holder count** | # of FII/MF holders | ⚠ **GAP** — SCR gives total "No. of Shareholders", not institutional-entity count | ⚠ likely drop/approximate v1 |

### Pillar 5 — Forward Visibility
| Factor | Raw fields | Source | Cadence / PIT |
|---|---|---|---|
| Analyst Revision | Forward EPS revisions | TL **LV-only** (display-locked) | ⚠ **BT → dropped** (modular Pillar 5) |
| Order Book | contracted revenue | ⚠ **dropped** (no source) | — |
| Sector Tailwind | realized sector profit-growth breadth | **computed** from SCR P&L + AMFI sectors | Quarterly; no external source |

### Technical / sizing / regime — all from price
| Item | Raw fields | Source |
|---|---|---|
| Trend_Score (40w/10w MA) | Weekly OHLC | KITE (weekly from daily) |
| Timing (50d MA, ATR, base/breakout, volume) | Daily OHLCV | KITE |
| Extension guard / initial stop | ATR, 50d MA, weekly swing low | KITE |
| Regime throttle (11a) | Nifty + 40w MA | NSE/KITE |

### Vetoes
| Veto | Fields | Source |
|---|---|---|
| CFO<0 & NP>0 | CFO, Net Profit | SCR |
| D/E>ceiling & coverage<min | Borrowings, Equity, EBIT, Interest | SCR |
| Pledge high & rising | Pledged % | SCR |
| Manufactured earnings | Revenue YoY, Net Profit YoY | SCR |
| GSM/ASM/T2T | flag lists | TL **LV-only** (backtest omits) |

### Universe / validation / earnings
| Item | Source | Note |
|---|---|---|
| PIT index membership | NSE/niftyindices reconstitution | back-apply change-lists; ⚠ delisted-financials gap (SCR) |
| Liquidity filter | KITE turnover | daily |
| Sector / financials-exclusion | AMFI | static-ish |
| Naive-momentum benchmark (12b) | NSE (Nifty500 Momentum 50 / 200 Momentum 30) | published index history |
| Earnings blackout (11c) | TL calendar + SCR "Upcoming result date" (LV); SCR Announcements (BT dates) | — |

### Data gaps surfaced by this map (the point of doing it)
1. ⚠ **Institutional-holder COUNT (Pillar 4)** — Screener gives total shareholder count, not # of
   FII/MF *entities*. No clean BT source → **drop or approximate (use No.-of-Shareholders proxy) for
   v1**; revisit if TL exposes it. Lowest-weight Pillar-4 factor; minimal loss.
2. ⚠ **EV/EBITDA cash (Pillar 2)** — Screener summary BS folds cash into "Other Assets"; net-debt
   needs isolated cash. **v1: use gross-debt EV** (or pull raw BS PDF). Acceptable approximation.
3. ⚠ **Forward estimates** — BT none (Pillar 5 realized-only; PEG trailing-only). Already designed.
4. ⚠ **Delisted-name financials** — survivorship-in-data (Screener); v1 likely on listed survivors.
5. ⚠ **Pledging history depth** + **announcement-date assembly** — implementation effort, not missing.

**Verdict:** every v1 factor has a feed except two low-weight degradations (institutional-count drop,
gross-debt EV) and the already-designed estimate down-scope. No factor is *unfeedable* — the map is
green enough to build.

---

## Piece 15 — Ingestion Route (API vs Chrome-scrape)

Goal: minimize fragile/ToS-risky browser scraping; prefer real programmatic access.

| Source | Data | Route | Type |
|---|---|---|---|
| **Kite Connect** | price/volume, live | Official REST API (already used; ~₹2000/mo hist) | ✅ Clean API |
| **Trendlyne Excel Connect** | financials + shareholding, **current + historical** | Token feed → Google Sheets/Excel (official feature) | ✅ Semi-API |
| **Trendlyne Forecaster** | analyst estimates | **display-only license — NOT exportable** | ⛔ Browser-display only |
| **Screener.in** | financials/shareholding (historical) | CSV/Excel export endpoint; no official API (Apify wrapper) | ⚠ Scriptable export, ToS-gray |
| **NSE/niftyindices** | index, membership, benchmark, ASM/GSM | CSV/file downloads + unofficial JSON | ⚠ Semi-API (file), fragile |

### Key conclusions
- **Chrome-scrape is needed for ~zero essential v1 data.** The only display-locked item is analyst
  estimates (Trendlyne Forecaster), and those are already OUT of the v1 critical path (Pillar 5
  realized-only, PEG trailing-only). Everything else has an API / scriptable export / file route.
- **Correction to 13g:** the "current-snapshot only" limit was the *Data Downloader*. **Excel Connect
  pulls current AND historical financials** via token into Sheets/Excel → Trendlyne can
  programmatically serve **backtest financials too**, potentially reducing the Screener dependency.
  `OPEN` — verify Excel Connect historical depth + whether it covers shareholding.
- **Legitimacy ladder:** cleanest legit programmatic = **Kite API + Trendlyne Excel Connect**.
  Screener export-scripting + NSE JSON are ToS-gray/fragile → acceptable for a personal system with
  rate-limiting/caching; if Excel Connect depth suffices, lean on it and treat Screener as
  fallback/cross-check to shrink the gray-area surface.
- **ASM/GSM:** source directly from **NSE** (published lists) rather than scraping Trendlyne's
  dashboard — avoids a browser dependency for the live compliance veto.

### 15a. Excel Connect — verified live (Jun 2026, authorized session)

Inspected the authorized Sheet. **Strong result for fundamentals:**
- **Depth: 10+ years annual** (Mar 2026 → Mar 2017+) across **Quarterly-P&L, Annual-P&L, Balance
  Sheet, Cash Flow** tabs.
- **CFO present + deep** (Cash from Operating Activity, 10+ yr) → Pillar 3. OPM%, **EBITDA**, revenue
  YoY pre-computed → Pillar 1 + EV/EBITDA. Interest, depreciation, PBT present.
- **Both Standalone AND Consolidated** provided (consolidated default usable). Backing **"Annual -
  Raw Data" sheet with up to 299 parameters**.
- Token-based, official feature → **legitimate programmatic route** (scriptable via the Sheets
  connector's endpoint).

**Hard constraint — RATE LIMITS: 50 stocks/day, 500/month** (stated on the sheet). Implications:
- *Backtest one-time pull* of ~350 stocks = ~7 days @ 50/day, within 500/mo. Feasible, slow.
- *Live* fundamentals refresh is event-driven (only stocks that just reported) → well within limits
  except possibly peak results season; fundamentals change quarterly so no daily re-pull. Workable.

**Gaps:**
- ⚠ **No Shareholding** in Excel Connect → Pillar 4 historical still needs Screener (or the Stock
  Data Downloader's Shareholding group = current snapshot only).
- Estimates still display-locked (unchanged).

**⇒ Revised ingestion stack (cleaner, more legit):**
- **Fundamentals (Pillars 1, 3, + EBITDA/debt for Pillar 2)** → **Trendlyne Excel Connect**
  (10+ yr, consolidated, legit, rate-limited) — *replaces the Screener ToS-gray scrape for
  financials*. Screener becomes fallback/cross-check.
- **Shareholding (Pillar 4)** → Screener (historical) — the one remaining gray-area/scrape need.
- **Price/index/membership/benchmark** → Kite API + NSE files.
- **Estimates** → out of v1 backtest; live read-only.

Net: the only ToS-gray/scrape surface left is **Pillar-4 historical shareholding** (Screener);
everything else is Kite API + Trendlyne Excel Connect (official) + NSE files.

### 15b. Excel Connect API spike — RESOLVED (method b: direct REST)

Read the connector's bound Apps Script. Excel Connect is backed by a **versioned token REST API**:
- `GET https://trendlyne.com/fundamentals/fincsv/v1/quarter/?stock_hash=<hash>` → CSV (quarterly)
- `GET https://trendlyne.com/fundamentals/fincsv/v1/annual/?stock_hash=<hash>` → CSV (annual)
- `GET …/v1/get-expiry/` → token-validity check; + a stock-master-list endpoint (symbol → stock_hash)
- **Auth:** request header `tltoken: Token <token>` (token from the user's Trendlyne account);
  a logged-in session **Cookie** is also passed by the script.
- Rate limit (50/day, 500/mo) enforced **server-side per token**.

**⇒ Ingestion method = call these endpoints directly from Python** (requests → parse CSV → PIT
store). No Google Sheets / Apps Script in the production loop; the Sheet was only the discovery
vehicle. `stock_hash` per symbol comes from the master-list endpoint (fetch once, cache).

**SECURITY NOTE:** the user's session cookie + csrftoken are hard-coded inside the sheet's Apps
Script — should be treated as a secret (rotate if shared).

### 15c. fincsv API — verified contract + the cookie wrinkle (Phase 0.2 probe)

Probed the live API from Python (read-only). **Confirmed endpoints** (all GET, return CSV/JSON):
| Endpoint | Auth | Result |
|---|---|---|
| `…/fincsv/v1/get-expiry/` | `tltoken` header + browser UA | ✅ 200 JSON `{expires_on, is_expired}` |
| `…/fincsv/v1/all_stocks/` | `tltoken` + UA | ✅ 200 CSV — **7,608 stocks**, cols `ISIN, NSEcode, BSEcode, Company, Unique Code (=stock_hash), Currency` |
| `…/fincsv/v1/quarter/?stock_hash=<h>` | `tltoken` + UA + **session Cookie** | ⚠ 403 without a valid session cookie |
| `…/fincsv/v1/annual/?stock_hash=<h>` | `tltoken` + UA + **session Cookie** | ⚠ 403 without a valid session cookie |

- **WAF blocks `python-requests` UA** → must send a real browser User-Agent.
- **The data endpoints (quarter/annual) require a valid logged-in session Cookie** in addition to the
  stable `tltoken` — the master/expiry endpoints do not. Confirmed by: the Apps Script attaches the
  Cookie *only* to the financials call, and Excel Connect demonstrably works (the sheet fetched real
  data) = token + valid cookie works; a stale cookie 403s. (In-browser fetch + cookie extraction are
  blocked by the automation safety layer — correctly.)
- **Mitigating context:** fundamentals change *quarterly*, so fetches are infrequent — a session
  cookie valid for days/weeks easily covers both the one-time backtest pull (~7 days @ 50/day) and
  ongoing event-driven refresh. So cookie *longevity* matters less than for a high-frequency feed.

`OPEN — needs user decision (Phase 0.2 blocker):` how to supply/refresh the Trendlyne **session
cookie** for the financials endpoints. Options: (1) Python login routine (user's Trendlyne
credentials → fresh session+csrf, à la kite_totp_refresh) — most robust/unattended; (2) manual
periodic cookie paste into `.env` — simple, fine given quarterly cadence; (3) fall back to Screener
for backtest financials (ToS-gray scrape) and keep Trendlyne for live reads only.

---

## End-to-End Locked Pipeline (v1, rules-only)

```
Universe: ~350 Nifty 500/750 non-financials, PIT-vintaged fundamentals
  │
  │  FUNDAMENTAL ENGINE (5 pillars, sector-relative where noted, daily rank recompute)
  │   factors → winsorize(caps→1/99) → normalize(percentile; z for PEG) → pillar → composite 0–100
  │   absence: missing→0.5 | N/A→drop&renormalize
  │
  ├─ VETOES (binary; = Clock 1 on open positions): CFO<0&NP>0 | D/E&coverage |
  │          promoter-sell-into-strength(corp-action-exonerated) | pledge | mfd-earnings | GSM/ASM/T2T
  │
  ▼  GATE A — eligible if composite pctile ≥ 70th AND ≥ absolute floor AND min-scoreability AND no veto
Eligible pool
  ▼  GATE B (hard) — weekly Stage-2 uptrend confirmed (Trend_Score floor)
Trend-confirmed pool
  ▼  TRIGGER (event-driven) — fresh daily pullback OR breakout; parabolic-extension entry-veto (R2)
Entry candidates
  ▼  RANK — within-pool fundamental pctile × Technical_Score  (fuse via geo-mean? — flagged R3)
  ▼  SIZE — risk-based off WIDE catastrophe stop (R4); caps: per-sector %, per-stock %; FVM sleeve only
Positions
  ▼  EXITS (any clock = act; precedence): hard-veto → weekly trend-break → valuation-exhaustion(trim)
      → trailing(40wk→10wk in profit) → recycle(no new high N wks) → else hold/trail

ML (deferred, gated): GBT factor-combiner challenger; ships only if it beats this rules baseline
  in a majority of purged/embargoed walk-forward folds AND return delta ≥ 0.
Labels: triple-barrier (vol-scaled), eligible-pool daily, continuous net-return-at-touch.
```

## Consolidated OPEN tunables (set at calibration)
- Fundamental: absolute composite floor; 70th pctile cut; per-pillar/factor weights (start
  round-number; learn only via the gated GBT); ATR floor `F_t`=1%·TTM-rev; winsor caps.
- Technical: 40w/10w MA mapping; Trend_Score gate floor; N×ATR extension threshold; volume-expansion
  factor; pullback proximity band.
- Labels: barrier multiplier k; time-barrier 40–60d; ATR window.
- Exits: "in profit" threshold for trail tighten; valuation-exhaustion PEG level; recycle N weeks;
  initial-stop basis; trim fraction + post-trim stop rule.
- Portfolio: FVM vs LRExtrema sleeve sizes; per-sector %, per-stock %, risk% per trade.

## Data dependencies (post Piece 13 triage)
**v1 hard path (GREEN/AMBER, must have):**
- Reported financials P&L/BS/CF, announcement-date-stamped (13a) → Pillars 1, 3, trailing PEG.
- Shareholding pattern + promoter pledging (quarterly, filing-dated) → Pillar 4.
- Weekly + daily price/volume; Nifty index level (regime); published momentum benchmark (validation).
- **PIT index membership** — historical Nifty-500 constituents as-of each date, incl. later-dropped
  names (survivorship, 13e). NSE historical reconstitutions.
- AMFI sector map (coarsened to ≥20/bucket).
- Earnings declaration dates (backtest blackout); forward earnings-calendar feed (live blackout, 11c).

**Optional / deferred (RED, NOT on v1 critical path):**
- PIT analyst forward EPS + revisions — parallel investigation (13b); plug-in enhancement only.
- Structured order-book history — dropped for v1 (13b).

**Removed from v1:**
- Corporate-actions feed — eliminated by the promoter penalty-only decision (13d).
- Historical compliance-flag archive — compliance is live-only (13c).

## Status
All 12 design pieces worked (spine → factors → scoring → vetoes → technical+scoring functions →
handoff → labels → ML → exits → portfolio/sizing → governance/regime → validation). v1 = rules-only,
shippable without ML. **Architecture is complete** — remaining work is data-sourcing, formula/
threshold calibration of the OPEN list, and implementation, not further design.
- Piece 7 — Labels (the single most consequential ML decision).
- Piece 8 — ML layer (weights/interactions/ranking; must beat rules-based baseline).
- Piece 9 — Exits (thesis-break / price-break / opportunity-recycle / trail).
- Piece 10 — Portfolio & sizing.

### New data dependencies surfaced during design
- PIT vintaged fundamental store (P&L, balance sheet, cash flow, shareholding).
- Analyst consensus forward EPS (feeds PEG + estimate-revision).
- Corporate-actions feed (QIP/ESOP/issuance) — to exonerate promoter-holding-drop veto.
- Order-book data for the ~4 relevant sectors.
- Compliance flags (GSM/ASM/T2T).
