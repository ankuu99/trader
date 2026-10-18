# Portfolio sim `SC2-d10_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹928,501 · trades 5018 · win rate 50.0% · PF 1.17 · money-weighted win % 54.0 · avg ₹185/trade · max DD ₹266,303 (37.2%) · ann. return 9.8% · Calmar 0.26 · mean utilisation 76.0% · avg held 10.0 bars

## Excluding 2020

net ₹752,186 · trades 4691 · win rate 49.7% · PF 1.15 · money-weighted win % 53.5 · avg ₹160/trade · max DD ₹266,303 (37.2%) · ann. return 8.6% · Calmar 0.23 · mean utilisation 76.0% · avg held 10.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 11 | -90 |
| TIME | 5007 | 928,591 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 299 | -158,482 | 30.2 |
| 2012 | 334 | 142,691 | 19.5 |
| 2013 | 303 | -54,705 | 35.0 |
| 2014 | 309 | 238,590 | 7.0 |
| 2015 | 301 | -13,615 | 14.9 |
| 2016 | 306 | -66,262 | 13.9 |
| 2017 | 325 | 613,246 | 15.5 |
| 2018 | 321 | -11,321 | 8.4 |
| 2019 | 314 | 51,060 | 10.6 |
| 2020 | 327 | 176,315 | 10.6 |
| 2021 | 323 | 58,507 | 4.2 |
| 2022 | 333 | -77,075 | 11.1 |
| 2023 | 313 | 50,754 | 9.1 |
| 2024 | 305 | 87,673 | 4.5 |
| 2025 | 326 | -38,322 | 5.7 |
| 2026 | 279 | -70,552 | 6.4 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 34; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d10_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 10,
  "score_source": "ref:prod_pmin",
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
