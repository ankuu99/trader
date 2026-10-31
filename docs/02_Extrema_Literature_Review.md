# 02 — Trough/peak detection: literature review

Written 2026-10-18 · Literature track of the campaign in `docs/01_Extrema_Model_Campaign.md` (protocol, arms
EXP-01..EXP-10) · Starting point: `reviews/extrema_model_research_inventory_20261018.md` §4 (reading list, cited
from memory) · Prior evidence: `reviews/ather_minima_diagnosis_20260927.md`, `reviews/extrema_campaign/LEDGER.md`.

**Purpose.** (1) Check every citation on the inventory's reading list. (2) Pull out each source's mechanism with its
formulas. (3) Judge whether it transfers to long-only NSE mid/small caps on 15m / 4h / day bars. (4) Turn what
transfers into concrete campaign arms (existing EXP IDs, or EXP-11+).

**How it was verified.** Bibliographic data comes from Crossref (DOI, volume, issue, pages) plus publisher and
library pages. Mechanisms for Lo–Mamaysky–Wang, Avellaneda–Lee, Da–Liu–Schaumburg (NY Fed working-paper version),
Nagel (NBER working-paper version), Glattfelder et al. (arXiv) and Adams–MacKay (arXiv) were read from the full
text. The books (AFML, ML for Asset Managers, Chen & Tsang) and Chan (2003) were checked only at the level of their
tables of contents and abstracts. Anything marked *(recalled, unverified)* comes from memory and needs checking
before it is cited as fact. No page numbers or results have been made up. Where a number is quoted, it comes from
the text that was read.

**The constraint that frames everything (2026-10-18 headroom probe).** The probe scored predictors against the
campaign's "tradeable trough" truth (the bar reaches +profit_pct before our stale or stop exits fire). Production
P(min) has median AUC **0.511**. Single swing measures do no better: −depth50 0.534, −ret20 0.515, −RSI14 0.513.
**A single stock's own price path carries almost no information about whether a dip will pay under our exits.**
So this review gives most weight to sources that bring in *outside* information: market state (VIX, index
declines), *why* the price fell (news vs no news, fundamental vs non-fundamental), liquidity and volume
conditioning, and labels aligned with outcomes. Sources that only re-describe the own price path (kernel extrema,
directional change, changepoints) get low priority, however elegant they are.

---

## Summary table

| # | Source | Verified? | Core mechanism | Transfers to us? | Proposed arm / worktree |
|---|---|---|---|---|---|
| 1 | López de Prado, *AFML* (2018) ch 3/4/7 | ✔ (TOC level) | triple-barrier labels; meta-labelling; average-uniqueness weights; purged k-fold + embargo | **Yes**: the labelling and leakage machinery, not a new signal | EXP-01/02 already *are* triple-barrier labels with our exits as the barriers → **EXP-11** (uniqueness weights for dense labels) + protocol embargo |
| 2 | López de Prado, *ML for Asset Managers* (2020) ch 5 | ✔ (ch 5 = "Financial Labels"; trend-scanning *section number* unverified) | trend-scanning: label = sign of the max-\|t\| forward OLS slope | Weak: already built (`TrendScanningLabeler`), R-05 NULL | none (do not re-run) |
| 3 | Saito & Rehmsmeier (2015) | ✔ | PR beats ROC under class imbalance | Yes, for **evaluation** | protocol: add average precision (PR-AUC) next to AUC in Stage A |
| 4 | Niculescu-Mizil & Caruana (2005) | ✔ | boosted trees/SVMs give sigmoid-distorted probabilities; Platt / isotonic fix it | Only where thresholds are compared across models | none for Stage A (matched thresholds use ranks only); calibrate before any live gbdt |
| 5 | Chan (2003) | ✔ | big moves **without** public news reverse; bad-news moves drift | **Plausible**, and it is *outside* information | **EXP-15** news/no-news flag (W3) |
| 6 | Da, Liu & Schaumburg (2014) | ✔ | reversal = residual after removing industry momentum + cash-flow news; long-side profit = liquidity shocks | **Plausible**: residual vs index/sector is computable | **EXP-07** add residual returns; **EXP-13** residual s-score |
| 7 | Nagel (2012) | ✔ | reversal returns = liquidity-provision returns, strongly predicted by lagged VIX | **Plausible**: India VIX exists from 2008 (daily) | **EXP-12** stratification probe → **EXP-07** VIX features |
| 8 | Avellaneda & Lee (2010) | ✔ | OU fit to factor residuals; s-score; open at −1.25, close at −0.50; volume-scaled "trading time" | Yes, if run on the **residual**, not raw price | **EXP-10** → redefine as **EXP-13** (residual + trading-time) |
| 9 | Lo, Mamaysky & Wang (2000) | ✔ | kernel regression (0.3 × CV bandwidth) on 38-day windows; extrema = sign change of m̂′; pattern definitions | Weak: own-path; the evidence is about the shape of the return distribution, not profit | fold a "double-bottom" feature into **EXP-08** (W4), low priority |
| 10 | Glattfelder, Dupuis & Olsen (2011) | ✔ (journal year 2011, online 2010) | directional-change events at threshold δ; average overshoot ≈ δ; N(δ) power law | Weak: own-path; tick FX | **EXP-17** overshoot/δ feature (W2), low priority |
| 10b | Chen & Tsang (2020/21) | ✔ (authors **Jun Chen** & **Edward P. K. Tsang**) | DC summaries + HMM regime detection | Weak | none beyond EXP-17 |
| 11 | Adams & MacKay (2007) | ✔ (arXiv 0710.3742, a preprint, not a journal) | exact online run-length posterior | **Does not apply** to entry timing (it detects a change after it happens) | none |

Citation corrections are collected at the end of the per-source sections.

---

## 1. López de Prado — *Advances in Financial Machine Learning* (2018), ch 3, 4, 7

**Citation (verified).** Marcos López de Prado, *Advances in Financial Machine Learning*, John Wiley & Sons,
Hoboken NJ, 2018. ISBN 978-1-119-48208-6 (hardcover), 978-1-119-48211-6 (e-book). Chapter titles were checked
against retailer and library tables of contents: **ch 3 "Labeling"** (fixed-horizon method, dynamic thresholds,
triple-barrier method, meta-labeling, dropping unnecessary labels), **ch 4 "Sample Weights"** (overlapping outcomes,
concurrent labels, average uniqueness, sequential bootstrap, return attribution, time decay, class weights),
**ch 7 "Cross-Validation in Finance"** (purged k-fold, purging, embargo). The inventory's chapter mapping is
**correct**.

**Mechanism.**
- *Triple barrier (ch 3).* For an event at t₀ with entry price p₀ there are three barriers: an upper barrier
  p₀(1 + π·σ_t₀), a lower barrier p₀(1 − ς·σ_t₀), and a vertical barrier at t₀ + h. σ is a volatility target
  known at t₀ (in the book, an exponentially weighted std of daily returns; *the span value is recalled,
  unverified*). Label = +1 or −1 for whichever horizontal barrier is touched first. At the vertical barrier the
  label is the sign of the return (or 0).
- *Meta-labelling (ch 3).* A primary model picks the side. A secondary binary model learns whether to act on the
  primary's signals, and its probability sizes the bet.
- *Uniqueness (ch 4).* Label i spans [t_i,0, t_i,1]. Concurrency c_t = Σ_i 1{t ∈ [t_i,0, t_i,1]}. Uniqueness at
  t: u_t,i = 1{t ∈ span_i}/c_t. Average uniqueness ū_i = mean of u_t,i over span_i. The sample weight is ∝ ū_i (or
  ∝ |Σ_t r_t/c_t| for return attribution). The sequential bootstrap draws samples with probability ∝ their
  uniqueness given the samples already drawn.
- *Purging and embargo (ch 7).* Drop from the training fold every observation whose label span overlaps any
  test-fold label span (purge). Then also drop a band of observations right after each test fold (embargo).
  *A width of ≈1 % of T is commonly quoted; recalled, unverified.*

**Evidence.** A methods text. Its claims are about leakage and estimator variance, backed by argument and
synthetic examples, not by a market study. It applies at any frequency.

**Applies to us.**
- EXP-01/02 (`labels.type: tradeable`) **is** a triple-barrier label, with a better barrier set than the
  generic one: our actual exit stack (hard stop, stale tier-1 + re-arm, stale_2, hold_bars) instead of a symmetric
  σ-band. Keep it that way. AFML's σ-scaled barriers are the wrong target here because the exits are what we
  trade.
- **Overlap is severe for EXP-02.** Dense candidates with a forward horizon of up to hold_bars (200 bars at 15m)
  mean each label overlaps up to ~200 neighbours. Unweighted, the logistic fit is dominated by long clustered runs
  of near-identical labels (a slow 4 % grind gives ~50 consecutive "good" bars). → **EXP-11**: average-uniqueness
  sample weights. This needs `sample_weight` passed through `ExtremaModel.fit`. Both logistic and gbdt accept it
  in sklearn; the interface does not pass it today.
- **Purging inside walk-forward training.** A tradeable label is resolved only after its exit fires. At retrain
  time, candidates in the last ≤ hold_bars bars are unresolved and must be **dropped** (they are not negatives).
  `triple_barrier_label` already returns None past the end of the data, and the EXP-01 guide must carry the same
  guard. Cost: at 15m the most recent ~200 bars of a 1200-bar window never train, so the model is a little stale.
  At day TF hold is 40 bars, so the cost is small.
- **Embargo in Stage A.** The calibration window (2023–24) and the test window (2025→) are fixed. Thresholds are
  calibrated on firings whose truth may be resolved by bars inside 2025. That is a minor leak and only
  conservative, but the protocol should say that calibration-window truth is computed only from bars before
  2025-01-01, i.e. an embargo of hold_bars before the cut.
- **Meta-labelling is already FALSIFIED here (R-25).** Do not re-propose it.

## 2. López de Prado — *Machine Learning for Asset Managers* (2020), ch 5

**Citation (verified).** M. M. López de Prado, *Machine Learning for Asset Managers*, Cambridge University Press,
Elements in Quantitative Finance, 2020 (online 4 Apr 2020). DOI 10.1017/9781108883658, ISBN 978-1-108-79289-9.
The publisher's TOC lists **ch 5 "Financial Labels"** from p. 65. Trend-scanning is presented in this book
(library docs confirm it). That it sits in ch 5, and under which section number, is **unverified** but very likely
given the chapter title.

**Mechanism.** For each t and each horizon L in a set 𝓛, fit p_{t+l} = β₀ + β₁·l + ε for l = 0..L and compute
t̂(β₁). Pick L* = argmax_L |t̂(β₁)|. Label = sign(t̂_L*), with |t̂| as sample weight or confidence. A |t| floor
gives a {−1, 0, +1} label.

**Evidence.** Methodological, illustrated on synthetic series.

**Applies to us — does not, as a new arm.** It is already built (`trader/features/labels.py::TrendScanningLabeler`,
`labels.type: trend_scan`) and is ledger R-05: NULL for point detection. It labels every bar of a trend (≈12k
samples), so the model learns regime, not turning point. The same structural problem falsified avg_trend (R-07):
a forward-trend label flips only once the trend is under way. One reusable idea: |t̂| as a sample weight. EXP-11's
uniqueness weights address the same overweighting problem more directly. No arm.

## 3. Saito & Rehmsmeier (2015)

**Citation (verified).** T. Saito, M. Rehmsmeier, "The Precision-Recall Plot Is More Informative than the ROC Plot
When Evaluating Binary Classifiers on Imbalanced Datasets", *PLOS ONE* 10(3): e0118432, 4 Mar 2015.
DOI 10.1371/journal.pone.0118432.

**Mechanism.** On imbalanced data ROC curves look reassuring because the FPR denominator (all negatives) is huge.
Precision TP/(TP+FP) shows directly what fraction of firings are right. The paper argues PR curves (and their area)
are the more informative summary when positives are rare. It also flags that interpolating between PR points
needs care.

**Evidence.** Simulations plus a re-analysis of bioinformatics classifier literature. It is a methods paper with no
finance content, and the argument is general.

**Applies to us — evaluation, not an arm.** Stage A gates on ROC-AUC over *all bars*, plus precision and EV at the
matched threshold. We only trade the top ~1–3 % of bars, so ROC-AUC mostly measures ranking in the bulk we never
fire on. **Protocol suggestion:** report average precision (PR-AUC) and precision@k at the matched firing budget
next to AUC. Treat the gate's EV@matched branch as the one that matters, since it is already a top-of-ranking
metric. Changing the gate itself needs a DECISIONS row *before* any arm runs (campaign rule).

## 4. Niculescu-Mizil & Caruana (2005)

**Citation (verified).** A. Niculescu-Mizil, R. Caruana, "Predicting good probabilities with supervised learning",
*Proc. 22nd ICML* (ICML '05), pp. 625–632. DOI 10.1145/1102351.1102430.

**Mechanism.** Max-margin methods (boosted trees and stumps, SVMs) push predicted probabilities away from 0 and 1,
giving a sigmoid-shaped reliability curve. Naive Bayes pushes them toward 0 and 1. Neural nets, bagged trees and
logistic regression are roughly calibrated. Fixes: Platt scaling (fit a 1-D logistic on held-out scores) or
isotonic regression (non-parametric and monotone, needs more data). After calibration, boosted trees, random forests
and SVMs give the best probabilities.

**Evidence.** Eight UCI-type binary problems. General ML, no finance.

**Applies to us — narrow.** The Stage-A matched threshold is rank-based (a per-stock firing count), so calibration
cannot change any Stage-A or Stage-B result. It matters in two places only: (a) any **live** deployment of a gbdt
arm, where the global 0.90 / sell 0.85 / veto thresholds assume logistic scale (inventory §1, coupling 1). Isotonic
on a held-out tail of each retrain window would let the existing thresholds carry over. (b) Any future arm that
sizes positions by P(win) (the meta filter's `max_fraction`). No arm.

## 5. Chan (2003) — news vs no-news

**Citation (verified).** Wesley S. Chan, "Stock price reaction to news and no-news: drift and reversal after
headlines", *Journal of Financial Economics* 70(2), 223–260, Nov 2003. DOI 10.1016/S0304-405X(03)00146-6
(SSRN working paper 10.2139/ssrn.262452, 2001).

**Mechanism (abstract level; full text not read).** Monthly returns of stocks with public headline news are
compared with stocks that had similar returns and no identifiable news. Stocks with news show **drift**, strongest
after bad news (investors are slow to react). Stocks with extreme moves and **no** news show **reversal** in the
following month. The patterns survive risk adjustment and are **concentrated in smaller, less liquid stocks**. The
size of the reversal is not quoted here because it was not verified.

**Evidence.** US monthly data. The horizon (one month) is longer than our 15m holds but similar to day-TF holds
(hold_bars 40 days).

**Transfer.** This is the most direct published answer to "which dips bounce", and the information it uses
(was there news?) is **not in the price path**. That is exactly what the headroom probe says we lack. The
small/illiquid concentration matches our universe. Risks: Indian corporate-announcement data is noisy (many filings
are routine), and the monthly→15m step is untested. It transfers best to day/4h-TF names.

**Arm — EXP-15 (W3 market/context, new).** Tag each candidate bar with "price-relevant corporate event within the
decline window": quarterly result date, board meeting, rating action, block/bulk deal. Sources: NSE corporate
announcements / financial-results calendar, or Trendlyne result dates, which the repo already ingests for FVM. Run
it **as a stratification first** (no model change): the tradeable-trough base rate and EV for event-declines vs
no-event declines, per stock TF. If no-news declines pay clearly more, it becomes a feature (`features.news.enabled`)
or an entry mask. **Data-availability check comes first.** The historical announcement timestamps must be
point-in-time (no restated dates).

## 6. Da, Liu & Schaumburg (2014) — decomposing the reversal

**Citation (verified).** Zhi Da, Qianqiu Liu, Ernst Schaumburg, "A Closer Look at the Short-Term Return Reversal",
*Management Science* 60(3), 658–674, Mar 2014. DOI 10.1287/mnsc.2013.1766. Working paper: "Decomposing Short-Term
Return Reversal", FRB New York Staff Report 513, Sep 2011 (read in full).

**Mechanism.** Analytically, the profit of the standard monthly reversal strategy (buy the prior-month losing
decile, sell the winning decile) splits into four parts: (1) across-industry return momentum, which works
*against* reversal; (2) within-industry variation in expected returns; (3) under-reaction to within-industry
cash-flow news, measured by analyst forecast revisions (I/B/E/S), which also works against it; (4) a residual
("discount-rate" or non-fundamental news). **Only the residual is significantly positive.** Working-paper numbers,
1982–2009: the standard reversal 3-factor alpha is 0.33 %/month (t 1.37). A within-industry reversal earns 1.20 %/mo
raw (0.92 % alpha). The residual-based within-industry strategy earns 1.57 %/mo raw and 1.34 % 3-factor alpha
(t 9.28). A simple 3×3 within-industry double sort on prior return and earnings-forecast revision earns 1.72 % alpha.
The published abstract says "four times" the standard strategy; the working paper says three. The long side (losers)
loads on lagged aggregate Amihud illiquidity and S&P realised volatility, i.e. it is **compensation for providing
liquidity**. The short side is sentiment.

**Evidence.** US monthly, analyst-covered stocks. Robust to midquote returns (not bid-ask bounce) and present even
among large liquid stocks.

**Transfer.** The two portable pieces are *industry/market adjustment* and *the long side is a liquidity
premium*. Analyst revisions are not available intraday for NSE mid/small caps, and coverage is thin. "Price fell but
the fundamental outlook did not" can be approximated by price-falls-without-news (EXP-15) and by the residual
versus the sector/market. Removing the index component is computable today: Nifty 50 is in the cache, and sector
indices would need fetching.

**Arm.** Extend **EXP-07** with residual returns: r_stock − β·r_Nifty over 5/20 bars (β from a rolling 60-bar OLS),
plus sector-index residuals if sector data is fetched. This feeds **EXP-13** below. Hypothesis: a dip that is mostly
market (index down too) or mostly residual behaves differently from one that is mostly own price. Da et al. predict
the residual part reverses, and Nagel/Hameed (below) predict market-wide declines pay liquidity providers more.
Both are outside-the-own-path information.

## 7. Nagel (2012) — evaporating liquidity

**Citation (verified).** Stefan Nagel, "Evaporating Liquidity", *Review of Financial Studies* 25(7), 2005–2039,
2012. DOI 10.1093/rfs/hhs066 (NBER WP 17653, Dec 2011; read in full).

**Mechanism.** Short-term reversal returns are read as returns to liquidity provision. Strategy (Lehmann 1990):
weight w_it = −(R_i,t−1 − R_m,t−1) / (½ Σ_i |R_i,t−1 − R_m,t−1|), which is $1 long / $1 short. The daily strategy
averages five sub-strategies conditioned on days t−1…t−5. Predictive regression: L_t = a + b·VIX_{t−5} + c′g_{t−5}
+ e_t, with VIX normalised to daily vol (÷√250). Result: b = 0.22 (s.e. 0.02). One point of daily-normalised VIX
(≈ 16 annualised points) adds ≈ 0.22 pp to the strategy's *daily* return, adj. R² 0.07 (very high for a daily
predictive regression). Quote-midpoint returns give about ⅔ of the coefficient. Industry-portfolio reversals, which
earn little unconditionally, earn high Sharpe ratios when VIX is high. Interpretation: constrained intermediaries
withdraw in turmoil, so the premium for providing liquidity jumps.

**Evidence.** US daily (CRSP NYSE/AMEX/Nasdaq), roughly 1998–2010, strong. These are cross-sectional, market-neutral
returns, not long-only.

**Transfer.** The mechanism (buying dips is supplying liquidity, and it pays most when liquidity is scarce) fits a
long-only dip buyer. It is consistent with our own **R-35** finding that "knife-state entries are the BEST
bucket". India VIX is published daily by NSE from 2008. The campaign notes say only 2023-11→ of *15m* VIX is
cached, but a **daily** previous-close VIX feature avoids the backfill entirely and is look-ahead-safe. Caveats:
our book is long-only and un-hedged, so high VIX also means the market leg hurts, and Nagel's numbers are
market-neutral. The effect may show up as larger bounces *and* larger stop-outs.

**Arms.**
- **EXP-12 (W3, new, cheap, run first):** a market-state stratification of the Stage-A truth, with no model and no
  config. On the existing Stage-A truth table, compute the tradeable-trough base rate and mean EV by tercile of
  (a) India VIX previous close, (b) 5-day VIX change, (c) Nifty drawdown from its 20-/60-day high, per stock and
  pooled. This directly measures how much headroom W3 has.
- **EXP-07 (refined):** the features are daily India VIX (level, z-score vs its 1-year mean, 5-day change), Nifty
  drawdown from the 20/60-day high, Nifty 5/20-day return, and the stock's residual return (§6). Use previous-day
  values only for intraday TFs.

## 8. Avellaneda & Lee (2010) — OU s-score

**Citation (verified).** Marco Avellaneda, Jeong-Hyun Lee, "Statistical arbitrage in the U.S. equities market",
*Quantitative Finance* 10(7), 761–782, 2010. DOI 10.1080/14697680903124632 (SSRN 2008). Read: the NYU working-paper
PDF (2008 draft). Thresholds and formulas below are from that draft, and the published version may differ slightly.

**Mechanism.**
- Regress stock returns on factors (sector ETF, or 15 PCA factors): R_i = β_i·F + dX_i. The cumulative residual X_i
  is modelled as Ornstein–Uhlenbeck: dX_i = κ_i(m_i − X_i)dt + σ_i dW_i.
- Estimate on a **60-day** window via the AR(1) X_{n+1} = a + bX_n + ζ: κ = −ln(b)·252, m = a/(1−b),
  σ_eq = √(Var(ζ)/(1−b²)). Keep the stock only if mean reversion is fast: κ > 252/30 (τ < ~1.5 months,
  0 < b < 0.9672). Median τ in 2007 was 7.5 days.
- s-score s_i = (X_i − m_i)/σ_eq,i, with m centred by subtracting the cross-sectional mean of a/(1−b).
- Rules: **buy to open s < −1.25**, **close long s > −0.50**, sell to open s > +1.25, close short s < +0.75. The
  cut-offs were chosen empirically on 2000–2004.
- **Trading-time variant (§6):** replace returns with R̃_t = R_t·⟨δV⟩/(V_{t+Δt} − V_t), i.e. scale each return by
  typical/actual volume. A drop on **high** volume shrinks, so "buying stocks that drop on high volume is
  discouraged". This improved the ETF-factor strategies unequivocally and made no significant difference for PCA.
- Results: PCA strategies Sharpe 1.44 net of 10 bp round trip over 1997–2007, but 0.9 over 2003–07. ETF strategies
  1.1 over 1997–2007, and 1.51 with trading time over 2003–07.

**Evidence.** US daily, large liquid universe, market-neutral with hedging. Performance decayed after 2003.

**Transfer.** The useful parts are the *residualisation* and the *volume-scaled return*. EXP-10 as currently sketched
(OU s-score on the stock's own price) is an own-path statistic, the family the headroom probe says is near chance
(−RSI14 0.513 is essentially an s-score). Our book is unhedged, so the residual is a *signal* definition; the
position still carries the market. Fast-κ screening is a useful extra filter: stocks or windows with τ beyond the
holding horizon have no mean reversion to harvest.

**Arm — EXP-10 → EXP-13 (W5, redefine).** s-score of the **residual vs Nifty** (sector index if available) per
strategy TF. Estimation window = 60 bars of that TF, κ filter as in the paper (τ ≤ half the window). Two variants:
calendar-time and trading-time (A&L eq. 20, volume-scaled). Use as (i) a rule model: enter at s < −1.25 with the
usual exit stack; A&L's own exit at s > −0.5 would be a new exit, so out of scope for this entry campaign; (ii)
features [s, κ-pass flag]. Keep the raw-price s-score as the control: if residual ≈ raw at Stage A, the W3 premise
fails here too.

## 9. Lo, Mamaysky & Wang (2000) — kernel-smoothed extrema

**Citation (verified).** Andrew W. Lo, Harry Mamaysky, Jiang Wang, "Foundations of Technical Analysis: Computational
Algorithms, Statistical Inference, and Empirical Implementation", *Journal of Finance* 55(4), 1705–1765, Aug 2000.
DOI 10.1111/0022-1082.00265 (NBER WP 7613). Read in full.

**Mechanism.**
- Nadaraya–Watson kernel regression with a Gaussian kernel, on **rolling windows of l + d = 38 trading days
  (l = 35, d = 3)**: m̂_h(τ) = Σ K_h(τ−s)P_s / Σ K_h(τ−s).
- **Bandwidth h = 0.3 × h\***, where h\* minimises the leave-one-out CV function. The CV bandwidth was "too smooth"
  according to the professional technical analysts they polled. The authors call 0.3 "ad hoc" and fixed it before
  running any statistics.
- **Extrema:** find τ where Sgn(m̂′(τ)) = −Sgn(m̂′(τ+1)), then take the max/min of the *actual* prices in
  [τ−1, τ+1]. Patterns are defined on five consecutive extrema.
- **Double bottom:** an initial minimum E₁, then the lowest later minimum E_b, within **1.5 %** of their average and
  **> 22 trading days** apart. Triangles, rectangles, broadening and (inverse) head-and-shoulders are defined
  similarly.
- **Detection lag d = 3:** the pattern must complete by day t+l−1, and returns are measured from t+l+d. This is how
  they keep the conditional returns out-of-sample.
- **Test:** compare conditional vs unconditional distributions of normalised one-day returns 3 days after
  completion (χ² goodness-of-fit, Kolmogorov–Smirnov).

**Evidence.** US daily 1962–96, 350 stocks per exchange sample. Several patterns (more on Nasdaq) shift the return
distribution ("incremental information"). This is evidence about **distribution shape, not trading profit**.

**Transfer — weak.** Smoothed extrema are own-path geometry, the family the headroom probe flags. The
detection-lag design is the same issue that sank avg_trend (R-07): a smoothed-curve extremum is known only d bars
later. The one possibly additive idea is **structural**: a test of a prior swing low (double bottom), which carries
memory of an earlier level and is not captured by depth/RSI.

**Arm — fold into EXP-08 (W4).** Add `dbl_bottom_dist` = (close − nearest prior smoothed minimum) / that minimum,
for prior minima ≥ 22 bars back (scaled to TF) within the window, plus a flag for |dist| ≤ 1.5 %. Kernel at
0.3 × h\*_CV, computed causally on the trailing window only (the last ~d bars are boundary-biased, a known kernel
problem). Low priority. Run only if EXP-08 shows W4 has any headroom.

## 10. Directional change — Glattfelder, Dupuis & Olsen (2011); Chen & Tsang (2020)

**Citations (verified).**
- J. B. Glattfelder, A. Dupuis, R. B. Olsen, "Patterns in high-frequency FX data: discovery of 12 empirical scaling
  laws", *Quantitative Finance* 11(4), 599–614, 2011 (issue Apr 2011; online 2010, so RePEc lists 2010).
  DOI 10.1080/14697688.2010.481632. arXiv 0809.1040 (read).
- Jun Chen, Edward P. K. Tsang, *Detecting Regime Change in Computational Finance: Data Science, Machine Learning
  and Algorithmic Trading*, CRC Press (Chapman & Hall), 2020. Some catalogues give ©2021. ISBN 978-0-367-53628-2
  (hb), 978-0-367-54095-1 (pb), e-book 978-1-003-08759-5.

**Mechanism.** Directional change (DC) samples the series in "intrinsic time". Track the running extreme. A DC event
is confirmed when price retraces δ (relative) from that extreme, and then the mode flips. The **overshoot** (OS) is
the move from the DC confirmation point to the next extreme. Glattfelder et al. report, for 13 FX pairs on
2002-12 → 2007-12 ticks, that the **average OS ≈ δ** (exponent ≈ 1.04, prefactor ≈ 1.06), so the average total move
≈ 2δ. OS takes about twice the ticks and the time of the DC section. The number of DCs follows the power law
N(δ) = (δ/C)^E with E ≈ −2 (originally Guillaume et al. 1997). Chen & Tsang summarise each trend with DC indicators
and fit an HMM to separate normal from abnormal regimes. *The exact indicator definitions (e.g. "TMV", "R") are
recalled and unverified.*

**Evidence.** Tick FX, high quality for the averages. These are *average* laws, and individual overshoots are very
dispersed. Transfer to NSE equities on 15m+ bars has not been verified.

**Transfer — weak.** DC with vol-scaled δ is essentially our zigzag labeller (R-04, PARTIAL). As a feature, "current
downward overshoot in units of δ" is again own-path. The OS ≈ δ law offers a prior for *how far a decline continues
after confirmation*, which is relevant to entering too early (our firings lead the dip by a median of 2 bars).

**Arm — EXP-17 (W2, low priority).** Features: os_ratio = (DC-confirm price − current price)/(δ·confirm price) in
the current down-mode, and bars since the DC confirmation. δ = k·σ (the zigzag vol-scaled recipe, k = 2). Run only
if W2 shows any Stage-A headroom.

## 11. Adams & MacKay (2007) — Bayesian online changepoint detection

**Citation (verified).** Ryan P. Adams, David J. C. MacKay, "Bayesian Online Changepoint Detection",
**arXiv:0710.3742** [stat.ML], Oct 2007, a technical-report preprint (no journal version). Read in full.

**Mechanism.** Posterior over the run length r_t (time since the last change). Hazard H(τ) = P_gap(τ)/Σ_{t≥τ}P_gap(t),
constant 1/λ for a geometric prior. Growth: P(r_t = r_{t−1}+1, x_{1:t}) = P(r_{t−1}, x_{1:t−1})·π_t·(1−H).
Changepoint: P(r_t = 0, x_{1:t}) = Σ P(r_{t−1}, x_{1:t−1})·π_t·H. Conjugate exponential-family updates per run.
O(t) per step, and pruning makes it roughly constant. Demos: well-log data, DJIA daily returns 1972–75 (variance
regime), coal-mine disasters.

**Evidence.** Illustrative only. The paper does not measure detection lag.

**Applies to us — does not.** A change in a dip's mean or variance is confirmed only after several post-change bars,
which is the after-the-fact lag the inventory already flagged. The only conceivable use is market-level context
(run length since the last Nifty volatility-regime change), and EXP-07's VIX features cover that more directly. No arm.

### Citation corrections (vs the inventory's §4)

1. **Chen & Tsang:** the authors are **Jun Chen and Edward P. K. Tsang**. The full title is *Detecting Regime Change
   in Computational Finance: Data Science, Machine Learning and Algorithmic Trading* (CRC Press, 2020; some catalogues
   ©2021). The inventory's short form is otherwise fine.
2. **Glattfelder, Dupuis & Olsen:** *Quantitative Finance* **11(4):599–614, 2011**, DOI 10.1080/14697688.2010.481632.
   The inventory's "2011" is right; RePEc's "2010" is the online date. The inventory omitted the title: "Patterns in
   high-frequency FX data: discovery of 12 empirical scaling laws".
3. **Adams & MacKay (2007)** is an arXiv preprint (0710.3742), not a journal or conference paper.
4. **Da, Liu & Schaumburg:** the working-paper title differs ("Decomposing Short-Term Return Reversal", FRBNY SR 513,
   2011), and its "three times" became "four times" in the published version.
5. **Avellaneda & Lee:** the journal year 2010 is correct, and the widely cited 2008 date is the SSRN draft.
6. **MLAM:** "ch 5" is correct as "Financial Labels". Whether trend-scanning is a numbered section of ch 5 is
   unverified.

All other §4 entries (AFML ch 3/4/7, Saito & Rehmsmeier, Niculescu-Mizil & Caruana, Chan, Nagel, Lo–Mamaysky–Wang)
are correct as cited.

---

## Additional sources (verified to exist; post-2015 unless marked)

**A1. Tatbul, Lee, Zdonik, Alam, Gottschlich (2018), "Precision and Recall for Time Series", NeurIPS 2018 (Advances
in NeurIPS 31); arXiv 1803.03639.** Range-based precision and recall: each predicted or real range is scored by an
existence reward α plus an overlap reward with tunable size, position bias (front/back/flat) and cardinality
penalties. It reduces to classical P/R for unit ranges. *Use:* our "event recall within [−5, +10] bars" is an ad-hoc
instance of this. Score a dip as a *range* (decline-low → first +profit_pct bar) with a **front-biased** position
function, since an early fire inside the range is worth more than a late one. That gives a principled timing-aware
recall for Stage A. It is a protocol refinement, not an arm.

**A2. Truong, Oudre, Vayatis (2020), "Selective review of offline change point detection methods", *Signal
Processing* 167:107299. DOI 10.1016/j.sigpro.2019.107299.** Defines margin-based precision, recall and F1: a true
event counts as detected if an estimate lies within M samples. P and R are well-defined only when M is smaller than
the minimum spacing between true events. *Use:* our ±3 / [−5, +10] tolerance windows must stay below the minimum
dip spacing per TF, or recall double-counts. Add an assertion in `stage_a.py`.

**A3. Cheng, Hameed, Subrahmanyam, Titman (2017), "Short-Term Reversals: The Effects of Past Returns and
Institutional Exits", *JFQA* 52(1), 143–173. DOI 10.1017/S0022109016000958.** Monthly reversals are stronger after
prior-quarter declines, and their size varies with the participation of active institutional liquidity providers,
who stay out of past losers (abstract level). *Use:* supports EXP-12/EXP-07 (prior decline × liquidity state). A
possible NSE proxy is FII/DII net flows (daily, NSE/NSDL) or the stock's delivery-% drop. Data availability is
unverified.

**A4. Medhat & Schmeling (2022), "Short-term Momentum", *Review of Financial Studies* 35(3), 1480–1526.
DOI 10.1093/rfs/hhab055.** Sorting on prior-month return × share turnover: **low-turnover losers reverse;
high-turnover stocks show short-term momentum (continuation)**. Strongest among large, liquid, well-covered stocks.
US 1963–2018, extended to 23 developed markets (secondary source). *Use:* together with A&L's trading-time result,
this argues *against* the "volume-climax capitulation" heuristic. A decline on unusually high turnover is more
likely informed and keeps going. Our volume_ratio feature (AUC 0.61 vs hand dips) has an unknown sign against
tradeable truth. → **EXP-14**.

**A5. Jegadeesh, Luo, Subrahmanyam, Titman (2025), "Short-Term Reversals and Longer-Term Momentum around the World:
Theory and Evidence", *Review of Financial Studies* 38(12), 3673–3728. DOI 10.1093/rfs/hhaf057.** Model with short-
and long-horizon noise traders. It predicts **attenuated reversals after earnings announcements** (consistent with
Chan's news/no-news split) and larger reversals with more noise trading, confirmed on US + international data (49
countries per a secondary summary; whether India is included was **not** verified). *Use:* supports EXP-15
(result-date flag).

**A6. Wu, Wang, Su, Tang, Wu (2020), "A Labeling Method for Financial Time Series Prediction Based on Trends",
*Entropy* 22(10):1162. DOI 10.3390/e22101162.** "Continuous trend labelling": label whole up/down legs found by a
retracement threshold, instead of comparing with a fixed future point. Shanghai Composite only, low-to-mid venue.
*Use:* none. It is a DC/zigzag relative (R-04) and has the same dense-regime-label problem as avg_trend (R-07). It is
listed to show that the ML-labelling literature has not moved past own-path definitions.

**Context (pre-2015, verified, abstract-level):**
- Hameed, Kang, Viswanathan (2010), "Stock Market Declines and Liquidity", *J. Finance* 65(1), 257–293,
  DOI 10.1111/j.1540-6261.2009.01529.x. After market declines liquidity dries up and the returns to providing it
  (reversals) rise. Nagel's VIX result is the same story; Nagel's regression controls for its lagged-market-return
  effect.
- Avramov, Chordia, Goyal (2006), "Liquidity and Autocorrelations in Individual Stock Returns", *J. Finance* 61(5),
  2365–2394, DOI 10.1111/j.1540-6261.2006.01060.x. Short-horizon reversals concentrate in illiquid stocks
  (*recalled: specifically high-turnover, illiquid ones; unverified*).
- Gervais, Kaniel, Mingelgrin (2001), "The High-Volume Return Premium", *J. Finance* 56(3), 877–919,
  DOI 10.1111/0022-1082.00349. Unusually high volume predicts higher subsequent returns (visibility). This pulls in
  the opposite direction from A4, so the sign of volume conditioning must be measured, not assumed.
- Sezer & Ozbayoglu (2018), "Algorithmic financial trading with deep convolutional neural networks: Time series to
  image conversion approach", *Applied Soft Computing* 70, 525–538, DOI 10.1016/j.asoc.2018.04.024. Labels Buy/Sell/Hold
  from the "hills and valleys" of a sliding window. That is the field's default label, and it is our R-01 problem.
  *Exact window rule not verified.*

**India-specific evidence is thin.** The only verified short-horizon NSE study found is Tripathi & Aggarwal (2015),
"Prior Return Effect in Indian Stock Market: An Intra-day Analysis", *International Journal of Financial Management*
(Publishing India). It reports reversal within minutes of extreme intraday moves, with asymmetric speed (faster
recovery after unjustified falls). The venue is low-tier, only the abstract was read, and the method and sample are
unverified. Indian monthly studies (e.g. Dhankar & Maheshwari, NSE 1997–2013) find short-term *momentum* and
long-term reversal. Net: there is **no reliable published evidence on daily or weekly dip-buying on NSE mid/small
caps**. Our own backtests are the only evidence for this universe, and the US mechanisms above are hypotheses to
test, not priors to trust.

---

## Arms proposed to the campaign ledger

Ordered by expected value of information given the headroom probe (outside information first; cheap probes before
builds). "Stage A gate" = the protocol's gate in `docs/01_Extrema_Model_Campaign.md`.

1. **EXP-12 — market-state stratification probe** (W3; no model, no config). *Hypothesis (Nagel 2012; Hameed et al.
   2010; Cheng et al. 2017):* the tradeable-trough base rate and EV are materially higher when India VIX is high or
   rising and when Nifty is in a drawdown. *Change:* a script over the existing Stage-A truth table, joined to daily
   India VIX (previous close) and Nifty 20/60-day drawdown and 5-day return. Report base rate and mean EV by tercile,
   per stock and pooled, on the calibration window only. *Falsified if:* top-vs-bottom tercile base rate differs by
   < 20 % relative *and* EV by < 0.25 pp pooled, with no consistent sign on ≥ ⅔ of stocks. Then deprioritise EXP-07.
2. **EXP-07 (refined) — market + residual features** (W3). *Hypothesis:* adding market state and the stock's
   residual-vs-Nifty return lets the model separate dips that pay from dips that don't, which own-path features
   cannot (AUC ≈ 0.51). *Change:* `features.market: {enabled, vix: [level, z250, chg5], nifty: [dd20, dd60, ret5,
   ret20], residual: {beta_window: 60, horizons: [5, 20]}}`. Daily values lagged one session for intraday TFs, so no
   15m VIX backfill is needed. *Falsified if:* Stage A gate fails (median ΔAUC < +0.03 and median ΔEV@matched
   < +0.25 pp).
3. **EXP-15 — news/no-news decline flag** (W3; stratify first). *Hypothesis (Chan 2003; Jegadeesh et al. 2025;
   Da et al. 2014):* declines with no price-relevant corporate event reverse, and event declines drift. *Change:*
   point-in-time event table (result dates, board meetings, rating actions, bulk/block deals). Step 1 stratifies the
   Stage-A truth by "event within the decline window". Step 2 (if it passes) adds `features.news: {enabled,
   window_bars}`. *Falsified if:* the no-event vs event base-rate/EV difference is < 0.25 pp EV pooled, or not the
   same sign on ≥ ⅔ of stocks. *Blocker:* historical point-in-time event data must be confirmed available first.
4. **EXP-11 — dense tradeable labels with average-uniqueness weights** (W1; modifies EXP-02). *Hypothesis (AFML
   ch 4):* dense outcome labels with a horizon of up to hold_bars overlap heavily, and unweighted fitting
   overweights long runs of near-duplicate samples. Uniqueness weighting improves ranking. *Change:* EXP-02 plus
   `labels.tradeable.sample_weight: uniqueness` (ū_i over each label's [t, exit_bar] span). `ExtremaModel.fit`
   gains a `sample_weight` passthrough. Unresolved labels (exit beyond the retrain point) are dropped, not
   negatives. *Falsified if:* not better than unweighted EXP-02 on the Stage A metrics (ΔAUC or ΔEV@matched ≤ 0
   median).
5. **EXP-13 — residual OU s-score (redefines EXP-10)** (W5). *Hypothesis (Avellaneda & Lee 2010; Da et al. 2014):*
   mean reversion is in the market-residual, not the raw price. A residual s-score ranks tradeable troughs better
   than the raw-price s-score, which per the probe should be ≈ RSI ≈ chance. *Change:* `features.ou: {enabled,
   factor: nifty, window: 60, kappa_min: "tau<=window/2", trading_time: false|true}` and `model.type: rules` with
   `ou.entry_s: -1.25`. Raw-price s-score as the control arm. *Falsified if:* the residual variant fails the Stage A
   gate vs baseline, or does not beat the raw-price control by ≥ 0.02 median AUC.
6. **EXP-14 — volume/turnover-conditioned decline** (W2/W3; stratify first). *Hypothesis (Medhat & Schmeling 2022;
   A&L trading time; opposite prior from Gervais et al. 2001):* the sign of volume's effect on whether a dip pays
   is the opposite of the capitulation heuristic. Low-volume declines pay, high-volume declines continue. *Change:*
   step 1 stratifies the Stage-A truth by decline-window volume_ratio tercile. Step 2 adds trading-time
   (volume-scaled, A&L eq. 20) versions of ret5/ret20/depth as features (`features.trading_time.enabled`).
   *Falsified if:* tercile base rates differ by < 20 % relative or the sign flips across ≥ ⅓ of stocks. If the
   *high*-volume tercile wins, record that as support for capitulation instead.
7. **EXP-08 (+ double bottom)** (W4). *Hypothesis (Lo–Mamaysky–Wang 2000):* a retest of a prior smoothed swing low
   carries level memory that depth/RSI lack. *Change:* add `dbl_bottom_dist` and a `within_1.5pct` flag (causal
   kernel, h = 0.3 × h\*_CV, prior minimum ≥ 22 bars back, scaled per TF) to the EXP-08 S/R feature block.
   *Falsified if:* EXP-08 with the feature is not better than EXP-08 without it on Stage A.
8. **EXP-17 — directional-change overshoot features** (W2; lowest priority). *Hypothesis (Glattfelder et al. 2011):*
   since the average overshoot ≈ δ, a decline that has already overshot ≥ δ beyond its DC confirmation is nearer its
   end. *Change:* `features.dc: {enabled, k: 2.0}` → os_ratio and bars_since_dc. *Falsified if:* Stage A gate fails.
   Skip entirely if EXP-04/05/06 (other own-path W2 arms) all fail, which the headroom probe predicts.

**Protocol notes, not arms** (each needs a DECISIONS row before any arm runs, per the campaign rule): (a) also report
average precision / precision@matched-budget (Saito & Rehmsmeier) and a front-biased range recall (Tatbul et al.)
in Stage A. (b) Embargo hold_bars before the 2025-01-01 cut for calibration-window truth (AFML ch 7). (c) Assert
tolerance margin < minimum true-dip spacing (Truong et al.). (d) Isotonic calibration is required only before any
*live* gbdt deployment (Niculescu-Mizil & Caruana). (e) Not re-proposed: trend-scanning (R-05), meta-labelling
(R-25), changepoint detection (no fit to entry timing).
