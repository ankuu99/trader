# Portfolio sim `SC3-M500-x4_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹598,870 · trades 1665 · win rate 52.2% · PF 1.27 · money-weighted win % 56.0 · avg ₹360/trade · max DD ₹445,346 (62.1%) · ann. return 10.7% · Calmar 0.17 · mean utilisation 95.5% · avg held 493.4 bars

## Excluding 2020

net ₹457,371 · trades 1478 · win rate 51.2% · PF 1.25 · money-weighted win % 55.6 · avg ₹309/trade · max DD ₹255,101 (35.6%) · ann. return 9.4% · Calmar 0.26 · mean utilisation 95.5% · avg held 494.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -2,461 |
| TIME | 1601 | 577,580 |
| TRAIL | 49 | 23,751 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 45 | 103,011 | 5.1 |
| 2018 | 179 | -169,746 | 34.4 |
| 2019 | 180 | -236 | 23.3 |
| 2020 | 187 | 141,499 | 51.2 |
| 2021 | 181 | 218,954 | 9.1 |
| 2022 | 185 | 18,734 | 14.3 |
| 2023 | 182 | 136,622 | 8.5 |
| 2024 | 184 | 130,456 | 6.8 |
| 2025 | 184 | 23,193 | 7.3 |
| 2026 | 158 | -3,615 | 8.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x4_coin",
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
  "trail_pct": 0.15,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
