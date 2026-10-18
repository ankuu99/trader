# Portfolio sim `SC2-m25_model` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹-1,650,796 · trades 17928 · win rate 46.1% · PF 0.78 · money-weighted win % 43.7 · avg ₹-92/trade · max DD ₹1,683,136 (272.4%) · ann. return -29.6% · Calmar -0.11 · mean utilisation 50.6% · avg held 25.0 bars

## Excluding 2020

net ₹-1,494,054 · trades 16162 · win rate 45.9% · PF 0.77 · money-weighted win % 43.4 · avg ₹-92/trade · max DD ₹1,527,647 (247.3%) · ann. return -30.7% · Calmar -0.12 · mean utilisation 50.6% · avg held 25.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 11 | 1,877 |
| TIME | 17917 | -1,652,673 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 506 | -4,455 | 6.4 |
| 2018 | 2073 | -214,286 | 42.0 |
| 2019 | 2085 | -184,567 | 52.4 |
| 2020 | 1766 | -156,742 | 140.4 |
| 2021 | 1872 | -178,054 | 352.3 |
| 2022 | 1908 | -171,982 | 0.0 |
| 2023 | 2097 | -141,457 | 0.0 |
| 2024 | 1935 | -114,451 | 0.0 |
| 2025 | 2017 | -232,024 | 0.0 |
| 2026 | 1669 | -252,778 | 0.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-m25_model",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 25,
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
