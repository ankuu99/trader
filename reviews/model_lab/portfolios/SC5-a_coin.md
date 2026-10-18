# Portfolio sim `SC5-a_coin` (run `A11_day_hgbq_edgez20`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹913,232 · trades 2919 · win rate 51.1% · PF 1.21 · money-weighted win % 54.8 · avg ₹313/trade · max DD ₹489,241 (45.4%) · ann. return 9.6% · Calmar 0.21 · mean utilisation 93.4% · avg held 19.9 bars

## Excluding 2020

net ₹767,456 · trades 2732 · win rate 50.9% · PF 1.20 · money-weighted win % 54.5 · avg ₹281/trade · max DD ₹272,156 (45.4%) · ann. return 8.8% · Calmar 0.19 · mean utilisation 93.4% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -1,885 |
| TIME | 2904 | 915,116 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 174 | -232,470 | 44.0 |
| 2012 | 186 | 167,216 | 29.7 |
| 2013 | 181 | -29,194 | 41.5 |
| 2014 | 183 | 350,473 | 14.1 |
| 2015 | 185 | 10,675 | 10.7 |
| 2016 | 186 | -4,535 | 14.7 |
| 2017 | 177 | 179,684 | 6.3 |
| 2018 | 185 | -73,261 | 15.7 |
| 2019 | 184 | -100,891 | 15.0 |
| 2020 | 187 | 145,776 | 33.2 |
| 2021 | 188 | 173,669 | 4.2 |
| 2022 | 183 | -28,164 | 15.1 |
| 2023 | 185 | 222,155 | 4.2 |
| 2024 | 187 | 130,200 | 5.1 |
| 2025 | 186 | 38,734 | 4.6 |
| 2026 | 162 | -36,837 | 6.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 11; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC5-a_coin",
  "run_id": "A11_day_hgbq_edgez20",
  "hold_bars": 20,
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
  "queue_max_runup": null,
  "sources": []
}
```
