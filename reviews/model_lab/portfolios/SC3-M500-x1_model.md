# Portfolio sim `SC3-M500-x1_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹515,305 · trades 1687 · win rate 52.0% · PF 1.21 · money-weighted win % 54.7 · avg ₹305/trade · max DD ₹381,446 (53.1%) · ann. return 9.2% · Calmar 0.17 · mean utilisation 94.2% · avg held 481.7 bars

## Excluding 2020

net ₹341,157 · trades 1484 · win rate 51.6% · PF 1.17 · money-weighted win % 53.9 · avg ₹230/trade · max DD ₹217,839 (30.3%) · ann. return 7.0% · Calmar 0.23 · mean utilisation 94.2% · avg held 486.6 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -591 |
| STOP | 107 | -867,045 |
| TIME | 1565 | 1,382,941 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 39 | 69,951 | 3.7 |
| 2018 | 181 | -27,244 | 19.2 |
| 2019 | 190 | -2,629 | 25.3 |
| 2020 | 203 | 174,149 | 48.7 |
| 2021 | 180 | 107,341 | 9.1 |
| 2022 | 181 | 83,819 | 11.9 |
| 2023 | 186 | 92,433 | 9.8 |
| 2024 | 183 | 46,936 | 5.1 |
| 2025 | 187 | -5,954 | 8.7 |
| 2026 | 157 | -23,496 | 6.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x1_model",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "run",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": 0.2,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
