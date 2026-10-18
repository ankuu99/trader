# Portfolio sim `S0_15m_A05_prod_time125` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹-215,331 · trades 5583 · win rate 47.8% · PF 0.95 · money-weighted win % 48.8 · avg ₹-39/trade · max DD ₹457,623 (67.5%) · ann. return -3.9% · Calmar -0.06 · mean utilisation 81.0% · avg held 124.9 bars

## Excluding 2020

net ₹-200,917 · trades 5020 · win rate 47.8% · PF 0.95 · money-weighted win % 48.7 · avg ₹-40/trade · max DD ₹379,611 (56.0%) · ann. return -4.1% · Calmar -0.07 · mean utilisation 81.0% · avg held 124.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 12 | 12,768 |
| TIME | 5571 | -228,099 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 140 | 58,543 | 2.9 |
| 2018 | 603 | -152,254 | 31.9 |
| 2019 | 646 | -58,577 | 28.5 |
| 2020 | 563 | -14,414 | 51.7 |
| 2021 | 632 | 45,648 | 14.8 |
| 2022 | 623 | -102,828 | 43.4 |
| 2023 | 635 | 92,030 | 17.6 |
| 2024 | 569 | 67,512 | 13.5 |
| 2025 | 656 | -67,269 | 27.2 |
| 2026 | 516 | -83,723 | 24.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 7.

## Spec

```json
{
  "sim_id": "S0_15m_A05_prod_time125",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 125,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": []
}
```
