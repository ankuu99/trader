# Portfolio sim `S0_day_A01_prod_time20` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹638,170 · trades 2218 · win rate 51.9% · PF 1.19 · money-weighted win % 54.4 · avg ₹288/trade · max DD ₹504,248 (42.3%) · ann. return 6.7% · Calmar 0.16 · mean utilisation 70.7% · avg held 19.9 bars

## Excluding 2020

net ₹688,447 · trades 2114 · win rate 51.8% · PF 1.23 · money-weighted win % 55.1 · avg ₹326/trade · max DD ₹347,347 (40.7%) · ann. return 7.9% · Calmar 0.19 · mean utilisation 70.7% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -9,076 |
| TIME | 2203 | 647,246 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 94 | -177,761 | 31.8 |
| 2012 | 151 | 138,451 | 18.8 |
| 2013 | 144 | -38,218 | 39.8 |
| 2014 | 152 | 185,455 | 9.2 |
| 2015 | 138 | 25,869 | 10.1 |
| 2016 | 138 | 12,281 | 14.9 |
| 2017 | 138 | 349,520 | 21.1 |
| 2018 | 146 | -161,952 | 18.5 |
| 2019 | 142 | 9,125 | 14.3 |
| 2020 | 104 | -50,277 | 27.8 |
| 2021 | 158 | 63,031 | 6.0 |
| 2022 | 129 | -13,673 | 12.1 |
| 2023 | 149 | 180,785 | 7.4 |
| 2024 | 160 | 90,913 | 7.3 |
| 2025 | 131 | 53,795 | 4.5 |
| 2026 | 144 | -29,175 | 7.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 13.

## Spec

```json
{
  "sim_id": "S0_day_A01_prod_time20",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
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
