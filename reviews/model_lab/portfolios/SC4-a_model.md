# Portfolio sim `SC4-a_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,126,202 · trades 1360 · win rate 53.1% · PF 1.44 · money-weighted win % 59.0 · avg ₹828/trade · max DD ₹386,419 (35.4%) · ann. return 11.9% · Calmar 0.34 · mean utilisation 94.4% · avg held 42.1 bars

## Excluding 2020

net ₹1,012,543 · trades 1274 · win rate 52.7% · PF 1.44 · money-weighted win % 59.1 · avg ₹795/trade · max DD ₹271,767 (34.8%) · ann. return 11.6% · Calmar 0.33 · mean utilisation 94.4% · avg held 42.1 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -27,113 |
| TIME | 1345 | 1,153,315 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 41 | -88,521 | 33.7 |
| 2012 | 88 | 93,222 | 22.7 |
| 2013 | 81 | -9,619 | 33.9 |
| 2014 | 91 | 165,669 | 8.8 |
| 2015 | 90 | 15,628 | 10.9 |
| 2016 | 99 | 63,424 | 13.3 |
| 2017 | 92 | 65,914 | 10.8 |
| 2018 | 91 | -15,811 | 21.6 |
| 2019 | 83 | 25,957 | 11.8 |
| 2020 | 86 | 113,659 | 29.4 |
| 2021 | 85 | 316,182 | 4.3 |
| 2022 | 82 | 52,802 | 8.9 |
| 2023 | 95 | 179,826 | 4.4 |
| 2024 | 80 | 87,653 | 6.5 |
| 2025 | 94 | 119,187 | 4.2 |
| 2026 | 82 | -58,970 | 4.7 |

## By score source

| source | trades | net ₹ |
|---|---|---|
| ref:prod_pmin | 762 | 870,209 |
| run | 598 | 255,993 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 14; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC4-a_model",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
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
  "sources": [
    [
      "run",
      20
    ],
    [
      "ref:prod_pmin",
      60
    ]
  ]
}
```
