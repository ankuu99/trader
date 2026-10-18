# Portfolio sim `SC3-M500-x2_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹350,844 · trades 1930 · win rate 46.9% · PF 1.13 · money-weighted win % 52.9 · avg ₹182/trade · max DD ₹598,367 (83.2%) · ann. return 6.3% · Calmar 0.08 · mean utilisation 95.5% · avg held 425.4 bars

## Excluding 2020

net ₹364,981 · trades 1650 · win rate 48.3% · PF 1.17 · money-weighted win % 53.8 · avg ₹221/trade · max DD ₹280,089 (39.0%) · ann. return 7.5% · Calmar 0.19 · mean utilisation 95.5% · avg held 440.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 3,277 |
| STOP | 506 | -2,094,633 |
| TIME | 1409 | 2,442,199 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 45 | 98,951 | 4.8 |
| 2018 | 216 | -163,524 | 33.6 |
| 2019 | 209 | -47,058 | 27.3 |
| 2020 | 280 | -14,137 | 76.7 |
| 2021 | 202 | 140,754 | 14.5 |
| 2022 | 209 | 792 | 23.0 |
| 2023 | 190 | 179,251 | 11.0 |
| 2024 | 205 | 57,886 | 9.4 |
| 2025 | 200 | 53,083 | 10.5 |
| 2026 | 174 | 44,847 | 6.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 2; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x2_coin",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:coin",
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
