# Portfolio sim `SC3-M500-x4_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹417,003 · trades 1618 · win rate 51.2% · PF 1.18 · money-weighted win % 54.2 · avg ₹258/trade · max DD ₹322,305 (47.6%) · ann. return 7.5% · Calmar 0.16 · mean utilisation 92.3% · avg held 490.4 bars

## Excluding 2020

net ₹302,165 · trades 1447 · win rate 50.5% · PF 1.16 · money-weighted win % 53.6 · avg ₹209/trade · max DD ₹241,728 (35.7%) · ann. return 6.2% · Calmar 0.17 · mean utilisation 92.3% · avg held 493.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -17,928 |
| TIME | 1539 | 245,644 |
| TRAIL | 64 | 189,287 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 31 | 39,639 | 5.9 |
| 2018 | 181 | -129,675 | 28.3 |
| 2019 | 180 | -8,547 | 19.7 |
| 2020 | 171 | 114,838 | 36.7 |
| 2021 | 183 | 157,438 | 9.6 |
| 2022 | 179 | 76,267 | 16.5 |
| 2023 | 179 | 98,323 | 8.1 |
| 2024 | 179 | 99,822 | 8.5 |
| 2025 | 180 | 29,566 | 6.1 |
| 2026 | 155 | -60,667 | 8.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x4_prod",
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
  "trail_pct": 0.15,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
