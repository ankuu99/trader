# Portfolio sim `SC3-M500-x4_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹357,609 · trades 1648 · win rate 50.1% · PF 1.15 · money-weighted win % 53.6 · avg ₹217/trade · max DD ₹366,916 (49.5%) · ann. return 6.4% · Calmar 0.13 · mean utilisation 94.2% · avg held 492.6 bars

## Excluding 2020

net ₹252,958 · trades 1462 · win rate 49.2% · PF 1.13 · money-weighted win % 53.0 · avg ₹173/trade · max DD ₹188,838 (25.5%) · ann. return 5.2% · Calmar 0.20 · mean utilisation 94.2% · avg held 494.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -14,688 |
| TIME | 1591 | 313,554 |
| TRAIL | 42 | 58,743 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 39 | 69,951 | 3.7 |
| 2018 | 177 | 13,437 | 16.2 |
| 2019 | 182 | -56,731 | 22.1 |
| 2020 | 186 | 104,651 | 42.1 |
| 2021 | 183 | 84,587 | 11.0 |
| 2022 | 180 | 30,526 | 14.7 |
| 2023 | 182 | 93,927 | 12.8 |
| 2024 | 181 | 77,689 | 6.0 |
| 2025 | 182 | 14,415 | 9.2 |
| 2026 | 156 | -74,845 | 9.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x4_model",
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
  "trail_pct": 0.15,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
