# Portfolio sim `SC3-M500-x6_coin` (run `A05_15m_logit_t1z5`, tf 15m)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹427,350 · trades 1755 · win rate 52.6% · PF 1.17 · money-weighted win % 54.0 · avg ₹244/trade · max DD ₹546,814 (75.8%) · ann. return 7.7% · Calmar 0.10 · mean utilisation 95.5% · avg held 467.7 bars

## Excluding 2020

net ₹374,646 · trades 1517 · win rate 52.3% · PF 1.19 · money-weighted win % 54.3 · avg ₹247/trade · max DD ₹247,639 (34.3%) · ann. return 7.7% · Calmar 0.22 · mean utilisation 95.5% · avg held 480.2 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -6,970 |
| STOP | 94 | -768,398 |
| TIME | 1506 | 863,849 |
| TRAIL | 140 | 338,869 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2017 | 45 | 104,126 | 5.0 |
| 2018 | 183 | -148,976 | 33.7 |
| 2019 | 190 | -48,290 | 24.3 |
| 2020 | 238 | 52,703 | 66.2 |
| 2021 | 189 | 178,254 | 11.3 |
| 2022 | 188 | -36,667 | 26.3 |
| 2023 | 186 | 158,963 | 5.6 |
| 2024 | 188 | 99,643 | 8.5 |
| 2025 | 189 | 50,733 | 10.4 |
| 2026 | 159 | 16,860 | 8.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 6; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-M500-x6_coin",
  "run_id": "A05_15m_logit_t1z5",
  "hold_bars": 500,
  "score_source": "ref:coin",
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
