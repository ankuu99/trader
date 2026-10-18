# Portfolio sim `SN-3_coin103` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹636,615 · trades 990 · win rate 51.6% · PF 1.24 · money-weighted win % 55.4 · avg ₹643/trade · max DD ₹497,201 (80.9%) · ann. return 6.7% · Calmar 0.08 · mean utilisation 96.7% · avg held 59.2 bars

## Excluding 2020

net ₹434,209 · trades 923 · win rate 50.5% · PF 1.18 · money-weighted win % 54.1 · avg ₹470/trade · max DD ₹485,303 (80.9%) · ann. return 5.0% · Calmar 0.06 · mean utilisation 96.7% · avg held 59.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | 10,665 |
| END | 15 | 14,706 |
| TIME | 973 | 611,244 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 57 | -295,592 | 53.1 |
| 2012 | 63 | 112,409 | 30.9 |
| 2013 | 60 | -122,345 | 74.2 |
| 2014 | 60 | 371,287 | 14.8 |
| 2015 | 60 | -35,282 | 18.8 |
| 2016 | 60 | 107,792 | 20.7 |
| 2017 | 60 | 115,040 | 6.7 |
| 2018 | 62 | -136,653 | 27.5 |
| 2019 | 66 | -118,802 | 26.4 |
| 2020 | 67 | 202,406 | 37.9 |
| 2021 | 60 | 193,279 | 7.2 |
| 2022 | 60 | 26,039 | 14.7 |
| 2023 | 60 | 139,151 | 9.0 |
| 2024 | 60 | 164,378 | 6.4 |
| 2025 | 61 | -109,220 | 8.2 |
| 2026 | 74 | 22,728 | 7.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin103",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:103",
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
