# Portfolio sim `SC1-1a_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹695,509 · trades 1330 · win rate 50.1% · PF 1.17 · money-weighted win % 53.9 · avg ₹523/trade · max DD ₹642,834 (61.1%) · ann. return 7.3% · Calmar 0.12 · mean utilisation 85.6% · avg held 20.0 bars

## Excluding 2020

net ₹568,692 · trades 1241 · win rate 49.3% · PF 1.15 · money-weighted win % 53.6 · avg ₹458/trade · max DD ₹366,029 (47.6%) · ann. return 6.5% · Calmar 0.14 · mean utilisation 85.6% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 6 | 19,484 |
| TIME | 1324 | 676,026 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 60 | -131,146 | 33.2 |
| 2012 | 87 | 208,539 | 16.5 |
| 2013 | 84 | -58,574 | 47.6 |
| 2014 | 84 | 198,269 | 8.1 |
| 2015 | 85 | 17,956 | 9.4 |
| 2016 | 85 | 20,697 | 13.3 |
| 2017 | 85 | 152,719 | 5.9 |
| 2018 | 85 | -115,466 | 18.8 |
| 2019 | 84 | -191,945 | 22.7 |
| 2020 | 89 | 126,817 | 43.8 |
| 2021 | 85 | 258,348 | 7.2 |
| 2022 | 87 | -65,315 | 17.2 |
| 2023 | 85 | 181,519 | 5.8 |
| 2024 | 85 | 101,353 | 6.2 |
| 2025 | 86 | 4,081 | 7.5 |
| 2026 | 74 | -12,343 | 9.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-1a_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 80000,
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
  "queue_bars": 0,
  "queue_max_runup": null
}
```
