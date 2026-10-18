# Portfolio sim `SC2-d10_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹416,805 · trades 4257 · win rate 49.8% · PF 1.09 · money-weighted win % 52.0 · avg ₹98/trade · max DD ₹563,478 (45.1%) · ann. return 4.4% · Calmar 0.10 · mean utilisation 64.5% · avg held 10.0 bars

## Excluding 2020

net ₹380,778 · trades 3980 · win rate 49.5% · PF 1.09 · money-weighted win % 52.0 · avg ₹96/trade · max DD ₹476,499 (38.1%) · ann. return 4.4% · Calmar 0.11 · mean utilisation 64.5% · avg held 10.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 11 | 4,979 |
| TIME | 4246 | 411,826 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 264 | -108,144 | 25.5 |
| 2012 | 268 | 194,898 | 9.8 |
| 2013 | 261 | -25,519 | 33.5 |
| 2014 | 270 | 185,223 | 4.5 |
| 2015 | 272 | 15,645 | 11.4 |
| 2016 | 262 | 18,952 | 10.0 |
| 2017 | 260 | 201,807 | 16.8 |
| 2018 | 276 | -106,228 | 15.6 |
| 2019 | 275 | -92,808 | 21.7 |
| 2020 | 277 | 36,027 | 26.7 |
| 2021 | 251 | 87,825 | 6.4 |
| 2022 | 269 | -54,310 | 11.1 |
| 2023 | 271 | 39,019 | 9.0 |
| 2024 | 266 | 36,770 | 4.6 |
| 2025 | 278 | -6,292 | 8.8 |
| 2026 | 237 | -6,059 | 9.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 47; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d10_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 10,
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
