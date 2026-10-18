# Portfolio sim `SC1-2b_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹910,822 · trades 2879 · win rate 50.4% · PF 1.22 · money-weighted win % 55.0 · avg ₹316/trade · max DD ₹426,249 (45.6%) · ann. return 9.6% · Calmar 0.21 · mean utilisation 92.1% · avg held 20.0 bars

## Excluding 2020

net ₹788,106 · trades 2694 · win rate 50.0% · PF 1.21 · money-weighted win % 54.8 · avg ₹293/trade · max DD ₹290,450 (45.6%) · ann. return 9.0% · Calmar 0.20 · mean utilisation 92.1% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -10,408 |
| TIME | 2865 | 921,230 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 131 | -144,118 | 33.4 |
| 2012 | 184 | 77,244 | 31.6 |
| 2013 | 183 | -16,113 | 38.6 |
| 2014 | 183 | 256,928 | 8.4 |
| 2015 | 186 | -16,631 | 11.0 |
| 2016 | 183 | 11,162 | 13.9 |
| 2017 | 184 | 193,017 | 6.3 |
| 2018 | 185 | -48,151 | 16.1 |
| 2019 | 185 | -41,100 | 15.1 |
| 2020 | 185 | 122,716 | 33.8 |
| 2021 | 189 | 222,126 | 5.5 |
| 2022 | 183 | -19,760 | 15.1 |
| 2023 | 185 | 225,720 | 5.2 |
| 2024 | 186 | 149,422 | 5.0 |
| 2025 | 187 | 4,702 | 5.1 |
| 2026 | 160 | -66,342 | 7.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 16; entries from the carry-over queue: 1486 (queue_bars 5).

## Spec

```json
{
  "sim_id": "SC1-2b_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
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
  "queue_bars": 5,
  "queue_max_runup": 0.02
}
```
