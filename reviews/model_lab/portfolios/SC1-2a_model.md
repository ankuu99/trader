# Portfolio sim `SC1-2a_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹618,444 · trades 1988 · win rate 53.1% · PF 1.20 · money-weighted win % 54.6 · avg ₹311/trade · max DD ₹323,853 (43.1%) · ann. return 6.5% · Calmar 0.15 · mean utilisation 63.4% · avg held 19.9 bars

## Excluding 2020

net ₹750,822 · trades 1889 · win rate 53.1% · PF 1.27 · money-weighted win % 56.0 · avg ₹397/trade · max DD ₹312,115 (43.1%) · ann. return 8.6% · Calmar 0.20 · mean utilisation 63.4% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -3,512 |
| TIME | 1974 | 621,956 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 79 | -40,522 | 16.5 |
| 2012 | 108 | 160,556 | 14.5 |
| 2013 | 117 | -150,262 | 43.1 |
| 2014 | 129 | 186,653 | 6.6 |
| 2015 | 131 | -42,811 | 14.2 |
| 2016 | 141 | 73,187 | 15.2 |
| 2017 | 129 | 68,824 | 7.2 |
| 2018 | 135 | -54,602 | 15.9 |
| 2019 | 111 | 98,382 | 19.6 |
| 2020 | 99 | -132,378 | 34.2 |
| 2021 | 146 | 138,119 | 8.7 |
| 2022 | 115 | 22,314 | 9.9 |
| 2023 | 145 | 164,923 | 7.3 |
| 2024 | 143 | 97,356 | 7.4 |
| 2025 | 126 | 13,689 | 5.1 |
| 2026 | 134 | 15,014 | 8.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 18; entries from the carry-over queue: 306 (queue_bars 3).

## Spec

```json
{
  "sim_id": "SC1-2a_model",
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
  "queue_bars": 3,
  "queue_max_runup": 0.02
}
```
