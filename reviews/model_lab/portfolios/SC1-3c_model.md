# Portfolio sim `SC1-3c_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,015,151 · trades 2907 · win rate 51.4% · PF 1.23 · money-weighted win % 55.1 · avg ₹349/trade · max DD ₹368,493 (47.8%) · ann. return 10.7% · Calmar 0.22 · mean utilisation 92.9% · avg held 20.0 bars

## Excluding 2020

net ₹848,111 · trades 2718 · win rate 50.9% · PF 1.21 · money-weighted win % 54.8 · avg ₹312/trade · max DD ₹345,418 (47.8%) · ann. return 9.7% · Calmar 0.20 · mean utilisation 92.9% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -11,821 |
| TIME | 2893 | 1,026,972 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 172 | -149,237 | 34.3 |
| 2012 | 184 | 257,730 | 12.6 |
| 2013 | 184 | -92,030 | 47.8 |
| 2014 | 182 | 174,383 | 7.5 |
| 2015 | 184 | 45,252 | 10.7 |
| 2016 | 183 | 82,610 | 14.7 |
| 2017 | 183 | 292,458 | 17.7 |
| 2018 | 183 | -119,979 | 18.9 |
| 2019 | 182 | 53,467 | 19.2 |
| 2020 | 189 | 167,040 | 24.7 |
| 2021 | 183 | 115,503 | 5.4 |
| 2022 | 184 | -3,697 | 12.0 |
| 2023 | 185 | 175,232 | 3.9 |
| 2024 | 185 | 10,149 | 6.1 |
| 2025 | 184 | 9,730 | 5.9 |
| 2026 | 160 | -3,460 | 6.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 31; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-3c_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "run",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 3,
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
