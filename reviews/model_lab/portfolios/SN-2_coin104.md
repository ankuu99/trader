# Portfolio sim `SN-2_coin104` (run `A01n_dayn_logit_t1z5`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹773,564 · trades 1161 · win rate 53.7% · PF 1.29 · money-weighted win % 56.3 · avg ₹666/trade · max DD ₹392,287 (34.9%) · ann. return 8.2% · Calmar 0.23 · mean utilisation 96.8% · avg held 50.5 bars

## Excluding 2020

net ₹572,466 · trades 1071 · win rate 52.3% · PF 1.23 · money-weighted win % 55.2 · avg ₹535/trade · max DD ₹290,576 (34.7%) · ann. return 6.6% · Calmar 0.19 · mean utilisation 96.8% · avg held 51.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 2 | 2,069 |
| END | 15 | -27,088 |
| TARGET | 339 | 2,688,014 |
| TIME | 805 | -1,889,432 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 57 | -165,962 | 34.7 |
| 2012 | 85 | 195,835 | 19.8 |
| 2013 | 83 | 32,458 | 28.3 |
| 2014 | 83 | 319,747 | 7.9 |
| 2015 | 64 | -30,193 | 15.7 |
| 2016 | 72 | 26,902 | 14.4 |
| 2017 | 68 | 135,481 | 4.9 |
| 2018 | 72 | -104,489 | 14.9 |
| 2019 | 72 | -101,646 | 19.9 |
| 2020 | 90 | 201,098 | 23.6 |
| 2021 | 74 | 206,643 | 5.5 |
| 2022 | 67 | -22,602 | 9.8 |
| 2023 | 68 | 104,510 | 5.2 |
| 2024 | 73 | 103,623 | 4.7 |
| 2025 | 66 | -50,543 | 5.9 |
| 2026 | 67 | -77,298 | 9.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-2_coin104",
  "run_id": "A01n_dayn_logit_t1z5",
  "hold_bars": 60,
  "score_source": "coin:104",
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
