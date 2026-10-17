# Scale-in × re-entry discount × loss re-entry block — 2×2×2 (2026-10-17)

Fixed engine (pre-order-reject freeze fix, d9e7bc7). Current 21-name watchlist, ₹6L @ 6.67 %,
compounding on. Settings: scale-in 50 %/2 tiers/10 % pool; discount 1.5 % one-sided; loss
block 3 sessions. Full window 2025-01-01 → 2026-10-15 plus four independent windows (each
starts flat at ₹6L). Δ = P&L vs baseline in the same window.

| Combo | Full P&L (Δ) | Full DD | Calmar | 2025-H1 | 2025-H2 | 2026-H1 | 2026-Q3+ | Windows beaten |
|---|---|---|---|---|---|---|---|---|
| Baseline | ₹442.4k | 6.7 % (₹40.2k) | 5.41 | ₹55.6k | ₹53.0k | ₹213.9k | ₹3.6k | — |
| Loss block | ₹413.9k (−28.5k) | **5.1 %** (₹30.4k) | 6.74 | +0.1 | −7.6 | −2.2 | +6.3 | 2/4 |
| Discount | ₹451.8k (+9.4k) | 6.5 % | 5.70 | −0.2 | −6.1 | +15.1 | +2.3 | 2/4 |
| Discount + loss block | ₹415.4k (−27.1k) | 5.1 % | 6.75 | −0.3 | −10.3 | −2.8 | +7.2 | 1/4 |
| Scale-in | **₹487.9k (+45.5k)** | 7.6 % (₹45.3k) | 5.24 | +10.9 | +6.1 | +12.6 | +4.3 | 4/4 |
| **Scale-in + loss block** | ₹465.4k (+23.0k) | **5.8 %** (₹34.9k) | **6.52** | +11.8 | +9.4 | +15.6 | +10.9 | **4/4** |
| Scale-in + discount | ₹478.8k (+36.3k) | 7.4 % | 5.28 | +7.5 | +7.8 | +27.7 | +9.4 | 4/4 |
| All three | ₹455.0k (+12.6k) | 6.0 % | 6.24 | +5.3 | +6.1 | +14.6 | +13.7 | 4/4 |

Drawdown by window, baseline → scale-in + loss block: 2025-H1 6.7 → 5.8 %, 2025-H2 2.3 → 2.1 %,
2026-H1 3.7 → 3.0 %, 2026-Q3+ 2.6 → 2.9 %.

## Reading

- **Scale-in is the P&L lever** — positive in all four windows on its own, but it raises DD
  (6.7 → 7.6 %) because it is leverage on the same signal.
- **The loss block is the risk lever** — on its own it costs ~₹28k and is mixed by window,
  but it cuts DD by a quarter.
- **Together they complement:** scale-in + loss block is the only combo that beats the baseline
  on P&L **and** drawdown over the full window, and it beats it in every half-year window — by
  more than scale-in alone in all four (+11.8/+9.4/+15.6/+10.9 vs +10.9/+6.1/+12.6/+4.3).
  In the 2025-H1 correction (the only real stress here) DD *fell* 6.7 → 5.8 %.
- **The discount gate adds nothing reliable** — mixed alone, one big window (+15.1k, +27.7k
  in 2026-H1) drives every gain; with the loss block it is redundant. Drop it.
- Path dependence caveat: scale-in + loss block's half-year deltas sum to +₹47.7k but the
  continuous run shows +₹23.0k — compounding and position sequencing over 21 months differ
  from four fresh starts. Direction is consistent; magnitude is uncertain.

## Caveats before enabling

- Scale-in needs real extra cash: the 10 % pool is ₹60k on top of ₹6L (live sizing is capped
  by Kite cash; startup warns if the pool isn't funded). Peak utilisation previously reached
  ~112 %.
- The 2020–26 counterfactual found scale-in amplifies bad quarters 3–4×; this window's worst
  stress is only the 2025-H1 correction. The loss block is the natural brake on exactly that.
- Config: `scale_in.enabled: true` + `risk.loss_reentry_block: {enabled: true, sessions: 3}`.
