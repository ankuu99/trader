# Portfolio sim `SC3-M500-x0_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹532,134 · trades 1648 · win rate 53.0% · PF 1.23 · money-weighted win % 55.2 · avg ₹323/trade · max DD ₹446,240 (62.3%) · ann. return 9.6% · Calmar 0.15 · mean utilisation 95.6% · avg held 497.9 bars

## Excluding 2020

net ₹392,927 · trades 1467 · win rate 51.9% · PF 1.21 · money-weighted win % 54.7 · avg ₹268/trade · max DD ₹243,054 (33.9%) · ann. return 8.1% · Calmar 0.24 · mean utilisation 95.6% · avg held 497.7 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 8,002 |
| TIME | 1633 | 524,132 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 45 | 103,011 | 5.1 |
| 2018 | 177 | -150,146 | 33.9 |
| 2019 | 180 | -15,130 | 20.7 |
| 2020 | 181 | 139,207 | 52.2 |
| 2021 | 180 | 175,211 | 9.7 |
| 2022 | 180 | 23,460 | 16.1 |
| 2023 | 180 | 93,556 | 12.3 |
| 2024 | 181 | 127,052 | 9.2 |
| 2025 | 185 | 41,317 | 6.8 |
| 2026 | 159 | -5,405 | 7.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x0_coin",
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
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
