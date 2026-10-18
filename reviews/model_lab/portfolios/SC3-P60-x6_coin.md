# Portfolio sim `SC3-P60-x6_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,051,483 · trades 1257 · win rate 53.9% · PF 1.37 · money-weighted win % 57.9 · avg ₹837/trade · max DD ₹385,214 (31.6%) · ann. return 11.1% · Calmar 0.35 · mean utilisation 96.3% · avg held 46.1 bars

## Excluding 2020

net ₹969,732 · trades 1148 · win rate 54.1% · PF 1.39 · money-weighted win % 58.1 · avg ₹845/trade · max DD ₹241,907 (31.6%) · ann. return 11.1% · Calmar 0.35 · mean utilisation 96.3% · avg held 47.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -4,461 |
| STOP | 240 | -1,970,241 |
| TIME | 646 | 1,620,623 |
| TRAIL | 356 | 1,405,562 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 80 | -169,629 | 31.6 |
| 2012 | 68 | 71,734 | 22.3 |
| 2013 | 87 | 37,947 | 26.5 |
| 2014 | 80 | 259,797 | 10.4 |
| 2015 | 77 | 16,605 | 11.6 |
| 2016 | 80 | 23,642 | 15.2 |
| 2017 | 71 | 405,971 | 13.4 |
| 2018 | 85 | -102,092 | 16.1 |
| 2019 | 83 | -20,507 | 9.7 |
| 2020 | 109 | 81,751 | 23.4 |
| 2021 | 76 | 303,921 | 3.9 |
| 2022 | 75 | -90,161 | 14.4 |
| 2023 | 66 | 119,363 | 4.7 |
| 2024 | 75 | 188,854 | 5.4 |
| 2025 | 73 | -6,906 | 4.7 |
| 2026 | 72 | -68,809 | 8.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x6_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:coin",
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
