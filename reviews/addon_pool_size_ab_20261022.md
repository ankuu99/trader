# Add-on (scale-in) pool size A/B — ₹60k vs ₹1.2L vs ₹2.4L vs unlimited (2026-10-22)

**Trigger:** live 2026-10-21 — 17 add-on signals rejected with the pool unfunded (TD-022); owner asked what unlimited
add-ons would do. Engine at HEAD (fundamental_based_approach, config identical to release-20261018a), live config:
scale-in 50 %/2 tiers/1-day spacing, loss block 3 sessions, ₹6L @ 6.67 %, compounding. Only `scale_in.budget_pct`
varied: 10 (live ₹60k) / 20 / 40 / 1000 (= unlimited). Each window an independent run from ₹6L. Harness, raw JSON and
tables: `reviews/addon_pool_size_ab_20261022/`. "peak add-on cash" = max concurrent add-on cost basis (the extra
money the account must actually hold). Same survivorship caveat as `scalein_lossblock_2020_horizon_20261017.md`.

## Per-year (fair read — each year starts at ₹6L)

| Year | Now ₹60k | ₹1.2L Δ | ₹2.4L Δ | Unlimited Δ | Unlimited peak add-on cash | DD now → unlimited |
|---|---|---|---|---|---|---|
| 2020 | ₹9.2k | −₹18.4k | −₹37.9k | −₹37.9k | ₹227k | ₹219k → ₹263k (COVID) |
| 2021 | ₹165.7k | +₹11.0k | +₹24.6k | +₹27.7k | ₹334k | ₹39.5k → ₹47.9k |
| 2022 | ₹37.8k | +₹0.4k | +₹3.8k | +₹3.8k | ₹219k | ₹38.8k → ₹46.8k |
| 2023 | ₹166.3k | +₹19.7k | +₹32.2k | +₹32.8k | ₹250k | ₹21.6k → ₹20.8k |
| 2024 | ₹147.2k | +₹36.8k | +₹73.6k | +₹71.7k | ₹266k | ₹31.3k → ₹38.3k |
| 2025 | ₹118.9k | +₹15.3k | +₹37.0k | +₹41.4k | ₹273k | ₹34.9k → ₹35.7k |
| 2026 YTD | ₹276.3k | +₹47.6k | +₹86.4k | +₹90.1k | ₹294k | ₹22.3k → ₹27.7k |

Full 2020→2026 compounding run: ₹2.02M → ₹2.78M unlimited (+₹762k) but peak add-on cash ₹984k, because lots grow
with compounded P&L — not comparable to the yearly rows.

## Reading

- **More pool = more P&L in 6 of 7 years**; only the 2020 crash year loses (−₹38k, DD +₹44k). Same shape as the
  2026-07-07 counterfactual: add-ons are leverage on the same curve — they amplify crash quarters.
- **₹2.4L ≈ unlimited.** The book never needs much more than ₹2.2–3.3L of add-on cash in a year; ₹2.4L captures
  ~95 % of the unlimited gain. ₹1.2L captures about half.
- **Return on the extra cash:** unlimited's extra P&L ÷ extra peak cash ≈ +0.10…+0.39 per year in 2021–26 (median
  ~0.2), −0.24 in 2020. Extra BASE capital earns ~0 (fixed engine saturates at ₹5L — `project_capital_500k_ab`), so
  extra money is worth more in the add-on pool than in the base.
- Money-weighted win % is flat (±1 pt): add-ons don't change trade quality, only size.
- Live requires the cash: a ₹2.4L pool means the account must hold ~₹6L base + cum P&L + ₹2.4L.

No config change made — owner decision.
