# Portfolio sim `SC3-M500-x2_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹283,766 · trades 1910 · win rate 46.6% · PF 1.10 · money-weighted win % 52.3 · avg ₹149/trade · max DD ₹331,023 (48.4%) · ann. return 5.1% · Calmar 0.11 · mean utilisation 92.3% · avg held 415.9 bars

## Excluding 2020

net ₹283,174 · trades 1679 · win rate 47.3% · PF 1.12 · money-weighted win % 52.8 · avg ₹169/trade · max DD ₹200,017 (29.2%) · ann. return 5.8% · Calmar 0.20 · mean utilisation 92.3% · avg held 426.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 10,721 |
| STOP | 516 | -2,152,334 |
| TIME | 1379 | 2,425,379 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 36 | 45,006 | 5.3 |
| 2018 | 226 | -141,528 | 27.8 |
| 2019 | 219 | 80,010 | 19.7 |
| 2020 | 231 | 592 | 44.7 |
| 2021 | 208 | 145,852 | 9.5 |
| 2022 | 209 | 36,924 | 20.1 |
| 2023 | 192 | 92,925 | 9.5 |
| 2024 | 203 | 68,744 | 8.4 |
| 2025 | 205 | 8,921 | 9.4 |
| 2026 | 181 | -53,681 | 11.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x2_prod",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": 0.1,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
