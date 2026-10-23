# Giveback episodes vs external market indicators — 2026-09-01

**Question:** can the strategy's giveback-from-peak episodes be correlated with external,
market-level indicators (indices, India VIX, turbulence, absorption ratio)?
**Data:** backtests 2025-01-01 → 2026-09-01; realized P&L attributed to exit date.
Indicators: NIFTY 50, NIFTY BANK, INDIA VIX day closes (Kite); turbulence index
(Mahalanobis distance of watchlist daily returns vs trailing 120-day covariance) and
absorption ratio (top-3 PCA eigenvalue share) computed from our own 21-name candle cache.
Scripts: scratchpad `yesbank_giveback_corr.py`, `yesbank_vix_overlay.py`,
`portfolio_giveback_corr.py`.

## Single-stock probe (YESBANK, 85 trades, ₹6.9k)

- Weekly P&L vs Bank Nifty r=+0.26, vs Nifty +0.14, vs VIX change −0.19.
- Bank Nifty down weeks avg −₹99 vs up weeks +₹293.
- Striking split: VIX≥15 weeks carried ALL the P&L (₹6.9k/28wk); VIX<15 weeks net ₹0 (60wk).
- Episode overlay: max-VIX-during-episode flagged givebacks that endpoint index returns
  missed (Apr-2025 crash-and-rebound: Bank Nifty +6.8% point-to-point, VIX max 22.8).

## Portfolio (22 names, 425 trades, ₹322k)

Episodes ≥ ₹3k (depth / same-window BN% / N50% / VIXmax / TURBmax / ΔABS):

| peak→trough | depth | BN% | N50% | VIXmax | TURBmax | ΔABS |
|---|---|---|---|---|---|---|
| 2025-01-03 → 05-16 | ₹53.6k | +8.6 | +4.2 | 22.8 | — | — |
| 2026-01-14 → 02-03 | ₹22.7k | +0.8 | +0.2 | 15.1 | 160.0 | +0.011 |
| 2026-02-25 → 04-10 | ₹22.5k | −8.4 | −5.6 | 27.9 | 83.0 | **+0.041** |
| 2025-09-22 → 10-15 | ₹11.5k | +2.7 | +0.5 | 11.4 | — | — |
| (10 more ₹3–9k) | | mixed | mixed | 11–19 | 22–77 | ±0.01 |

Weekly correlations (n=88; turbulence/absorption n=45 — series starts once all 21 names
have 120d of common history):

| indicator | r |
|---|---|
| NIFTY BANK weekly % | +0.24 |
| NIFTY 50 weekly % | +0.23 |
| VIX weekly change | −0.21 |
| VIX level | −0.02 |
| Turbulence level | −0.03 |
| Absorption level | +0.34 |
| Absorption change | −0.27 |

Conditioning: Nifty-up weeks avg ₹5.4k vs down weeks ₹2.3k (down weeks still positive);
VIX≥15 avg ₹4.1k vs <15 ₹3.5k (no real split); turbulence terciles low ₹7.7k / mid ₹4.0k /
high ₹5.6k (no monotone pattern).

## Conclusions

1. **Partial, weak-to-moderate correlation.** Weekly market direction explains ~5% of P&L
   variance (r≈+0.24). The portfolio still averages positive P&L in down-index weeks —
   per-stock dip selection, not market beta, drives most outcomes.
2. **YESBANK's dramatic "all P&L above VIX 15" split did NOT generalize** — portfolio-level
   VIX≥15 vs <15 is a wash. Single-stock artifact; do not build rules from it.
3. **The deepest giveback (₹53.6k, Jan→May 2025) happened while Bank Nifty rose 8.6%** —
   endpoint index returns are the wrong lens. Vol-spike measures (VIX max during episode,
   absorption *rises*) do flag the market-driven episodes: the Feb→Apr 2026 correction
   carries the biggest ΔABS (+0.041) and VIXmax 27.9, and rising absorption within a week
   correlates with losses (r=−0.27), matching Kritzman et al. (absorption spikes precede
   drawdowns). Absorption *level* +0.34 is likely regime coincidence, not causation.
4. **No gating.** Consistent with prior falsifications (knife-regime entry gate NULL,
   probability-driven exits NULL, slow-TF cap falsified): the effect sizes here are far too
   small to filter trades on, and idiosyncratic episodes dominate. Value is **diagnostic**:
   when a giveback happens, VIXmax/ΔABS over the episode says whether it was a market event
   or our own stock selection.

## Possible next steps (not committed)

- Dashboard: annotate the Giveback pane's episode table with same-window Nifty %, VIX max,
  and ΔAbsorption (all computable from cached candles + one VIX day-series fetch).
- Data additions if ever revisited: FII/DII daily flows (NSE), Nifty PCR, % of universe
  above 200DMA (breadth from our own cache).
