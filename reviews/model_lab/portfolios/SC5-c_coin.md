# Portfolio sim `SC5-c_coin` (run `A11_day_hgbq_edgez20`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹960,977 · trades 1161 · win rate 55.5% · PF 1.38 · money-weighted win % 58.0 · avg ₹828/trade · max DD ₹448,236 (37.3%) · ann. return 10.1% · Calmar 0.27 · mean utilisation 96.8% · avg held 50.3 bars

## Excluding 2020

net ₹848,344 · trades 1071 · win rate 54.9% · PF 1.38 · money-weighted win % 57.9 · avg ₹792/trade · max DD ₹270,946 (36.8%) · ann. return 9.7% · Calmar 0.26 · mean utilisation 96.8% · avg held 50.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -19,040 |
| TARGET | 346 | 2,715,689 |
| TIME | 801 | -1,735,673 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 59 | -104,517 | 31.5 |
| 2012 | 71 | 125,031 | 18.8 |
| 2013 | 75 | -38,898 | 36.8 |
| 2014 | 83 | 273,644 | 10.0 |
| 2015 | 68 | -12,215 | 14.0 |
| 2016 | 78 | 87,323 | 13.5 |
| 2017 | 77 | 229,678 | 4.7 |
| 2018 | 65 | -78,538 | 14.5 |
| 2019 | 68 | -83,621 | 14.5 |
| 2020 | 90 | 112,632 | 26.7 |
| 2021 | 76 | 233,331 | 4.4 |
| 2022 | 70 | -57,735 | 11.6 |
| 2023 | 73 | 182,991 | 4.7 |
| 2024 | 74 | 164,438 | 5.5 |
| 2025 | 66 | -52,857 | 7.5 |
| 2026 | 68 | -19,712 | 6.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC5-c_coin",
  "run_id": "A11_day_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": 0.2,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null,
  "sources": []
}
```
