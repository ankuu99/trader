# Portfolio sim `SC3-M500-x5_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹614,076 · trades 1709 · win rate 53.6% · PF 1.27 · money-weighted win % 56.0 · avg ₹359/trade · max DD ₹281,583 (39.9%) · ann. return 11.0% · Calmar 0.28 · mean utilisation 95.5% · avg held 480.7 bars

## Excluding 2020

net ₹428,946 · trades 1506 · win rate 52.7% · PF 1.23 · money-weighted win % 55.1 · avg ₹285/trade · max DD ₹189,292 (27.1%) · ann. return 8.8% · Calmar 0.33 · mean utilisation 95.5% · avg held 484.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -2,892 |
| TARGET | 139 | 1,109,486 |
| TIME | 1555 | -492,518 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 46 | 88,694 | 5.2 |
| 2018 | 181 | -95,350 | 27.1 |
| 2019 | 187 | 67,240 | 15.6 |
| 2020 | 203 | 185,131 | 39.9 |
| 2021 | 185 | 88,822 | 9.3 |
| 2022 | 188 | 43,592 | 14.8 |
| 2023 | 183 | 102,384 | 5.6 |
| 2024 | 185 | 128,493 | 7.1 |
| 2025 | 188 | 6,784 | 7.6 |
| 2026 | 163 | -1,714 | 8.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x5_coin",
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
  "target_pct": 0.2,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
