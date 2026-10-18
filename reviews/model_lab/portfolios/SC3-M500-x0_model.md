# Portfolio sim `SC3-M500-x0_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹626,553 · trades 1630 · win rate 53.0% · PF 1.28 · money-weighted win % 56.2 · avg ₹384/trade · max DD ₹233,812 (31.3%) · ann. return 11.2% · Calmar 0.36 · mean utilisation 94.3% · avg held 498.6 bars

## Excluding 2020

net ₹476,514 · trades 1448 · win rate 52.0% · PF 1.26 · money-weighted win % 55.7 · avg ₹329/trade · max DD ₹148,088 (18.2%) · ann. return 9.8% · Calmar 0.54 · mean utilisation 94.3% · avg held 498.4 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -5,845 |
| TIME | 1615 | 632,398 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 39 | 69,951 | 3.7 |
| 2018 | 174 | 20,622 | 14.8 |
| 2019 | 179 | 35,708 | 18.2 |
| 2020 | 182 | 150,039 | 31.3 |
| 2021 | 180 | 77,163 | 9.5 |
| 2022 | 180 | 61,741 | 11.3 |
| 2023 | 180 | 81,128 | 11.1 |
| 2024 | 180 | 103,696 | 5.3 |
| 2025 | 183 | 18,287 | 7.8 |
| 2026 | 153 | 8,218 | 5.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x0_model",
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
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
