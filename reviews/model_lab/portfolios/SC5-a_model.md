# Portfolio sim `SC5-a_model` (run `A11_day_hgbq_edgez20`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹636,296 · trades 1840 · win rate 51.7% · PF 1.25 · money-weighted win % 55.6 · avg ₹346/trade · max DD ₹312,132 (37.7%) · ann. return 6.7% · Calmar 0.18 · mean utilisation 58.9% · avg held 20.0 bars

## Excluding 2020

net ₹416,748 · trades 1708 · win rate 51.3% · PF 1.19 · money-weighted win % 54.3 · avg ₹244/trade · max DD ₹226,488 (37.7%) · ann. return 4.8% · Calmar 0.13 · mean utilisation 58.9% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 8 | -7,950 |
| TIME | 1832 | 644,246 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 100 | -184,962 | 37.7 |
| 2012 | 120 | 151,457 | 7.4 |
| 2013 | 93 | -73,269 | 22.3 |
| 2014 | 97 | 178,561 | 5.1 |
| 2015 | 139 | -19,843 | 17.8 |
| 2016 | 103 | 795 | 13.8 |
| 2017 | 110 | 162,957 | 2.5 |
| 2018 | 108 | -75,921 | 17.2 |
| 2019 | 118 | 237 | 12.9 |
| 2020 | 132 | 219,548 | 30.4 |
| 2021 | 84 | 33,955 | 6.6 |
| 2022 | 116 | -15,060 | 11.5 |
| 2023 | 141 | 85,750 | 2.8 |
| 2024 | 122 | 155,463 | 5.1 |
| 2025 | 139 | -509 | 4.8 |
| 2026 | 118 | 17,137 | 6.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 45; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC5-a_model",
  "run_id": "A11_day_hgbq_edgez20",
  "hold_bars": 20,
  "score_source": "run",
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
