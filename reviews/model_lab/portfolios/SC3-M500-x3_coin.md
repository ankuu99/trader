# Portfolio sim `SC3-M500-x3_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹421,234 · trades 1691 · win rate 53.5% · PF 1.18 · money-weighted win % 54.2 · avg ₹249/trade · max DD ₹503,531 (69.8%) · ann. return 7.6% · Calmar 0.11 · mean utilisation 95.5% · avg held 485.7 bars

## Excluding 2020

net ₹348,878 · trades 1493 · win rate 52.5% · PF 1.18 · money-weighted win % 54.2 · avg ₹234/trade · max DD ₹238,471 (33.1%) · ann. return 7.2% · Calmar 0.22 · mean utilisation 95.5% · avg held 489.7 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -2,386 |
| TIME | 1553 | 118,862 |
| TRAIL | 123 | 304,758 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 45 | 104,126 | 5.0 |
| 2018 | 180 | -147,591 | 31.3 |
| 2019 | 184 | -38,273 | 24.5 |
| 2020 | 198 | 72,356 | 61.4 |
| 2021 | 188 | 114,882 | 10.5 |
| 2022 | 182 | 36,654 | 20.2 |
| 2023 | 185 | 132,382 | 12.1 |
| 2024 | 185 | 101,336 | 9.2 |
| 2025 | 187 | 28,460 | 9.2 |
| 2026 | 157 | 16,903 | 9.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x3_coin",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:coin",
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
