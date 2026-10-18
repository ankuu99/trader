# Portfolio sim `SC3-M500-x1_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹327,740 · trades 1652 · win rate 50.3% · PF 1.13 · money-weighted win % 53.2 · avg ₹198/trade · max DD ₹360,677 (53.6%) · ann. return 5.9% · Calmar 0.11 · mean utilisation 92.5% · avg held 481.4 bars

## Excluding 2020

net ₹242,013 · trades 1462 · win rate 50.3% · PF 1.12 · money-weighted win % 52.9 · avg ₹166/trade · max DD ₹229,547 (34.1%) · ann. return 5.0% · Calmar 0.15 · mean utilisation 92.5% · avg held 487.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -2,059 |
| STOP | 105 | -849,858 |
| TIME | 1532 | 1,179,657 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 32 | 38,630 | 5.9 |
| 2018 | 185 | -149,303 | 33.3 |
| 2019 | 180 | 21,467 | 19.6 |
| 2020 | 190 | 85,727 | 44.6 |
| 2021 | 181 | 138,719 | 10.3 |
| 2022 | 181 | 88,856 | 16.9 |
| 2023 | 183 | 66,300 | 13.0 |
| 2024 | 180 | 113,980 | 8.4 |
| 2025 | 184 | 11,380 | 7.4 |
| 2026 | 156 | -88,014 | 10.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 4; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x1_prod",
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
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
