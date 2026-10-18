# Portfolio sim `SC2-d5_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹-73,894 · trades 4826 · win rate 47.8% · PF 0.98 · money-weighted win % 49.6 · avg ₹-15/trade · max DD ₹368,076 (44.4%) · ann. return -0.8% · Calmar -0.02 · mean utilisation 32.5% · avg held 5.0 bars

## Excluding 2020

net ₹-122,445 · trades 4507 · win rate 47.6% · PF 0.97 · money-weighted win % 49.2 · avg ₹-27/trade · max DD ₹381,282 (45.9%) · ann. return -1.4% · Calmar -0.03 · mean utilisation 32.5% · avg held 5.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 6 | -1,490 |
| TIME | 4820 | -72,404 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 311 | -120,624 | 20.9 |
| 2012 | 301 | 110,543 | 8.1 |
| 2013 | 300 | -10,888 | 22.0 |
| 2014 | 307 | 89,012 | 7.4 |
| 2015 | 302 | -28,482 | 12.7 |
| 2016 | 290 | -10,093 | 8.0 |
| 2017 | 293 | 65,772 | 19.0 |
| 2018 | 312 | -71,422 | 14.6 |
| 2019 | 315 | -59,266 | 27.3 |
| 2020 | 319 | 48,551 | 23.0 |
| 2021 | 284 | 7,137 | 5.8 |
| 2022 | 301 | -56,975 | 14.8 |
| 2023 | 310 | -16,196 | 12.2 |
| 2024 | 301 | 21,392 | 5.5 |
| 2025 | 315 | 5,803 | 7.5 |
| 2026 | 265 | -48,158 | 10.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 47; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d5_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 5,
  "score_source": "run",
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
