# Portfolio sim `SN-3_model` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,595,682 · trades 956 · win rate 55.1% · PF 1.84 · money-weighted win % 64.8 · avg ₹1,669/trade · max DD ₹255,383 (42.1%) · ann. return 16.8% · Calmar 0.40 · mean utilisation 94.0% · avg held 59.4 bars

## Excluding 2020

net ₹1,107,230 · trades 892 · win rate 54.3% · PF 1.63 · money-weighted win % 62.0 · avg ₹1,241/trade · max DD ₹254,847 (42.1%) · ann. return 12.7% · Calmar 0.30 · mean utilisation 94.0% · avg held 59.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | 8,151 |
| END | 15 | -27,202 |
| TIME | 939 | 1,614,733 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 48 | -155,896 | 42.1 |
| 2012 | 61 | 300,485 | 4.8 |
| 2013 | 60 | -68,597 | 29.8 |
| 2014 | 58 | 214,309 | 6.5 |
| 2015 | 62 | 53,268 | 11.6 |
| 2016 | 58 | -2,122 | 11.7 |
| 2017 | 62 | 192,232 | 3.8 |
| 2018 | 57 | -43,564 | 11.8 |
| 2019 | 59 | -22,056 | 11.2 |
| 2020 | 64 | 488,451 | 17.0 |
| 2021 | 60 | 291,902 | 5.1 |
| 2022 | 61 | 22,473 | 6.5 |
| 2023 | 60 | 153,320 | 2.4 |
| 2024 | 62 | 212,141 | 2.9 |
| 2025 | 62 | 6,972 | 3.3 |
| 2026 | 62 | -47,637 | 4.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 11; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_model",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
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
  "sources": [],
  "delist_grace_days": 7
}
```
