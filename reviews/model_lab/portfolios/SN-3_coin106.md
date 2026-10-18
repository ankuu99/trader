# Portfolio sim `SN-3_coin106` (run `A11n_dayn_hgbq_edgez20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹787,632 · trades 987 · win rate 52.7% · PF 1.31 · money-weighted win % 56.8 · avg ₹798/trade · max DD ₹496,551 (50.7%) · ann. return 8.3% · Calmar 0.16 · mean utilisation 97.1% · avg held 59.3 bars

## Excluding 2020

net ₹625,113 · trades 919 · win rate 51.5% · PF 1.28 · money-weighted win % 56.1 · avg ₹680/trade · max DD ₹329,169 (46.5%) · ann. return 7.2% · Calmar 0.15 · mean utilisation 97.1% · avg held 59.3 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | 5,871 |
| END | 14 | 3,930 |
| TIME | 971 | 777,831 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 57 | -243,172 | 46.5 |
| 2012 | 63 | 241,837 | 27.7 |
| 2013 | 60 | -145,004 | 46.0 |
| 2014 | 61 | 320,785 | 16.1 |
| 2015 | 60 | -121,515 | 21.2 |
| 2016 | 60 | 109,640 | 21.1 |
| 2017 | 60 | 161,587 | 5.9 |
| 2018 | 60 | -216,126 | 30.4 |
| 2019 | 66 | -17,724 | 17.5 |
| 2020 | 68 | 162,519 | 33.9 |
| 2021 | 60 | 225,457 | 10.4 |
| 2022 | 61 | 10,128 | 13.6 |
| 2023 | 60 | 101,910 | 6.2 |
| 2024 | 60 | 147,383 | 6.2 |
| 2025 | 60 | 83,045 | 6.2 |
| 2026 | 71 | -33,117 | 6.4 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-3_coin106",
  "run_id": "A11n_dayn_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "coin:106",
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
