# Portfolio sim `SC4-b_model_P` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹576,144 · trades 520 · win rate 52.9% · PF 1.45 · money-weighted win % 59.2 · avg ₹1,108/trade · max DD ₹209,362 (45.7%) · ann. return 11.4% · Calmar 0.25 · mean utilisation 96.1% · avg held 59.4 bars

## Excluding 2020

net ₹467,615 · trades 487 · win rate 52.2% · PF 1.39 · money-weighted win % 58.1 · avg ₹960/trade · max DD ₹189,590 (45.7%) · ann. return 10.1% · Calmar 0.22 · mean utilisation 96.1% · avg held 59.4 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 8 | 8,025 |
| TIME | 512 | 568,119 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 26 | -60,318 | 31.3 |
| 2012 | 36 | -2,615 | 30.2 |
| 2013 | 34 | -20,393 | 36.5 |
| 2014 | 29 | 48,137 | 15.2 |
| 2015 | 35 | 29,509 | 16.6 |
| 2016 | 32 | 47,731 | 14.5 |
| 2017 | 32 | 281,424 | 28.3 |
| 2018 | 32 | -79,323 | 20.0 |
| 2019 | 32 | -29,735 | 14.5 |
| 2020 | 33 | 108,529 | 19.0 |
| 2021 | 32 | 158,017 | 6.9 |
| 2022 | 32 | -10,707 | 10.5 |
| 2023 | 32 | 47,680 | 7.9 |
| 2024 | 34 | 71,892 | 5.2 |
| 2025 | 35 | 4,449 | 5.2 |
| 2026 | 34 | -18,134 | 6.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC4-b_model_P",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:prod_pmin",
  "capital": 320000,
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
  "queue_max_runup": null,
  "sources": []
}
```
