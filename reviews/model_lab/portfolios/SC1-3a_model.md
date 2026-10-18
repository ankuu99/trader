# Portfolio sim `SC1-3a_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹772,546 · trades 2240 · win rate 51.7% · PF 1.22 · money-weighted win % 55.0 · avg ₹345/trade · max DD ₹265,893 (34.5%) · ann. return 8.2% · Calmar 0.24 · mean utilisation 71.5% · avg held 19.9 bars

## Excluding 2020

net ₹688,463 · trades 2098 · win rate 51.3% · PF 1.22 · money-weighted win % 54.9 · avg ₹328/trade · max DD ₹239,430 (34.5%) · ann. return 7.9% · Calmar 0.23 · mean utilisation 71.5% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | 2,817 |
| TIME | 2226 | 769,729 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 122 | -168,568 | 33.1 |
| 2012 | 143 | 254,157 | 11.4 |
| 2013 | 147 | 3,435 | 34.3 |
| 2014 | 122 | 120,299 | 7.4 |
| 2015 | 150 | 10,509 | 8.9 |
| 2016 | 140 | 91,315 | 10.4 |
| 2017 | 135 | 296,781 | 17.0 |
| 2018 | 148 | -112,351 | 14.7 |
| 2019 | 146 | 75,364 | 12.7 |
| 2020 | 142 | 84,083 | 19.9 |
| 2021 | 122 | 76,100 | 6.4 |
| 2022 | 146 | -58,608 | 10.5 |
| 2023 | 145 | 88,654 | 5.9 |
| 2024 | 147 | 35,949 | 4.1 |
| 2025 | 146 | 14,982 | 4.8 |
| 2026 | 139 | -39,554 | 7.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 23; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-3a_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "run",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 1,
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
