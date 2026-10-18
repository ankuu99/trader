# Portfolio sim `SN-3_coin107` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,038,291 · trades 989 · win rate 51.9% · PF 1.42 · money-weighted win % 58.7 · avg ₹1,050/trade · max DD ₹407,085 (47.7%) · ann. return 11.0% · Calmar 0.23 · mean utilisation 96.8% · avg held 59.2 bars

## Excluding 2020

net ₹801,507 · trades 921 · win rate 51.0% · PF 1.36 · money-weighted win % 57.7 · avg ₹870/trade · max DD ₹322,849 (47.7%) · ann. return 9.2% · Calmar 0.19 · mean utilisation 96.8% · avg held 59.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -569 |
| END | 15 | 1,264 |
| TIME | 973 | 1,037,596 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 56 | -241,379 | 45.0 |
| 2012 | 64 | 212,353 | 32.4 |
| 2013 | 60 | -77,780 | 40.1 |
| 2014 | 60 | 205,959 | 14.6 |
| 2015 | 60 | -62,958 | 21.4 |
| 2016 | 60 | 93,521 | 15.4 |
| 2017 | 60 | 156,735 | 6.5 |
| 2018 | 61 | -94,015 | 22.5 |
| 2019 | 66 | 18,286 | 16.6 |
| 2020 | 68 | 236,784 | 31.0 |
| 2021 | 60 | 342,835 | 4.4 |
| 2022 | 60 | 2,872 | 11.4 |
| 2023 | 60 | 102,207 | 4.1 |
| 2024 | 60 | 125,105 | 5.8 |
| 2025 | 60 | -13,674 | 5.9 |
| 2026 | 74 | 31,441 | 6.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 8; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin107",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:107",
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
