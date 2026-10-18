# Portfolio sim `SC3-M500-x5_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹394,469 · trades 1686 · win rate 51.2% · PF 1.17 · money-weighted win % 53.8 · avg ₹234/trade · max DD ₹308,254 (43.7%) · ann. return 7.1% · Calmar 0.16 · mean utilisation 94.1% · avg held 480.9 bars

## Excluding 2020

net ₹181,229 · trades 1492 · win rate 50.0% · PF 1.09 · money-weighted win % 52.1 · avg ₹121/trade · max DD ₹247,438 (35.1%) · ann. return 3.7% · Calmar 0.11 · mean utilisation 94.1% · avg held 485.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -743 |
| TARGET | 132 | 1,054,771 |
| TIME | 1540 | -659,559 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 42 | 84,235 | 3.6 |
| 2018 | 181 | -45,503 | 20.1 |
| 2019 | 189 | -61,338 | 29.8 |
| 2020 | 194 | 213,240 | 35.9 |
| 2021 | 187 | 80,702 | 8.9 |
| 2022 | 185 | 36,190 | 11.6 |
| 2023 | 183 | 64,852 | 16.2 |
| 2024 | 179 | 100,334 | 5.5 |
| 2025 | 189 | 9,679 | 10.1 |
| 2026 | 157 | -87,922 | 9.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x5_model",
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
  "target_pct": 0.2,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
