# Portfolio sim `SN-2_coin110` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹704,606 · trades 1155 · win rate 55.2% · PF 1.25 · money-weighted win % 55.6 · avg ₹610/trade · max DD ₹496,709 (59.6%) · ann. return 7.4% · Calmar 0.12 · mean utilisation 96.7% · avg held 50.7 bars

## Excluding 2020

net ₹583,554 · trades 1065 · win rate 54.5% · PF 1.23 · money-weighted win % 55.2 · avg ₹548/trade · max DD ₹326,462 (52.0%) · ann. return 6.7% · Calmar 0.13 · mean utilisation 96.7% · avg held 51.3 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | -7,533 |
| END | 15 | -38,055 |
| TARGET | 347 | 2,753,743 |
| TIME | 792 | -2,003,548 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 58 | -210,840 | 43.8 |
| 2012 | 85 | 159,906 | 25.3 |
| 2013 | 74 | -125,293 | 50.9 |
| 2014 | 79 | 194,450 | 15.4 |
| 2015 | 63 | -31,530 | 23.3 |
| 2016 | 73 | 65,401 | 23.1 |
| 2017 | 72 | 145,969 | 6.8 |
| 2018 | 66 | -178,866 | 28.7 |
| 2019 | 68 | -232 | 19.8 |
| 2020 | 90 | 121,052 | 45.8 |
| 2021 | 81 | 299,325 | 5.4 |
| 2022 | 68 | -22,860 | 13.2 |
| 2023 | 72 | 146,470 | 4.9 |
| 2024 | 72 | 119,441 | 5.7 |
| 2025 | 68 | 36,616 | 8.1 |
| 2026 | 66 | -14,403 | 7.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin110",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:110",
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
  "sources": [],
  "delist_grace_days": 7
}
```
