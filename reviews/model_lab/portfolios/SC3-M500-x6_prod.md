# Portfolio sim `SC3-M500-x6_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹400,264 · trades 1730 · win rate 51.3% · PF 1.17 · money-weighted win % 53.9 · avg ₹231/trade · max DD ₹321,036 (47.4%) · ann. return 7.2% · Calmar 0.15 · mean utilisation 92.3% · avg held 458.9 bars

## Excluding 2020

net ₹375,321 · trades 1507 · win rate 51.2% · PF 1.20 · money-weighted win % 54.5 · avg ₹249/trade · max DD ₹194,316 (28.7%) · ann. return 7.7% · Calmar 0.27 · mean utilisation 92.3% · avg held 474.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -3,506 |
| STOP | 102 | -825,133 |
| TIME | 1450 | 743,320 |
| TRAIL | 163 | 485,584 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 33 | 42,507 | 5.6 |
| 2018 | 190 | -112,583 | 25.3 |
| 2019 | 195 | 31,804 | 15.4 |
| 2020 | 223 | 24,943 | 40.7 |
| 2021 | 187 | 137,306 | 9.0 |
| 2022 | 183 | 22,545 | 18.2 |
| 2023 | 185 | 151,960 | 9.7 |
| 2024 | 190 | 145,841 | 8.6 |
| 2025 | 186 | 33,665 | 7.6 |
| 2026 | 158 | -77,723 | 9.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x6_prod",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:prod_pmin",
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
