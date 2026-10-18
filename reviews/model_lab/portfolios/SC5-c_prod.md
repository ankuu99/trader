# Portfolio sim `SC5-c_prod` (run `A11_day_hgbq_edgez20`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,456,782 · trades 1144 · win rate 57.2% · PF 1.60 · money-weighted win % 61.6 · avg ₹1,273/trade · max DD ₹233,436 (30.9%) · ann. return 15.4% · Calmar 0.50 · mean utilisation 96.3% · avg held 50.9 bars

## Excluding 2020

net ₹1,290,198 · trades 1065 · win rate 56.1% · PF 1.57 · money-weighted win % 61.0 · avg ₹1,211/trade · max DD ₹233,436 (30.9%) · ann. return 14.8% · Calmar 0.48 · mean utilisation 96.3% · avg held 51.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -25,837 |
| TARGET | 329 | 3,069,757 |
| TIME | 800 | -1,587,138 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 57 | -98,956 | 30.9 |
| 2012 | 79 | 101,449 | 21.6 |
| 2013 | 81 | 79,132 | 21.1 |
| 2014 | 77 | 164,815 | 7.8 |
| 2015 | 67 | 54,564 | 9.3 |
| 2016 | 70 | 64,680 | 9.6 |
| 2017 | 75 | 607,463 | 4.4 |
| 2018 | 69 | -49,685 | 9.7 |
| 2019 | 72 | 35,032 | 8.4 |
| 2020 | 79 | 166,584 | 13.1 |
| 2021 | 74 | 210,478 | 3.4 |
| 2022 | 63 | -85,940 | 9.0 |
| 2023 | 73 | 76,643 | 5.0 |
| 2024 | 72 | 110,943 | 4.8 |
| 2025 | 68 | 35,597 | 5.2 |
| 2026 | 68 | -16,018 | 3.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC5-c_prod",
  "run_id": "A11_day_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": 0.2,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null,
  "sources": []
}
```
