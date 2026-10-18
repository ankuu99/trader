# Portfolio sim `SC3-P60-x2_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹413,952 · trades 1502 · win rate 38.7% · PF 1.12 · money-weighted win % 52.8 · avg ₹276/trade · max DD ₹493,256 (53.8%) · ann. return 4.4% · Calmar 0.08 · mean utilisation 94.9% · avg held 38.5 bars

## Excluding 2020

net ₹271,339 · trades 1392 · win rate 38.6% · PF 1.09 · money-weighted win % 52.0 · avg ₹195/trade · max DD ₹462,327 (51.7%) · ann. return 3.1% · Calmar 0.06 · mean utilisation 94.9% · avg held 38.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 5,113 |
| STOP | 784 | -3,252,536 |
| TIME | 703 | 3,661,374 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 123 | -282,780 | 44.6 |
| 2012 | 80 | 147,673 | 31.6 |
| 2013 | 117 | -105,442 | 43.3 |
| 2014 | 82 | 140,169 | 14.4 |
| 2015 | 101 | 86,512 | 16.7 |
| 2016 | 90 | 11,841 | 16.6 |
| 2017 | 81 | 145,058 | 19.5 |
| 2018 | 99 | -171,647 | 22.7 |
| 2019 | 112 | -54,833 | 32.0 |
| 2020 | 110 | 142,613 | 27.0 |
| 2021 | 80 | 136,919 | 9.1 |
| 2022 | 93 | -67,316 | 20.2 |
| 2023 | 84 | 58,622 | 17.8 |
| 2024 | 83 | 130,167 | 9.2 |
| 2025 | 83 | 110,674 | 8.3 |
| 2026 | 84 | -14,278 | 10.4 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x2_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
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
