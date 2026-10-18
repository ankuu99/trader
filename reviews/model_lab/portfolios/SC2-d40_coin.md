# Portfolio sim `SC2-d40_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹986,835 · trades 1470 · win rate 52.2% · PF 1.34 · money-weighted win % 57.2 · avg ₹671/trade · max DD ₹410,336 (42.7%) · ann. return 10.4% · Calmar 0.24 · mean utilisation 96.1% · avg held 39.7 bars

## Excluding 2020

net ₹927,551 · trades 1378 · win rate 52.0% · PF 1.35 · money-weighted win % 57.5 · avg ₹673/trade · max DD ₹280,993 (42.7%) · ann. return 10.6% · Calmar 0.25 · mean utilisation 96.1% · avg held 39.7 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -681 |
| TIME | 1455 | 987,516 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 85 | -158,356 | 36.1 |
| 2012 | 95 | 160,340 | 21.8 |
| 2013 | 90 | -59,956 | 42.7 |
| 2014 | 90 | 420,450 | 7.6 |
| 2015 | 90 | 55,199 | 7.2 |
| 2016 | 90 | 13,477 | 12.2 |
| 2017 | 94 | 184,155 | 4.8 |
| 2018 | 95 | -44,848 | 12.2 |
| 2019 | 94 | -60,999 | 12.3 |
| 2020 | 92 | 59,284 | 25.5 |
| 2021 | 90 | 78,168 | 5.3 |
| 2022 | 90 | -39,397 | 14.7 |
| 2023 | 98 | 147,691 | 4.0 |
| 2024 | 97 | 177,553 | 5.7 |
| 2025 | 90 | 27,542 | 6.4 |
| 2026 | 90 | 26,533 | 4.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 6; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d40_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 40,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
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
