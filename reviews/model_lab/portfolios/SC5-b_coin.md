# Portfolio sim `SC5-b_coin` (run `A11_day_hgbq_edgez20`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,480,473 · trades 975 · win rate 53.4% · PF 1.67 · money-weighted win % 62.5 · avg ₹1,518/trade · max DD ₹287,257 (40.0%) · ann. return 15.6% · Calmar 0.39 · mean utilisation 97.1% · avg held 59.9 bars

## Excluding 2020

net ₹1,293,371 · trades 908 · win rate 52.8% · PF 1.65 · money-weighted win % 62.3 · avg ₹1,424/trade · max DD ₹252,353 (40.0%) · ann. return 14.8% · Calmar 0.37 · mean utilisation 97.1% · avg held 59.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -36,632 |
| TIME | 961 | 1,517,105 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 56 | -149,083 | 37.3 |
| 2012 | 64 | 122,115 | 19.9 |
| 2013 | 60 | 21,764 | 37.1 |
| 2014 | 60 | 410,254 | 6.3 |
| 2015 | 60 | 19,880 | 6.8 |
| 2016 | 60 | 35,824 | 12.7 |
| 2017 | 60 | 236,787 | 6.1 |
| 2018 | 60 | -1,534 | 10.4 |
| 2019 | 60 | -7,834 | 8.9 |
| 2020 | 67 | 187,101 | 17.5 |
| 2021 | 68 | 306,649 | 3.3 |
| 2022 | 60 | -12,837 | 8.8 |
| 2023 | 60 | 157,462 | 4.6 |
| 2024 | 60 | 141,633 | 4.7 |
| 2025 | 60 | 7,265 | 5.8 |
| 2026 | 60 | 5,026 | 4.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC5-b_coin",
  "run_id": "A11_day_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "ref:coin",
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
  "queue_max_runup": null,
  "sources": []
}
```
