# Portfolio sim `SC3-P60-x3_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,212,919 · trades 1106 · win rate 56.7% · PF 1.57 · money-weighted win % 61.2 · avg ₹1,097/trade · max DD ₹415,745 (30.2%) · ann. return 12.8% · Calmar 0.42 · mean utilisation 96.4% · avg held 52.4 bars

## Excluding 2020

net ₹1,166,501 · trades 1036 · win rate 57.3% · PF 1.61 · money-weighted win % 61.7 · avg ₹1,126/trade · max DD ₹299,185 (30.2%) · ann. return 13.4% · Calmar 0.44 · mean utilisation 96.4% · avg held 52.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 1,482 |
| TIME | 783 | 84,596 |
| TRAIL | 308 | 1,126,841 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 57 | -89,726 | 28.6 |
| 2012 | 67 | 113,578 | 14.8 |
| 2013 | 77 | -23,190 | 30.2 |
| 2014 | 70 | 190,671 | 7.2 |
| 2015 | 67 | 38,132 | 10.8 |
| 2016 | 64 | 91,164 | 9.8 |
| 2017 | 74 | 392,092 | 11.4 |
| 2018 | 77 | -39,653 | 10.8 |
| 2019 | 68 | -17,148 | 13.7 |
| 2020 | 70 | 46,418 | 19.9 |
| 2021 | 74 | 248,476 | 4.8 |
| 2022 | 69 | -51,554 | 9.2 |
| 2023 | 66 | 84,568 | 5.5 |
| 2024 | 68 | 158,340 | 6.9 |
| 2025 | 69 | 74,600 | 4.6 |
| 2026 | 69 | -3,849 | 4.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 8; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x3_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": 0.1,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
