# Portfolio sim `SC5-c_model` (run `A11_day_hgbq_edgez20`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,083,740 · trades 1060 · win rate 57.7% · PF 1.50 · money-weighted win % 60.0 · avg ₹1,022/trade · max DD ₹274,385 (41.4%) · ann. return 11.4% · Calmar 0.28 · mean utilisation 88.0% · avg held 50.2 bars

## Excluding 2020

net ₹827,848 · trades 969 · win rate 56.3% · PF 1.42 · money-weighted win % 58.7 · avg ₹854/trade · max DD ₹248,630 (41.4%) · ann. return 9.5% · Calmar 0.23 · mean utilisation 88.0% · avg held 51.3 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -42,063 |
| TARGET | 313 | 2,493,803 |
| TIME | 733 | -1,367,999 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 50 | -159,857 | 41.4 |
| 2012 | 72 | 191,210 | 7.2 |
| 2013 | 62 | -103,718 | 37.1 |
| 2014 | 65 | 288,245 | 6.1 |
| 2015 | 69 | -20,823 | 13.4 |
| 2016 | 66 | 93,011 | 11.1 |
| 2017 | 66 | 244,102 | 2.5 |
| 2018 | 57 | -59,355 | 13.9 |
| 2019 | 70 | 45,653 | 6.4 |
| 2020 | 91 | 255,892 | 20.4 |
| 2021 | 57 | 137,512 | 4.3 |
| 2022 | 66 | 3,138 | 9.4 |
| 2023 | 63 | 63,693 | 4.6 |
| 2024 | 74 | 138,091 | 4.2 |
| 2025 | 66 | 44,195 | 5.0 |
| 2026 | 66 | -77,250 | 5.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 18; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC5-c_model",
  "run_id": "A11_day_hgbq_edgez20",
  "hold_bars": 60,
  "score_source": "run",
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
