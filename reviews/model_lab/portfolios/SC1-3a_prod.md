# Portfolio sim `SC1-3a_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹872,121 · trades 2460 · win rate 51.5% · PF 1.24 · money-weighted win % 55.3 · avg ₹355/trade · max DD ₹241,471 (40.2%) · ann. return 9.2% · Calmar 0.23 · mean utilisation 78.6% · avg held 20.0 bars

## Excluding 2020

net ₹761,865 · trades 2312 · win rate 51.3% · PF 1.22 · money-weighted win % 55.0 · avg ₹330/trade · max DD ₹241,471 (40.2%) · ann. return 8.7% · Calmar 0.22 · mean utilisation 78.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 10 | -5,236 |
| TIME | 2450 | 877,357 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 141 | -221,015 | 40.2 |
| 2012 | 168 | 207,188 | 21.1 |
| 2013 | 163 | -45,072 | 38.9 |
| 2014 | 146 | 188,225 | 4.8 |
| 2015 | 139 | -35,408 | 13.5 |
| 2016 | 144 | 2,916 | 13.5 |
| 2017 | 155 | 360,859 | 21.3 |
| 2018 | 156 | 330 | 8.8 |
| 2019 | 160 | 68,192 | 13.2 |
| 2020 | 148 | 110,255 | 19.0 |
| 2021 | 161 | 53,625 | 5.6 |
| 2022 | 174 | -32,249 | 12.5 |
| 2023 | 149 | 140,558 | 8.0 |
| 2024 | 156 | 32,428 | 5.7 |
| 2025 | 155 | 29,179 | 4.8 |
| 2026 | 145 | 12,108 | 4.4 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 19; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-3a_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:prod_pmin",
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
