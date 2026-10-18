# Portfolio sim `SC3-M500-x3_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹438,837 · trades 1642 · win rate 51.5% · PF 1.20 · money-weighted win % 54.5 · avg ₹267/trade · max DD ₹296,809 (43.5%) · ann. return 7.9% · Calmar 0.18 · mean utilisation 92.2% · avg held 482.8 bars

## Excluding 2020

net ₹424,740 · trades 1472 · win rate 51.0% · PF 1.23 · money-weighted win % 55.2 · avg ₹289/trade · max DD ₹198,764 (29.1%) · ann. return 8.7% · Calmar 0.30 · mean utilisation 92.2% · avg held 485.6 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -7,594 |
| TIME | 1495 | 54,506 |
| TRAIL | 133 | 391,925 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 32 | 43,517 | 5.6 |
| 2018 | 185 | -103,748 | 23.3 |
| 2019 | 185 | 27,753 | 17.1 |
| 2020 | 170 | 14,097 | 37.0 |
| 2021 | 187 | 134,095 | 8.9 |
| 2022 | 182 | 97,000 | 16.3 |
| 2023 | 182 | 135,187 | 13.7 |
| 2024 | 180 | 133,802 | 8.2 |
| 2025 | 184 | 28,590 | 6.0 |
| 2026 | 155 | -71,455 | 9.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x3_prod",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:prod_pmin",
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
