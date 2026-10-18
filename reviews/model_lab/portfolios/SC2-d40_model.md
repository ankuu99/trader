# Portfolio sim `SC2-d40_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹714,845 · trades 1460 · win rate 52.9% · PF 1.24 · money-weighted win % 55.4 · avg ₹490/trade · max DD ₹412,455 (50.5%) · ann. return 7.5% · Calmar 0.15 · mean utilisation 95.5% · avg held 39.8 bars

## Excluding 2020

net ₹641,360 · trades 1365 · win rate 52.7% · PF 1.24 · money-weighted win % 55.3 · avg ₹470/trade · max DD ₹317,203 (50.5%) · ann. return 7.4% · Calmar 0.15 · mean utilisation 95.5% · avg held 39.8 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -19,939 |
| TIME | 1445 | 734,784 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 79 | -139,930 | 42.0 |
| 2012 | 94 | 129,783 | 12.6 |
| 2013 | 91 | -69,861 | 48.6 |
| 2014 | 91 | 234,654 | 10.3 |
| 2015 | 94 | -40,057 | 17.4 |
| 2016 | 91 | 87,547 | 12.9 |
| 2017 | 91 | 168,661 | 5.8 |
| 2018 | 92 | -104,461 | 21.0 |
| 2019 | 91 | -45,322 | 18.6 |
| 2020 | 95 | 73,484 | 28.8 |
| 2021 | 93 | 199,568 | 7.0 |
| 2022 | 93 | -3,148 | 15.2 |
| 2023 | 91 | 138,496 | 4.9 |
| 2024 | 92 | 74,100 | 6.3 |
| 2025 | 94 | 56,479 | 7.7 |
| 2026 | 88 | -45,148 | 7.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 13; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d40_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 40,
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
  "queue_max_runup": null
}
```
