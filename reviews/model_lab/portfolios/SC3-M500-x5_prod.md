# Portfolio sim `SC3-M500-x5_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹424,057 · trades 1656 · win rate 51.8% · PF 1.18 · money-weighted win % 54.2 · avg ₹256/trade · max DD ₹392,778 (56.6%) · ann. return 7.6% · Calmar 0.13 · mean utilisation 92.3% · avg held 479.5 bars

## Excluding 2020

net ₹414,779 · trades 1481 · win rate 51.2% · PF 1.22 · money-weighted win % 54.9 · avg ₹280/trade · max DD ₹257,750 (37.1%) · ann. return 8.5% · Calmar 0.23 · mean utilisation 92.3% · avg held 483.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -8,118 |
| TARGET | 132 | 1,055,918 |
| TIME | 1509 | -623,743 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 36 | 59,445 | 5.7 |
| 2018 | 182 | -150,525 | 31.9 |
| 2019 | 181 | 514 | 18.0 |
| 2020 | 175 | 9,278 | 44.2 |
| 2021 | 189 | 154,100 | 11.7 |
| 2022 | 186 | 128,476 | 15.0 |
| 2023 | 183 | 125,847 | 10.3 |
| 2024 | 181 | 141,101 | 7.1 |
| 2025 | 185 | 30,309 | 7.1 |
| 2026 | 158 | -74,488 | 9.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x5_prod",
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
  "target_pct": 0.2,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
