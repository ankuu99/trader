# Stage A — batch 1 (EXP-01…EXP-10), 2026-10-18

Protocol: `docs/01_Extrema_Model_Campaign.md`. Baseline: config @ 5970eb5 (post-ISS-14). Truth: "tradeable trough" —
bar t is good iff a long at close[t] reaches +profit_pct before the stock's own non-model exits fire (shared simulator
`trader/policy/outcome.py`). Test window 2025-01-01 → 2026-10-16; thresholds matched on 2023–24 firing counts.
Raw: `runs/stage_a_<arm>.json`; overlays: `config/experiments/`; code on branches `exp/labels` (b99bfce),
`exp/features` (d54a0c0), `exp/rules` (abd3233), scaffold on the main line (c3fb3a3).

## Baseline reading

- Production P(min) median AUC **0.511** vs tradeable troughs (21 stocks): it does not rank troughs that pay.
- Single own-price measures are no better (headroom probe EXP-00b): depth50 0.534, ret20 0.515, RSI14 0.513.

## Results (gate: median ΔAUC ≥ +0.03 with ≤⅓ worse, OR median ΔEV@matched ≥ +0.25 pp with ≤⅓ worse)

| Arm | What | median ΔAUC | AUC worse | median ΔEV@matched (pp) | EV worse | Verdict |
|---|---|---|---|---|---|---|
| EXP-03 | forward_label re-test | -0.000 | 62 % | +0.00 | 24 % | FAIL |
| EXP-04 | lag stacking t-1,t-2 | -0.000 | 52 % | -0.62 | 76 % | FAIL |
| EXP-01 | tradeable labels (minima) | -0.013 | 76 % | -0.63 | 70 % | FAIL |
| EXP-02 | tradeable labels (every 5th bar) | -0.072 | 67 % | -1.10 | 76 % | FAIL |
| EXP-05 | bar-shape add-on | -0.002 | 67 % | -0.62 | 71 % | FAIL |
| EXP-06 | ATR-distance add-on | -0.003 | 67 % | -0.28 | 71 % | FAIL |
| EXP-07 | market add-on (Nifty/VIX) | +0.010 | 29 % | -0.18 | 62 % | FAIL |
| EXP-08 | support/resistance add-on | -0.002 | 67 % | -0.57 | 67 % | FAIL |
| EXP-09a | rule: RSI<35+bounce+EMA50 | -0.007 | 67 % | -1.80 | 85 % | FAIL |
| EXP-09b | rule: lowest-of-20 + up-close | -0.006 | 62 % | -0.68 | 81 % | FAIL |
| EXP-10a | rule: raw OU s-score | -0.006 | 52 % | -0.73 | 71 % | FAIL |
| EXP-10b | OU s-score features | +0.000 | 48 % | -0.16 | 67 % | FAIL |

Tuning-free cross-check (`scripts/campaign/tail_compare.py`, same top-q tail of each arm's own scores + average
precision): the uniformly negative ΔEV@matched is largely a bias (baseline thresholds were calibrated on windows that
overlap the test window); under the tuning-free view most arms sit at ≈ 0, the tradeable labels and the rules stay
clearly negative, and EXP-07 is the only arm with a consistent positive ranking change (ΔAP +0.006, worse on 29 %;
ΔAUC +0.012–0.014 on 4h/day names vs +0.006 on 15m). **No arm passes under either view.**

## What this rules out

1. **Better own-price features don't help** (EXP-04/05/06/08/10b): bar shape, lags, ATR distance, S/R levels and OU
   features all sit at chance against the tradeable truth — consistent with the headroom probe.
2. **Outcome-aligned labels hurt** (EXP-01/02): teaching the model "dips that pay" from its own 1,200-bar window makes
   ranking WORSE (−0.013 / −0.072). With so few paying dips per window the class-0 set is tiny and noisy; the model
   overfits it. This retires the main hypothesis the campaign started with (ledger B-01 / AFML triple barrier as the
   primary label).
3. **The no-ML rules are worse than the model** (EXP-09a/09b/10a): the model's "capitulation bar" bias is still better
   than RSI / lowest-turn / OU rules at the top tail.
4. **forward_label is a no-op on aggregated TFs** (EXP-03).

## What it points to

The only information that ranks tradeable troughs is **market state**, and it acts on *when* to trade, not *which*
dip: prior-day India VIX level median AUC 0.638 (86 % of stocks), robust in 6/7 calendar years 2020–26
(`vix_by_year.py`); baseline positions entered in the VIX stress tercile average +1.34 % vs +0.66 % in calm
(2020–26, 7/7 years). A per-stock model can't learn it from a 7-week 15m window (EXP-07), so it is tested at the
decision layer as **EXP-18** (pre-registered, DECISIONS 2026-10-18).
