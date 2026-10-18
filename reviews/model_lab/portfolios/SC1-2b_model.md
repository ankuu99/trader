# Portfolio sim `SC1-2b_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹656,951 · trades 2004 · win rate 53.2% · PF 1.21 · money-weighted win % 54.8 · avg ₹328/trade · max DD ₹323,853 (39.5%) · ann. return 6.9% · Calmar 0.18 · mean utilisation 64.0% · avg held 19.9 bars

## Excluding 2020

net ₹789,329 · trades 1905 · win rate 53.2% · PF 1.29 · money-weighted win % 56.3 · avg ₹414/trade · max DD ₹288,986 (39.5%) · ann. return 9.1% · Calmar 0.23 · mean utilisation 64.0% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -3,512 |
| TIME | 1990 | 660,462 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 80 | -47,691 | 16.7 |
| 2012 | 108 | 174,458 | 14.8 |
| 2013 | 119 | -108,634 | 39.5 |
| 2014 | 132 | 189,384 | 6.1 |
| 2015 | 133 | -39,874 | 13.8 |
| 2016 | 142 | 71,706 | 14.1 |
| 2017 | 129 | 80,329 | 6.0 |
| 2018 | 136 | -73,937 | 17.3 |
| 2019 | 113 | 102,991 | 18.7 |
| 2020 | 99 | -132,378 | 32.5 |
| 2021 | 146 | 138,932 | 8.2 |
| 2022 | 116 | 37,939 | 9.2 |
| 2023 | 145 | 147,308 | 7.6 |
| 2024 | 146 | 76,740 | 7.2 |
| 2025 | 126 | 27,015 | 4.6 |
| 2026 | 134 | 12,664 | 7.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 18; entries from the carry-over queue: 364 (queue_bars 5).

## Spec

```json
{
  "sim_id": "SC1-2b_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
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
  "queue_bars": 5,
  "queue_max_runup": 0.02
}
```
