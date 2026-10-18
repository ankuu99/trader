# Portfolio sim `SC1-1b_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹819,724 · trades 952 · win rate 51.2% · PF 1.19 · money-weighted win % 54.3 · avg ₹861/trade · max DD ₹704,913 (66.7%) · ann. return 8.7% · Calmar 0.13 · mean utilisation 92.1% · avg held 20.0 bars

## Excluding 2020

net ₹554,118 · trades 889 · win rate 50.2% · PF 1.14 · money-weighted win % 53.2 · avg ₹623/trade · max DD ₹459,968 (60.1%) · ann. return 6.4% · Calmar 0.11 · mean utilisation 92.1% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 4 | 29,358 |
| TIME | 948 | 790,366 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 44 | -188,785 | 41.7 |
| 2012 | 61 | 206,305 | 32.8 |
| 2013 | 60 | -130,678 | 58.8 |
| 2014 | 60 | 300,422 | 10.9 |
| 2015 | 61 | -22,109 | 14.3 |
| 2016 | 61 | 53,426 | 12.4 |
| 2017 | 61 | 186,367 | 8.1 |
| 2018 | 61 | -85,285 | 18.6 |
| 2019 | 60 | -251,064 | 33.8 |
| 2020 | 63 | 265,607 | 49.0 |
| 2021 | 62 | 193,807 | 7.0 |
| 2022 | 62 | -149,056 | 20.6 |
| 2023 | 60 | 294,991 | 4.6 |
| 2024 | 62 | 150,734 | 5.9 |
| 2025 | 61 | -21,052 | 7.5 |
| 2026 | 53 | 16,095 | 9.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-1b_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 120000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
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
