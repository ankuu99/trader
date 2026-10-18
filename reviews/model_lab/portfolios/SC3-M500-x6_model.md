# Portfolio sim `SC3-M500-x6_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹560,472 · trades 1771 · win rate 53.5% · PF 1.22 · money-weighted win % 55.0 · avg ₹316/trade · max DD ₹275,318 (38.2%) · ann. return 10.1% · Calmar 0.26 · mean utilisation 94.3% · avg held 458.3 bars

## Excluding 2020

net ₹286,774 · trades 1518 · win rate 51.8% · PF 1.14 · money-weighted win % 53.2 · avg ₹189/trade · max DD ₹201,320 (23.7%) · ann. return 5.9% · Calmar 0.25 · mean utilisation 94.3% · avg held 475.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -343 |
| STOP | 116 | -950,411 |
| TIME | 1487 | 1,000,748 |
| TRAIL | 153 | 510,478 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 41 | 76,610 | 3.9 |
| 2018 | 189 | -18,233 | 16.5 |
| 2019 | 198 | -20,070 | 17.9 |
| 2020 | 253 | 273,698 | 34.0 |
| 2021 | 187 | 154,969 | 7.3 |
| 2022 | 184 | -73,949 | 14.6 |
| 2023 | 187 | 152,896 | 5.4 |
| 2024 | 185 | 60,880 | 6.1 |
| 2025 | 189 | -27,579 | 8.5 |
| 2026 | 158 | -18,751 | 6.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x6_model",
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
  "trail_pct": 0.1,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
