# Portfolio sim `SC3-P60-x1_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,205,040 · trades 1111 · win rate 52.7% · PF 1.46 · money-weighted win % 59.3 · avg ₹1,085/trade · max DD ₹276,803 (35.9%) · ann. return 12.7% · Calmar 0.35 · mean utilisation 96.3% · avg held 52.4 bars

## Excluding 2020

net ₹977,284 · trades 1030 · win rate 52.7% · PF 1.41 · money-weighted win % 58.5 · avg ₹949/trade · max DD ₹262,950 (35.9%) · ann. return 11.2% · Calmar 0.31 · mean utilisation 96.3% · avg held 52.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -18,082 |
| STOP | 229 | -1,882,857 |
| TIME | 867 | 3,105,979 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 71 | -183,243 | 35.9 |
| 2012 | 67 | 135,200 | 22.2 |
| 2013 | 79 | -17,874 | 27.4 |
| 2014 | 64 | 241,460 | 9.7 |
| 2015 | 71 | 68,186 | 10.7 |
| 2016 | 67 | 106,650 | 9.1 |
| 2017 | 64 | 320,537 | 13.9 |
| 2018 | 74 | -120,450 | 14.3 |
| 2019 | 73 | -14,284 | 11.4 |
| 2020 | 81 | 227,755 | 14.9 |
| 2021 | 67 | 172,713 | 6.6 |
| 2022 | 64 | -6,577 | 9.4 |
| 2023 | 72 | 125,264 | 8.7 |
| 2024 | 62 | 151,645 | 3.9 |
| 2025 | 68 | 20,077 | 5.3 |
| 2026 | 67 | -22,021 | 4.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 7; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x1_model",
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
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
