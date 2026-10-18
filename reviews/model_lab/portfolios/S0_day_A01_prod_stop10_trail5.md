# Portfolio sim `S0_day_A01_prod_stop10_trail5` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹729,331 · trades 3020 · win rate 49.4% · PF 1.17 · money-weighted win % 53.9 · avg ₹242/trade · max DD ₹358,934 (51.5%) · ann. return 7.7% · Calmar 0.15 · mean utilisation 68.3% · avg held 14.1 bars

## Excluding 2020

net ₹853,882 · trades 2820 · win rate 49.9% · PF 1.22 · money-weighted win % 54.9 · avg ₹303/trade · max DD ₹308,782 (51.5%) · ann. return 9.8% · Calmar 0.19 · mean utilisation 68.3% · avg held 14.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 807 |
| STOP | 841 | -3,510,335 |
| TIME | 1306 | 1,921,453 |
| TRAIL | 858 | 2,317,406 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 157 | -199,637 | 31.7 |
| 2012 | 187 | 68,325 | 22.1 |
| 2013 | 217 | -63,297 | 42.1 |
| 2014 | 198 | 184,259 | 11.4 |
| 2015 | 184 | 7,417 | 9.6 |
| 2016 | 193 | -9,103 | 15.3 |
| 2017 | 176 | 665,558 | 17.0 |
| 2018 | 221 | -67,983 | 9.9 |
| 2019 | 223 | -10,217 | 11.7 |
| 2020 | 200 | -124,551 | 21.3 |
| 2021 | 188 | 62,182 | 5.8 |
| 2022 | 175 | -14,006 | 10.7 |
| 2023 | 176 | 136,867 | 7.6 |
| 2024 | 189 | 118,066 | 7.6 |
| 2025 | 164 | 5,129 | 6.5 |
| 2026 | 172 | -29,679 | 5.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 17.

## Spec

```json
{
  "sim_id": "S0_day_A01_prod_stop10_trail5",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": 0.1,
  "target_pct": null,
  "trail_pct": 0.05,
  "trail_activate_pct": 0.05,
  "reentry_gap_bars": 0,
  "exclusions": []
}
```
