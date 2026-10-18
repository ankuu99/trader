# Portfolio sim `SC1-2a_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹704,796 · trades 2285 · win rate 50.9% · PF 1.21 · money-weighted win % 54.8 · avg ₹308/trade · max DD ₹519,641 (40.9%) · ann. return 7.4% · Calmar 0.18 · mean utilisation 72.9% · avg held 19.9 bars

## Excluding 2020

net ₹774,014 · trades 2181 · win rate 50.8% · PF 1.25 · money-weighted win % 55.6 · avg ₹355/trade · max DD ₹354,480 (37.8%) · ann. return 8.9% · Calmar 0.23 · mean utilisation 72.9% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -12,713 |
| TIME | 2270 | 717,509 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 96 | -169,035 | 31.1 |
| 2012 | 155 | 141,437 | 20.1 |
| 2013 | 148 | -17,631 | 37.5 |
| 2014 | 161 | 196,984 | 9.2 |
| 2015 | 140 | 27,673 | 9.5 |
| 2016 | 142 | 37,371 | 15.1 |
| 2017 | 143 | 355,730 | 19.3 |
| 2018 | 152 | -134,409 | 16.5 |
| 2019 | 146 | -18,012 | 16.1 |
| 2020 | 104 | -69,218 | 27.1 |
| 2021 | 166 | 79,801 | 7.5 |
| 2022 | 133 | -7,825 | 10.8 |
| 2023 | 150 | 172,986 | 7.3 |
| 2024 | 164 | 87,324 | 6.6 |
| 2025 | 137 | 68,509 | 4.5 |
| 2026 | 148 | -46,890 | 6.4 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 18; entries from the carry-over queue: 452 (queue_bars 3).

## Spec

```json
{
  "sim_id": "SC1-2a_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:prod_pmin",
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
