# Portfolio sim `SC3-P60-x1_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹967,628 · trades 1102 · win rate 50.2% · PF 1.35 · money-weighted win % 57.5 · avg ₹878/trade · max DD ₹445,541 (45.5%) · ann. return 10.2% · Calmar 0.22 · mean utilisation 96.6% · avg held 53.0 bars

## Excluding 2020

net ₹804,105 · trades 1011 · win rate 50.3% · PF 1.33 · money-weighted win % 57.2 · avg ₹795/trade · max DD ₹303,052 (45.5%) · ann. return 9.2% · Calmar 0.20 · mean utilisation 96.6% · avg held 53.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -12,419 |
| STOP | 232 | -1,899,557 |
| TIME | 855 | 2,879,604 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 69 | -189,873 | 38.9 |
| 2012 | 65 | 45,072 | 24.9 |
| 2013 | 76 | 1,917 | 35.2 |
| 2014 | 61 | 388,717 | 13.2 |
| 2015 | 67 | -35,464 | 13.2 |
| 2016 | 67 | 78,077 | 14.3 |
| 2017 | 65 | 238,227 | 13.9 |
| 2018 | 76 | -13,036 | 18.1 |
| 2019 | 71 | -54,063 | 11.5 |
| 2020 | 91 | 163,522 | 24.1 |
| 2021 | 65 | 107,808 | 6.3 |
| 2022 | 64 | 36,530 | 11.9 |
| 2023 | 61 | 146,836 | 3.9 |
| 2024 | 67 | 116,157 | 6.6 |
| 2025 | 67 | -14,651 | 6.5 |
| 2026 | 70 | -48,149 | 7.6 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 5; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x1_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": 0.2,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
