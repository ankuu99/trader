# Portfolio sim `SC2-d5_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹570,227 · trades 5787 · win rate 47.8% · PF 1.12 · money-weighted win % 52.8 · avg ₹99/trade · max DD ₹252,006 (41.1%) · ann. return 6.0% · Calmar 0.15 · mean utilisation 39.0% · avg held 5.0 bars

## Excluding 2020

net ₹564,126 · trades 5421 · win rate 47.9% · PF 1.13 · money-weighted win % 52.9 · avg ₹104/trade · max DD ₹252,006 (41.1%) · ann. return 6.5% · Calmar 0.16 · mean utilisation 39.0% · avg held 5.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 5 | -1,155 |
| TIME | 5782 | 571,382 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 357 | -118,721 | 24.7 |
| 2012 | 389 | 45,353 | 13.0 |
| 2013 | 357 | -45,116 | 34.1 |
| 2014 | 362 | 122,047 | 6.2 |
| 2015 | 343 | -36,218 | 14.9 |
| 2016 | 357 | -81,044 | 17.6 |
| 2017 | 375 | 791,017 | 16.4 |
| 2018 | 373 | 9,791 | 7.7 |
| 2019 | 361 | 43,995 | 5.4 |
| 2020 | 366 | 6,101 | 6.6 |
| 2021 | 383 | -5,037 | 4.4 |
| 2022 | 372 | -78,433 | 7.8 |
| 2023 | 364 | -23,612 | 9.0 |
| 2024 | 342 | 48,127 | 3.7 |
| 2025 | 375 | -26,350 | 3.7 |
| 2026 | 311 | -81,672 | 6.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 37; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d5_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 5,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
