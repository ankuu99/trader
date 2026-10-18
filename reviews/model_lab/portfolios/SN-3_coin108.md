# Portfolio sim `SN-3_coin108` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹772,439 · trades 990 · win rate 50.7% · PF 1.30 · money-weighted win % 56.5 · avg ₹780/trade · max DD ₹410,660 (68.3%) · ann. return 8.2% · Calmar 0.12 · mean utilisation 97.1% · avg held 59.2 bars

## Excluding 2020

net ₹585,764 · trades 923 · win rate 49.5% · PF 1.25 · money-weighted win % 55.6 · avg ₹635/trade · max DD ₹410,660 (68.3%) · ann. return 6.7% · Calmar 0.10 · mean utilisation 97.1% · avg held 59.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 5 | 9,321 |
| END | 14 | -9,715 |
| TIME | 971 | 772,833 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 58 | -239,281 | 46.9 |
| 2012 | 62 | 102,459 | 31.3 |
| 2013 | 60 | -125,570 | 60.1 |
| 2014 | 62 | 225,624 | 25.2 |
| 2015 | 60 | 37,501 | 21.6 |
| 2016 | 60 | 68,471 | 23.7 |
| 2017 | 60 | 64,688 | 7.4 |
| 2018 | 62 | -164,773 | 32.6 |
| 2019 | 65 | 70,337 | 20.7 |
| 2020 | 67 | 186,675 | 40.9 |
| 2021 | 60 | 219,091 | 8.7 |
| 2022 | 61 | 64,808 | 14.2 |
| 2023 | 60 | 124,660 | 5.6 |
| 2024 | 61 | 221,439 | 6.5 |
| 2025 | 61 | -37,764 | 7.9 |
| 2026 | 71 | -45,925 | 7.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin108",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:108",
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
