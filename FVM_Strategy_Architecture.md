# Fundamentally-Validated Momentum (FVM)

A strategy design document — high-level architecture.

This describes a second, structurally independent strategy intended to run alongside
LRExtremaStrategy. Where LRExtrema is intraday, mean-reverting, buys weakness, and is
purely technical, FVM is positional, momentum-with-justification, buys *validated*
strength, blends fundamentals with technicals, and trades a broad universe with a
variable holding period.

This document is the **what** and the **why**. Data sourcing, pipelines, exact
formulas/thresholds, and implementation are intentionally deferred to later sessions.

---

## 1. Core Thesis

> Buy stocks that are moving up **because something real is driving them**, where that
> driver still has runway — applied uniformly across the entire universe — and exit when
> either the move matures or the fundamental justification weakens.

For every stock, every time, the strategy answers three questions:

1. **Is it moving?** (technical strength)
2. **Is the move justified?** (fundamental backing)
3. **Is there fuel left?** (runway — growth vs valuation)

A stock must pass all three. Pure momentum passes only #1. LRExtrema plays a different
game entirely. This is the gap FVM fills.

### Design constraints it must respect

- **Profit-taking, not asset-building** — every position is meant to be sold.
- **Volume of trades matters** — many opportunities across many stocks, not 3 perfect
  trades a year.
- **Variable holding period is fine** — hours to months, as long as it exits at profit.
- **One uniform logic across the whole universe** — a stock either qualifies for a
  signal or it doesn't. Per-stock overrides exist only as guardrails (exclusions,
  position limits), never as different logic per stock.
- **Multi-timeframe thinking allowed** — but the *same* multi-timeframe recipe for
  every stock.

---

## 2. The Fundamental Engine — Five Pillars

Each pillar answers a specific question about whether a move deserves to continue.

### Pillar 1 — Earnings Quality & Growth (≈35%) — the engine

The single most important pillar. Price follows earnings over time.

- **YoY Quarterly Net Profit Growth** — this quarter vs the same quarter last year
  (YoY, not QoQ, to kill seasonality).
- **Profit Growth Acceleration** — is the *rate* of growth itself rising across the last
  3–4 quarters? `20% → 35% → 55%` earns a re-rating; flat `30% → 30% → 30%` does not.
  **This is the crown-jewel factor.**
- **Revenue (Topline) Growth YoY** — harder to fake than profit. Profit rising while
  revenue is flat is a yellow flag (cost-cutting, not expansion). Profit growing *faster*
  than revenue = margin expansion (best case).
- **Operating Margin (OPM) Trend** — expanding margin on rising revenue = operating
  leverage = highest-quality growth.
- **Earnings Consistency** — steady compounding over the last 4–8 quarters beats one
  explosive quarter among several poor ones.

### Pillar 2 — Valuation Runway (≈25%) — the "fuel left" gate

Directly answers "already up 40%, why would it rise more?"

- **PEG Ratio (P/E ÷ growth)** — central number. High P/E is justified if growth is
  higher still. `< 1` strong, `1–1.5` acceptable, `> 2` exhausted.
- **P/E vs Own History** — a grower trading at its *historical-low* P/E has re-rating
  runway even after a price move.
- **P/E vs Sector/Peers** — the cheapest grower in a hot sector tends to catch up.
- **EV/EBITDA** — cross-checks P/E; strips capital-structure and one-off distortions.
  Important for capital-heavy names.

This pillar is the discipline against buying tops. A 40%-up stock with PEG still under 1
has fuel; the same stock with PEG at 4 is running on fumes — avoid, however strong the
chart.

### Pillar 3 — Balance Sheet Health (≈10%) — mostly a penalty / veto

Rarely *picks* a winner; frequently *saves* you from a blow-up.

- **Debt-to-Equity** — sector-adjusted ceiling; penalize fragility.
- **Interest Coverage (EBIT ÷ interest)** — can it service debt comfortably?
- **Debt Trend** — *falling* debt is a quietly bullish improving-story signal.
- **Operating Cash Flow vs Net Profit** — does profit convert to cash? If profit is high
  but CFO is weak, earnings are suspect. **The strongest early-warning for accounting
  weakness.**
- **ROCE / ROE** — capital efficiency. High *and rising* = genuine quality.

### Pillar 4 — Institutional & Ownership (≈15%) — smart-money confirmation

- **FII/DII Holding Trend** — institutions increasing stake QoQ; accumulation often
  *precedes* sustained moves.
- **Promoter Holding & Trend** — high/stable/rising = confidence; falling into strength =
  serious red flag.
- **Promoter Pledging** — rising pledges = stress; penalize.
- **Count of Institutional Holders** — a rising number of MFs/FIIs = broadening
  conviction.

Fundamentals tell the story; ownership tells you whether informed money is acting on it.

### Pillar 5 — Forward Visibility (≈15%) — the road ahead

The robust, structured pieces (news/sentiment deliberately excluded):

- **Order Book / Inflow Trend** — contracted future revenue (infra, defense, capital
  goods, EPC). Highly predictive for those sectors.
- **Analyst Estimate Revision Direction** — forward EPS revised *up*. One of the most
  robust factors in quant; a clean number, not a headline.
- **Sector Tailwind Score** — is the whole sector being structurally re-rated? Context
  for the other pillars.

> **Note on news:** explicitly excluded from the core engine. Headline sentiment is
> noisy, reflexive, speed-disadvantaged for retail, and unevenly distributed across the
> universe (biasing toward already-efficient large caps). Only the *structured, factual*
> slice (filings, order wins, estimate revisions) belongs here — and it already lives
> inside Pillar 5.

### The two factors that do the heaviest lifting for the core thesis

- **Profit Growth Acceleration** (Pillar 1) — proves the engine is still revving.
- **PEG + P/E-vs-own-history** (Pillar 2) — proves price hasn't outrun the engine yet.

Together they answer "is there fuel left?" better than any technical signal can.

---

## 3. Scoring Math — Raw Factor to Composite Score

Flow: **raw factor → cleaned → normalized → pillar score → composite score →
vetoes applied.**

### Stage 1 — Raw factor computation

Three factor types:

- **Level factors** — a snapshot (PEG = 0.8, D/E = 0.4, OPM = 18%).
- **Growth factors** — a change (YoY profit growth = +42%).
- **Trend factors** — a direction over time. Fit a **slope** across the last N quarters
  (e.g., regress the OPM series, or the growth-rate series for acceleration, against the
  quarter index; positive slope = improving).

### Stage 2 — Cleaning & outlier handling (do not skip)

- **PEG with growth ≈ 0** explodes → winsorize (e.g., cap PEG to `[0, 5]`).
- **Negative earnings** make P/E and PEG meaningless → map to a floor score explicitly;
  never let a negative P/E look "cheap."
- **Extreme growth from a tiny base** (₹1cr → ₹10cr = +900%) → winsorize growth
  (e.g., cap at ±200%).
- Rule of thumb: **winsorize every factor at the 1st/99th percentile** of the universe
  before normalizing.

### Stage 3 — Normalization (the heart of it)

**Default: percentile rank (cross-sectional).** For each factor, rank all stocks into
`[0, 1]`. Median = 0.5, best = 1.0, worst = 0.0.

- Robust to outliers and distribution shape.
- Self-calibrating to the universe; regime-robust (in a bull market everyone's growth is
  high, but percentile still separates the field).
- You're building a ranking engine — relative position is what you act on.

Z-scores are the alternative (preserve magnitude) but misbehave on the fat-tailed, skewed
distributions typical of financial ratios. If magnitude matters for a specific factor
(e.g., PEG), z-score *that one* and percentile the rest — but start uniform with
percentiles.

**Directionality — critical:** flip "lower-is-better" factors (PEG, D/E, pledging) before
ranking so that **1.0 always means good** across every factor. Fix this sign convention
once, centrally, or the whole score silently inverts.

### Stage 4 — Factor → pillar score

```
Pillar_score = Σ (factor_weight × normalized_factor)     # weights sum to 1 per pillar
```

Example, Pillar 1 (Earnings):

| Factor                     | Weight |
|----------------------------|:------:|
| Profit Growth Acceleration | 0.30   |
| YoY Profit Growth          | 0.25   |
| Revenue Growth             | 0.20   |
| OPM Trend                  | 0.15   |
| Earnings Consistency       | 0.10   |

(Acceleration weighted highest — thesis-critical.)

### Stage 5 — Pillar → composite Fundamental Score

```
Fundamental_Score = 100 × Σ (pillar_weight × pillar_score)
```

| Pillar                       | Weight |
|------------------------------|:------:|
| Earnings Quality & Growth    | 0.35   |
| Valuation Runway             | 0.25   |
| Forward Visibility           | 0.15   |
| Institutional / Ownership    | 0.15   |
| Balance Sheet Health         | 0.10   |

Result: a clean **0–100** score per stock, each point interpretable as weighted
percentile standing across all fundamentals.

### Stage 6 — Vetoes (applied AFTER scoring, as binary gates)

A stock either passes all or is disqualified regardless of its 0–100 score:

```
if (CFO < 0 and NetProfit > 0):                      VETO   # earnings-quality failure
if (pledge_pct > threshold and pledge_rising):       VETO
if (promoter_selling_into_strength):                 VETO
if (D/E > sector_ceiling and interest_coverage<min): VETO
if (revenue_declining and profit_rising_sharply):    VETO   # manufactured earnings
# plus existing compliance: GSM / ASM / T2T flags
```

Keep vetoes separate from the score so you can always inspect *why* a high-scoring stock
was rejected. A great score with one veto = no trade.

### Two robustness principles

1. **Sector-relative normalization where it matters.** A 0.6 D/E is alarming for IT,
   normal for infra; banks have no usual "OPM." At minimum, normalize **valuation and
   leverage** factors *within sector*. Growth factors can stay universe-wide.
2. **Don't over-optimize the weights (yet).** Start with these simple, defensible,
   round-number weights — deliberately "dumb." Hand-tuning 30 weights to a backtest is
   overfitting (and likely why earlier complex models never beat LRExtrema). The
   principled place to learn weights is the ML layer, under walk-forward validation.

### Per stock, per rebalance you end up with

- 5 interpretable pillar scores
- 1 composite Fundamental Score (0–100)
- A veto flag (pass/fail) with reason
- All point-in-time, cross-sectionally normalized, regime-robust

---

## 4. The Handoff — Fundamentals Meet Technicals

Fundamentals tell you **what** to own. Technicals tell you **when** to buy it.

### Gate, then time

- **Fundamentals = the GATE (what's eligible).** Only stocks above a fundamental
  threshold (e.g., top 30%) enter the tradeable pool. Slow-moving; changes when quarterly
  results update. Answers: *does this deserve capital at all?*
- **Technicals = the TIMER (when to enter).** Among already-eligible stocks, technicals
  decide which to enter now and at what point. Fast-moving; reacts daily/intraday.
  Answers: *is now a good moment?*

A great chart on a fundamentally weak stock is rejected outright (never passes the gate).
A great fundamental stock simply waits for its technical moment.

### Multiplicative interaction (don't average)

For ranking *within* the eligible pool:

```
Final Signal ≈ Fundamental_Score × Technical_Score
```

Multiplication **punishes imbalance** — both must be strong, and if either collapses the
product collapses. An average would let one strong half hide a weak half. This encodes the
thesis: *justified (fundamental) AND moving cleanly (technical).*

### What "technical" means here (high level)

- **Trend confirmation** — the stock is genuinely in an uptrend, not falling.
- **Entry timing** — prefer a controlled pullback or clean breakout over chasing a
  vertical spike.
- **Multi-timeframe alignment** — higher timeframe sets context, lower timeframe triggers
  entry (the systematic version of the manual Brigade-style multi-timeframe read).

### Resulting flow

```
Whole Universe
   ↓  Fundamental Score + vetoes
Eligible Pool        — "what deserves capital"
   ↓  Technical trend + timing
Entry Candidates     — "deserving AND well-timed"
   ↓  Final multiplicative rank + position sizing
Actual Trades
```

One uniform pipeline, applied identically to every stock.

---

## 5. Exit Philosophy

> You entered for a reason (justified strength). You exit when that reason is gone — OR
> when the market tells you it's gone before the fundamentals catch up.

Positional horizon means **two independent clocks** run at once; exit when *either* rings.

### The two clocks

- **Clock 1 — Thesis break (slow, fundamental).** The reason you bought has broken:
  growth decelerates, margins compress, cash-flow quality deteriorates, or valuation runs
  to exhaustion. Leave even if the chart still looks fine — the chart is lagging
  information you already have.
- **Clock 2 — Price break (fast, technical).** The market votes against you before the
  next results confirm why: trend structure breaks (decisive lower-low / loss of governing
  -timeframe support), or breakdown on volume. Price often knows first.

Fundamentals are *right but slow*; price is *noisy but fast*. Run both. Fundamentals stop
you holding a permanently broken story; price stops you round-tripping a winner while
waiting for proof.

### The asymmetry principle

**Enter slowly and selectively. Exit decisively.** You were patient and demanding to get
in; on the way out, give the benefit of the doubt to protecting capital, not to hope.
Either clock ringing clearly = act. They need not agree.

### Riding winners — the trailing layer

Within a healthy position (both clocks fine), don't exit at a fixed target — **trail** and
let the winner run. Fixed targets cap exactly the big positional moves this strategy exists
to capture.

Exit stack, in priority:

1. **Thesis break** → exit (fundamental clock)
2. **Trend break** → exit (price clock)
3. **Neither broken** → trail, ride, do nothing ("do nothing" is an active, correct
   decision — the hardest one)

### The opportunity-cost exit (third, subtle clock)

Matters *because volume matters.* A position that's not broken but not moving — flat for
weeks, dead money — silently costs you the trades you could make with that capital. If a
thesis hasn't *begun* to play out within a reasonable window (weeks, scaled to this
horizon), **recycle the capital.** Not a loss-cut — a redeployment to keep turnover and
trade count alive. The positional analog of the existing intraday stale-exit.

### What this deliberately avoids

- **No fixed profit target** — caps winners, defeats the purpose.
- **No "it'll come back" holding** — that turns positional into involuntary investing.
- **No exit on noise alone** — one red day isn't a trend break; the governing timeframe
  defines "break."

### Summary

| Trigger                     | Clock            | Action          |
|-----------------------------|------------------|-----------------|
| Fundamentals deteriorate    | Slow / thesis    | Exit            |
| Valuation exhausted         | Slow / thesis    | Trim or exit    |
| Trend structure breaks      | Fast / price     | Exit            |
| Healthy but stalled too long| Opportunity      | Recycle capital |
| Everything intact           | —                | Trail & hold    |

---

## 6. Where ML Adds Value (and Where It Doesn't)

The hard truth first: earlier neural nets never beat LRExtrema. That's *information* —
financial data is low signal-to-noise, non-stationary, and tabular, which is the worst
environment for deep learning and a reasonable one for simpler models. A too-simple model
can't overfit; that's part of why LRExtrema is durable.

**Rule for FVM: ML earns its place only where it does something rules genuinely can't.
Everywhere else, stay rules-based.**

### Where ML does NOT help (keep rules-based)

- **The vetoes** — bright-line safety rules; never learnable / overridable.
- **The exit triggers** — thesis-break and trend-break must stay interpretable; you want
  to know *why* you sold.
- **The fundamental factor definitions** — PEG, growth acceleration, margin trend are
  accounting facts, not things to learn.

Keeping these rule-based preserves the interpretability that makes the system trustworthy
and debuggable.

### Where ML genuinely adds value

1. **Learning weights and interactions (the big one).** Hand-set weights can't express
   conditional structure like *"high growth only matters when valuation is below a sector
   threshold."* A **gradient-boosted tree (XGBoost / LightGBM)** finds such splits
   automatically — the "fuel left?" question as learnable structure. Trees are the home
   turf for tabular, noisy, mixed-type fundamental data: robust, data-efficient,
   overfitting-resistant, and inspectable (feature importance, SHAP). This is very likely
   why earlier neural nets lost — wrong tool for tabular financial data.
2. **Cross-sectional ranking (learning-to-rank).** Train the model to rank the universe
   by expected forward return; trade the top, rotate as ranks shift. Ranking is a more
   natural, achievable objective than predicting absolute returns — and it directly
   generates the desired trade volume across a broad universe.
3. **The "fuel-left" probability.** A focused classifier: *given this stock is up X% with
   fundamental profile P, what's the probability of a further meaningful leg up before a
   stop?* The "don't buy the tired 40% stock" thesis, learned from history rather than
   guessed.

### Non-negotiable discipline

- **Point-in-time data** — train only on what was known then; restatement leakage is the
  silent killer of fundamental ML.
- **Walk-forward, always** — retrain periodically, test strictly out-of-sample. Never a
  random split on time-series.
- **Label honestly** — define "good outcome" as forward return *net of* a realistic stop
  and slippage, the way you'd actually trade it.
- **Start simple; add capacity only if it earns out-of-sample.** The rules-based composite
  score is the **baseline to beat.** If ML can't beat it on walk-forward, ship the simple
  score. (Same standard LRExtrema set.)

### Honest framing

> ML here is not a magic alpha generator. It's a **weighting-and-interaction engine**
> on top of fundamentally sound, interpretable factors — and it ships only if it beats the
> dumb version out-of-sample. The factors carry the edge; ML only sharpens how they
> combine, and must prove it.

---

## 7. End-to-End Picture

1. **Fundamental factors** (5 pillars) → clean, point-in-time, normalized.
2. **Composite Fundamental Score + hard vetoes** → the *gate*.
3. **Technical layer** → trend confirmation + entry *timing*.
4. **Multiplicative combination** → final rank (both must be strong).
5. **ML** → learns factor weights/interactions and ranks the universe (*only if it beats
   the rules-based baseline*).
6. **Dual-clock exits** → thesis-break, price-break, opportunity-recycle, trail the rest.

A single uniform paradigm — **buy validated strength, ride it, exit when the reason or the
trend dies** — structurally uncorrelated to LRExtrema, built for a broad universe and high
trade count.

### How it sits next to LRExtrema

| Aspect          | LRExtrema                  | FVM                                   |
|-----------------|----------------------------|---------------------------------------|
| Horizon         | Intraday (15-min)          | Positional (days–months)              |
| Edge            | Mean reversion             | Validated momentum                    |
| Entry           | Buys weakness (dips)       | Buys justified strength               |
| Inputs          | Pure technical             | Fundamental + technical               |
| Trades          | Many, fast                 | Fewer, larger, longer; broad universe |
| Correlation     | —                          | Structurally uncorrelated to LRExtrema|

When mean-reversion regimes go quiet, validated-momentum can carry, and vice versa — the
second pillar of a multi-strategy book.

---

## 8. Next Steps (for build sessions)

- **Data sourcing & pipeline** — handled separately.
- **Define the labels first** — what counts as a "good trade" historically (forward return
  net of stop and slippage). This single decision shapes the entire ML layer downstream.
- Then: exact factor formulas + Indian-market thresholds → normalization/scoring
  implementation → fundamental→technical handoff → ML ranking → exit logic.
