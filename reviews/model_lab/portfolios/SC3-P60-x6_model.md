# Portfolio sim `SC3-P60-x6_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,390,292 · trades 1276 · win rate 53.0% · PF 1.51 · money-weighted win % 60.1 · avg ₹1,090/trade · max DD ₹315,060 (41.0%) · ann. return 14.7% · Calmar 0.36 · mean utilisation 95.7% · avg held 45.3 bars

## Excluding 2020

net ₹1,323,168 · trades 1178 · win rate 52.8% · PF 1.53 · money-weighted win % 60.5 · avg ₹1,123/trade · max DD ₹248,067 (41.0%) · ann. return 15.2% · Calmar 0.37 · mean utilisation 95.7% · avg held 45.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -12,827 |
| STOP | 232 | -1,892,597 |
| TIME | 670 | 1,669,654 |
| TRAIL | 359 | 1,626,062 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 82 | -194,464 | 41.0 |
| 2012 | 73 | 148,979 | 18.0 |
| 2013 | 94 | -26,053 | 29.5 |
| 2014 | 77 | 253,811 | 7.2 |
| 2015 | 77 | 11,477 | 13.8 |
| 2016 | 73 | 71,840 | 12.4 |
| 2017 | 73 | 574,285 | 12.5 |
| 2018 | 96 | -28,228 | 8.5 |
| 2019 | 88 | 3,369 | 9.3 |
| 2020 | 98 | 67,124 | 16.4 |
| 2021 | 75 | 221,758 | 3.5 |
| 2022 | 80 | -25,146 | 9.0 |
| 2023 | 76 | 94,679 | 6.1 |
| 2024 | 69 | 169,405 | 5.2 |
| 2025 | 75 | 54,607 | 3.6 |
| 2026 | 70 | -7,150 | 4.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x6_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": 0.2,
  "target_pct": null,
  "trail_pct": 0.1,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
