# Portfolio sim `S0_day_A01_coin_time20` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹756,770 · trades 2814 · win rate 50.6% · PF 1.18 · money-weighted win % 54.2 · avg ₹269/trade · max DD ₹483,421 (56.8%) · ann. return 8.0% · Calmar 0.14 · mean utilisation 90.1% · avg held 20.0 bars

## Excluding 2020

net ₹665,116 · trades 2630 · win rate 50.2% · PF 1.18 · money-weighted win % 54.0 · avg ₹253/trade · max DD ₹366,349 (56.8%) · ann. return 7.6% · Calmar 0.13 · mean utilisation 90.1% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 13 | -1,035 |
| TIME | 2801 | 757,805 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 123 | -169,843 | 38.0 |
| 2012 | 179 | 137,369 | 22.0 |
| 2013 | 183 | -130,387 | 52.5 |
| 2014 | 180 | 284,212 | 12.1 |
| 2015 | 181 | 33,641 | 10.9 |
| 2016 | 182 | 7,456 | 16.3 |
| 2017 | 179 | 178,610 | 5.3 |
| 2018 | 179 | -73,223 | 18.8 |
| 2019 | 176 | -59,845 | 14.7 |
| 2020 | 184 | 91,654 | 38.0 |
| 2021 | 182 | 143,381 | 7.7 |
| 2022 | 185 | -21,636 | 16.1 |
| 2023 | 179 | 210,983 | 5.8 |
| 2024 | 184 | 147,524 | 5.8 |
| 2025 | 181 | 11,273 | 7.2 |
| 2026 | 157 | -34,398 | 7.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 14.

## Spec

```json
{
  "sim_id": "S0_day_A01_coin_time20",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:coin",
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
