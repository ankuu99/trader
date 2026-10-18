# Portfolio sim `SC5-b_model` (run `A11_day_hgbq_edgez20`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,290,622 · trades 932 · win rate 53.8% · PF 1.68 · money-weighted win % 62.7 · avg ₹1,385/trade · max DD ₹264,751 (42.6%) · ann. return 13.6% · Calmar 0.32 · mean utilisation 92.1% · avg held 59.5 bars

## Excluding 2020

net ₹979,585 · trades 870 · win rate 53.2% · PF 1.57 · money-weighted win % 61.1 · avg ₹1,126/trade · max DD ₹264,751 (42.6%) · ann. return 11.2% · Calmar 0.26 · mean utilisation 92.1% · avg held 59.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -23,316 |
| TIME | 917 | 1,313,938 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 47 | -147,795 | 40.2 |
| 2012 | 61 | 140,454 | 11.4 |
| 2013 | 55 | -137,412 | 42.6 |
| 2014 | 56 | 392,839 | 5.6 |
| 2015 | 62 | 16,220 | 15.5 |
| 2016 | 57 | 84,501 | 11.8 |
| 2017 | 59 | 194,797 | 2.7 |
| 2018 | 55 | -74,700 | 14.3 |
| 2019 | 59 | 68,430 | 7.9 |
| 2020 | 62 | 311,038 | 19.9 |
| 2021 | 53 | 238,401 | 4.3 |
| 2022 | 59 | -24,541 | 9.1 |
| 2023 | 62 | 62,319 | 3.0 |
| 2024 | 61 | 157,492 | 4.7 |
| 2025 | 62 | 41,137 | 4.5 |
| 2026 | 62 | -32,558 | 4.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 13; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC5-b_model",
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
