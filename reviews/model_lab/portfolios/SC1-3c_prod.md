# Portfolio sim `SC1-3c_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,133,724 · trades 2924 · win rate 52.2% · PF 1.27 · money-weighted win % 56.0 · avg ₹388/trade · max DD ₹289,309 (43.6%) · ann. return 12.0% · Calmar 0.27 · mean utilisation 93.4% · avg held 19.9 bars

## Excluding 2020

net ₹901,218 · trades 2734 · win rate 51.4% · PF 1.23 · money-weighted win % 55.2 · avg ₹330/trade · max DD ₹289,309 (43.6%) · ann. return 10.3% · Calmar 0.24 · mean utilisation 93.4% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -6,484 |
| TIME | 2910 | 1,140,207 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 173 | -108,273 | 30.1 |
| 2012 | 187 | 143,346 | 20.1 |
| 2013 | 182 | -92,834 | 43.6 |
| 2014 | 183 | 208,508 | 7.2 |
| 2015 | 186 | -11,446 | 12.9 |
| 2016 | 184 | 76,043 | 10.8 |
| 2017 | 184 | 426,585 | 16.6 |
| 2018 | 184 | -67,938 | 10.9 |
| 2019 | 182 | 58,245 | 10.4 |
| 2020 | 190 | 232,505 | 14.6 |
| 2021 | 185 | 69,297 | 5.1 |
| 2022 | 186 | -21,180 | 10.8 |
| 2023 | 184 | 133,966 | 8.2 |
| 2024 | 187 | 52,190 | 6.3 |
| 2025 | 186 | 29,236 | 4.6 |
| 2026 | 161 | 5,473 | 4.1 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 21; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-3c_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:prod_pmin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 3,
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
