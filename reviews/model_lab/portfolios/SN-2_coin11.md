# Portfolio sim `SN-2_coin11` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹813,762 · trades 1161 · win rate 54.5% · PF 1.30 · money-weighted win % 56.4 · avg ₹701/trade · max DD ₹483,931 (57.4%) · ann. return 8.6% · Calmar 0.15 · mean utilisation 96.7% · avg held 50.5 bars

## Excluding 2020

net ₹650,625 · trades 1071 · win rate 53.8% · PF 1.26 · money-weighted win % 55.7 · avg ₹607/trade · max DD ₹344,978 (57.4%) · ann. return 7.5% · Calmar 0.13 · mean utilisation 96.7% · avg held 51.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 4,996 |
| END | 14 | -17,217 |
| TARGET | 348 | 2,746,268 |
| TIME | 798 | -1,920,284 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 60 | -274,340 | 51.7 |
| 2012 | 74 | 154,834 | 22.7 |
| 2013 | 75 | -62,864 | 48.8 |
| 2014 | 87 | 326,047 | 9.0 |
| 2015 | 66 | -14,731 | 15.3 |
| 2016 | 71 | 77,518 | 16.9 |
| 2017 | 75 | 169,916 | 5.6 |
| 2018 | 67 | -173,490 | 22.4 |
| 2019 | 70 | -52,262 | 13.9 |
| 2020 | 90 | 163,138 | 35.0 |
| 2021 | 75 | 253,217 | 7.2 |
| 2022 | 69 | -103,793 | 15.4 |
| 2023 | 76 | 227,265 | 4.6 |
| 2024 | 71 | 131,644 | 6.0 |
| 2025 | 68 | 27,603 | 7.9 |
| 2026 | 67 | -35,940 | 8.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin11",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:11",
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
