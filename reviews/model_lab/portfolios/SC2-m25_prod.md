# Portfolio sim `SC2-m25_prod` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹-1,434,572 · trades 15908 · win rate 46.3% · PF 0.79 · money-weighted win % 44.2 · avg ₹-90/trade · max DD ₹1,463,502 (235.6%) · ann. return -25.7% · Calmar -0.11 · mean utilisation 45.6% · avg held 25.0 bars

## Excluding 2020

net ₹-1,268,166 · trades 14046 · win rate 46.1% · PF 0.78 · money-weighted win % 44.0 · avg ₹-90/trade · max DD ₹1,297,222 (208.9%) · ann. return -26.1% · Calmar -0.12 · mean utilisation 45.6% · avg held 25.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 9 | 1,502 |
| TIME | 15899 | -1,436,074 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 401 | -3,035 | 6.6 |
| 2018 | 1721 | -267,484 | 50.3 |
| 2019 | 1867 | -142,304 | 54.0 |
| 2020 | 1862 | -166,406 | 133.1 |
| 2021 | 1642 | -124,260 | 194.2 |
| 2022 | 1650 | -198,130 | 0.0 |
| 2023 | 1737 | -62,373 | 0.0 |
| 2024 | 1628 | -75,868 | 0.0 |
| 2025 | 1886 | -176,695 | 0.0 |
| 2026 | 1514 | -218,018 | 0.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 27; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-m25_prod",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 25,
  "score_source": "ref:prod_pmin",
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
