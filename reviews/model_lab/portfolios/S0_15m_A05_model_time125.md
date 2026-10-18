# Portfolio sim `S0_15m_A05_model_time125` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹-477,157 · trades 6007 · win rate 47.5% · PF 0.90 · money-weighted win % 47.4 · avg ₹-79/trade · max DD ₹559,273 (84.2%) · ann. return -8.6% · Calmar -0.10 · mean utilisation 86.6% · avg held 124.9 bars

## Excluding 2020

net ₹-481,154 · trades 5378 · win rate 47.2% · PF 0.88 · money-weighted win % 46.9 · avg ₹-89/trade · max DD ₹563,612 (84.9%) · ann. return -9.9% · Calmar -0.12 · mean utilisation 86.6% · avg held 124.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 5,826 |
| TIME | 5992 | -482,983 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 159 | 50,545 | 5.2 |
| 2018 | 674 | -127,947 | 30.8 |
| 2019 | 670 | -58,988 | 31.0 |
| 2020 | 629 | 3,997 | 65.1 |
| 2021 | 657 | -63,083 | 23.7 |
| 2022 | 664 | -125,978 | 52.3 |
| 2023 | 686 | 70,620 | 41.1 |
| 2024 | 646 | -3,565 | 19.3 |
| 2025 | 669 | -106,510 | 35.3 |
| 2026 | 553 | -116,248 | 57.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 0.

## Spec

```json
{
  "sim_id": "S0_15m_A05_model_time125",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 125,
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
  "exclusions": []
}
```
