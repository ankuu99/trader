# Portfolio sim `SC2-m25_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹-2,027,646 · trades 30346 · win rate 44.5% · PF 0.81 · money-weighted win % 44.8 · avg ₹-67/trade · max DD ₹2,086,933 (323.3%) · ann. return -36.4% · Calmar -0.11 · mean utilisation 84.7% · avg held 25.0 bars

## Excluding 2020

net ₹-1,888,605 · trades 26926 · win rate 44.1% · PF 0.79 · money-weighted win % 44.2 · avg ₹-70/trade · max DD ₹1,948,860 (301.9%) · ann. return -38.8% · Calmar -0.13 · mean utilisation 84.7% · avg held 25.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -410 |
| TIME | 30331 | -2,027,236 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 832 | 8,804 | 8.5 |
| 2018 | 3344 | -401,953 | 69.5 |
| 2019 | 3310 | -333,274 | 176.2 |
| 2020 | 3420 | -139,041 | 0.0 |
| 2021 | 3350 | -110,162 | 0.0 |
| 2022 | 3366 | -300,677 | 0.0 |
| 2023 | 3330 | -18,019 | 0.0 |
| 2024 | 3352 | -242,703 | 0.0 |
| 2025 | 3386 | -272,189 | 0.0 |
| 2026 | 2656 | -218,432 | 0.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 43; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-m25_coin",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 25,
  "score_source": "ref:coin",
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
