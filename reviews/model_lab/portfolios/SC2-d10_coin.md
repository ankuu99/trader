# Portfolio sim `SC2-d10_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹540,392 · trades 5773 · win rate 49.0% · PF 1.09 · money-weighted win % 52.1 · avg ₹94/trade · max DD ₹361,959 (60.3%) · ann. return 5.7% · Calmar 0.09 · mean utilisation 87.6% · avg held 10.0 bars

## Excluding 2020

net ₹405,889 · trades 5401 · win rate 48.7% · PF 1.07 · money-weighted win % 51.7 · avg ₹75/trade · max DD ₹361,959 (60.3%) · ann. return 4.7% · Calmar 0.08 · mean utilisation 87.6% · avg held 10.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | 1,057 |
| TIME | 5759 | 539,335 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 348 | -206,112 | 36.2 |
| 2012 | 370 | 91,886 | 35.0 |
| 2013 | 367 | -82,692 | 53.5 |
| 2014 | 360 | 198,044 | 15.8 |
| 2015 | 368 | -43,707 | 21.0 |
| 2016 | 365 | 26,718 | 22.8 |
| 2017 | 356 | 187,881 | 7.5 |
| 2018 | 362 | 40,106 | 14.4 |
| 2019 | 364 | -42,743 | 16.9 |
| 2020 | 372 | 134,504 | 33.3 |
| 2021 | 364 | 124,968 | 7.3 |
| 2022 | 366 | -66,365 | 17.0 |
| 2023 | 367 | 221,891 | 7.8 |
| 2024 | 369 | 54,432 | 8.6 |
| 2025 | 370 | -25,532 | 9.8 |
| 2026 | 305 | -72,888 | 8.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 28; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d10_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 10,
  "score_source": "ref:coin",
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
