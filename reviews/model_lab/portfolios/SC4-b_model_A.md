# Portfolio sim `SC4-b_model_A` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹154,889 · trades 1317 · win rate 51.5% · PF 1.07 · money-weighted win % 51.7 · avg ₹118/trade · max DD ₹240,918 (54.1%) · ann. return 3.5% · Calmar 0.06 · mean utilisation 90.3% · avg held 19.9 bars

## Excluding 2020

net ₹116,008 · trades 1234 · win rate 51.4% · PF 1.06 · money-weighted win % 51.4 · avg ₹94/trade · max DD ₹188,885 (48.6%) · ann. return 2.9% · Calmar 0.06 · mean utilisation 90.3% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 7 | -4,243 |
| TIME | 1310 | 159,132 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 77 | -59,806 | 32.4 |
| 2012 | 84 | 118,363 | 13.3 |
| 2013 | 85 | -18,964 | 48.4 |
| 2014 | 82 | 48,314 | 11.6 |
| 2015 | 85 | -22,871 | 18.8 |
| 2016 | 84 | 30,455 | 19.0 |
| 2017 | 83 | 47,852 | 7.0 |
| 2018 | 84 | -83,094 | 25.8 |
| 2019 | 82 | -22,880 | 27.7 |
| 2020 | 83 | 38,881 | 38.3 |
| 2021 | 75 | 61,816 | 9.6 |
| 2022 | 85 | -46,278 | 23.1 |
| 2023 | 83 | 57,254 | 14.1 |
| 2024 | 86 | 25,366 | 9.4 |
| 2025 | 84 | -1,398 | 9.6 |
| 2026 | 75 | -18,119 | 12.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 14; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC4-b_model_A",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "run",
  "capital": 280000,
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
