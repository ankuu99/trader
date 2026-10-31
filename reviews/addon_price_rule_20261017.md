# Add-on price rule — "only add when cheaper" (TD-008, 2026-10-17)

Owner idea: allow a scale-in add-on only when the new price is below the original entry (or the previous buy),
so a false-positive model signal can't pyramid into a rising position. Owner's own prior: probably a falling knife
on real declines and missed buy-ins on real rises — "worth testing out".

Fixed engine (d9e7bc7), released setting as the reference: scale-in 50 %/2 tiers/10 % pool + loss block 3 sessions,
₹6L, compounding, current 24-name config. 14 windows, each a fresh start. Variants (scratch monkeypatch of
`RiskManager._validate_addon`, no repo change): `below entry` (add-on price < parent entry), `below last buy`
(< previous lot), `0–4 % below last` (band). Δ = P&L vs the released setting in the same window.

```
window                   released (si+lb3) |           below entry|        below last buy|       0–4% below last
2020-01→2026-10   ₹  1913.2k DD 36.8% |   -113.6k DD 37.7% |   -110.2k DD 37.8% |   -136.6k DD 37.4% |
2020              ₹   -32.8k DD 36.8% |     -6.4k DD 37.7% |     -7.7k DD 37.8% |     -2.8k DD 37.4% |
2021              ₹   158.6k DD  6.4% |    -15.9k DD  6.3% |    -21.5k DD  6.9% |    -11.4k DD  7.4% |
2022              ₹    31.0k DD  6.6% |    -12.2k DD  6.9% |    -11.3k DD  6.9% |    -10.6k DD  7.1% |
2023              ₹   169.2k DD  2.4% |     -6.4k DD  2.7% |     -3.9k DD  2.7% |     -4.8k DD  3.1% |
2024              ₹   143.3k DD  5.5% |     +5.1k DD  5.4% |     +4.1k DD  5.4% |    +15.3k DD  5.0% |
2025              ₹   119.4k DD  5.7% |     +3.3k DD  5.9% |     +3.6k DD  5.9% |     -2.6k DD  5.4% |
2026 YTD          ₹   296.1k DD  3.6% |     -2.7k DD  3.6% |     -1.6k DD  3.6% |    -11.1k DD  3.7% |
2020–21           ₹   150.1k DD 36.8% |    -22.4k DD 37.7% |    -21.0k DD 37.8% |    -12.5k DD 37.4% |
2022–23           ₹   213.6k DD  6.6% |    -33.3k DD  6.9% |    -30.8k DD  6.9% |    -33.1k DD  7.1% |
2024–25           ₹   278.3k DD 13.2% |     +4.6k DD 13.4% |     +3.9k DD 13.3% |    +16.3k DD 12.5% |
COVID Feb–Jun 20  ₹  -138.1k DD 36.0% |     +1.0k DD 36.2% |     -2.0k DD 36.2% |     +6.7k DD 36.2% |
Bear H1-22        ₹   -14.7k DD  7.6% |     -7.9k DD  8.0% |     -7.0k DD  7.9% |     -4.1k DD  7.1% |
Corr Oct24–Mar25  ₹   -32.8k DD  9.9% |     +0.0k DD 10.2% |     +0.6k DD 10.1% |     +5.5k DD  9.7% |
  below entry        years better than released: 2/7  sum Δ ₹-35.3k  avg ΔDD +0.21pp
  below last buy     years better than released: 2/7  sum Δ ₹-38.3k  avg ΔDD +0.31pp
  0–4% below last    years better than released: 1/7  sum Δ ₹-28.0k  avg ΔDD +0.30pp
```

## Verdict — FALSIFIED, don't build

- Full 2020→2026: every variant loses ₹110–137k and drawdown gets slightly worse (36.8 % → 37.4–37.8 %).
- Calendar years beaten: 2/7, 2/7, 1/7. The only consistent gain is 2024 (+₹4–15k); 2021/2022 lose ₹10–22k each.
- Stress windows (COVID, H1-22 bear, Oct-24 correction): within ±₹8k — the rule gives no crash protection either.
- Why: the add-ons the rule removes are the ones that pyramid into winners that keep rising; the ones it keeps
  buy the dip inside positions that the stale exits later close at a loss — exactly the owner's falling-knife
  vs missed-buy-ins reasoning. The parent-frozen stale anchor and the loss block already bound the knife case.
