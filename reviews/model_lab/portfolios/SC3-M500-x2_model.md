# Portfolio sim `SC3-M500-x2_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹405,289 · trades 1953 · win rate 47.2% · PF 1.14 · money-weighted win % 53.2 · avg ₹208/trade · max DD ₹385,216 (55.1%) · ann. return 7.3% · Calmar 0.13 · mean utilisation 94.3% · avg held 415.8 bars

## Excluding 2020

net ₹235,495 · trades 1694 · win rate 47.3% · PF 1.10 · money-weighted win % 52.3 · avg ₹139/trade · max DD ₹242,747 (34.7%) · ann. return 4.8% · Calmar 0.14 · mean utilisation 94.3% · avg held 425.4 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 10,321 |
| STOP | 542 | -2,262,380 |
| TIME | 1396 | 2,657,349 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 40 | 68,143 | 3.8 |
| 2018 | 223 | -117,076 | 26.7 |
| 2019 | 228 | 30,250 | 24.5 |
| 2020 | 259 | 169,795 | 49.1 |
| 2021 | 202 | 105,191 | 9.3 |
| 2022 | 213 | 20,791 | 20.4 |
| 2023 | 199 | 145,681 | 7.9 |
| 2024 | 210 | 29,345 | 7.3 |
| 2025 | 200 | -167 | 9.1 |
| 2026 | 179 | -46,664 | 8.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x2_model",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "run",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": 0.1,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
