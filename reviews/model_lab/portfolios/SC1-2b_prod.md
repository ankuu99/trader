# Portfolio sim `SC1-2b_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹659,383 · trades 2316 · win rate 50.9% · PF 1.20 · money-weighted win % 54.5 · avg ₹285/trade · max DD ₹556,584 (44.4%) · ann. return 7.0% · Calmar 0.16 · mean utilisation 73.9% · avg held 19.9 bars

## Excluding 2020

net ₹736,928 · trades 2207 · win rate 50.9% · PF 1.24 · money-weighted win % 55.3 · avg ₹334/trade · max DD ₹363,795 (36.9%) · ann. return 8.5% · Calmar 0.23 · mean utilisation 73.9% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -13,571 |
| TIME | 2301 | 672,954 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 97 | -159,709 | 29.6 |
| 2012 | 157 | 138,290 | 20.3 |
| 2013 | 149 | -12,120 | 36.9 |
| 2014 | 162 | 181,179 | 10.1 |
| 2015 | 142 | 32,170 | 9.9 |
| 2016 | 146 | 25,750 | 15.1 |
| 2017 | 146 | 352,118 | 19.7 |
| 2018 | 153 | -139,676 | 17.5 |
| 2019 | 147 | -50,286 | 17.1 |
| 2020 | 109 | -77,545 | 28.5 |
| 2021 | 167 | 81,805 | 7.3 |
| 2022 | 137 | 4,242 | 11.0 |
| 2023 | 150 | 159,441 | 7.6 |
| 2024 | 164 | 86,493 | 7.0 |
| 2025 | 140 | 64,764 | 4.3 |
| 2026 | 150 | -27,532 | 6.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 16; entries from the carry-over queue: 563 (queue_bars 5).

## Spec

```json
{
  "sim_id": "SC1-2b_prod",
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
  "queue_bars": 5,
  "queue_max_runup": 0.02
}
```
