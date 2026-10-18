# Portfolio sim `SC3-M500-x3_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹755,552 · trades 1676 · win rate 54.5% · PF 1.35 · money-weighted win % 57.4 · avg ₹451/trade · max DD ₹267,776 (36.9%) · ann. return 13.6% · Calmar 0.37 · mean utilisation 94.3% · avg held 484.6 bars

## Excluding 2020

net ₹516,916 · trades 1478 · win rate 52.8% · PF 1.28 · money-weighted win % 56.2 · avg ₹350/trade · max DD ₹166,856 (23.0%) · ann. return 10.6% · Calmar 0.46 · mean utilisation 94.3% · avg held 489.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 2,917 |
| TIME | 1537 | 374,078 |
| TRAIL | 124 | 378,556 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 41 | 76,610 | 3.9 |
| 2018 | 179 | 17,339 | 14.3 |
| 2019 | 185 | -33,330 | 21.4 |
| 2020 | 198 | 238,636 | 35.7 |
| 2021 | 186 | 123,371 | 7.3 |
| 2022 | 184 | 66,149 | 10.7 |
| 2023 | 181 | 174,090 | 4.2 |
| 2024 | 180 | 64,781 | 4.5 |
| 2025 | 187 | 16,229 | 7.9 |
| 2026 | 155 | 11,676 | 3.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x3_model",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "run",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": 0.1,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
