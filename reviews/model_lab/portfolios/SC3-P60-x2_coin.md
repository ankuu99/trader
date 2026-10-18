# Portfolio sim `SC3-P60-x2_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹978,891 · trades 1498 · win rate 39.4% · PF 1.29 · money-weighted win % 56.3 · avg ₹653/trade · max DD ₹374,805 (62.5%) · ann. return 10.3% · Calmar 0.17 · mean utilisation 95.7% · avg held 38.8 bars

## Excluding 2020

net ₹809,635 · trades 1376 · win rate 39.8% · PF 1.26 · money-weighted win % 55.8 · avg ₹588/trade · max DD ₹374,805 (62.5%) · ann. return 9.3% · Calmar 0.15 · mean utilisation 95.7% · avg held 39.5 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | 6,365 |
| STOP | 793 | -3,250,359 |
| TIME | 690 | 4,222,886 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 121 | -315,541 | 52.8 |
| 2012 | 90 | 79,911 | 32.7 |
| 2013 | 106 | -1,388 | 48.9 |
| 2014 | 84 | 389,161 | 18.5 |
| 2015 | 93 | -45,044 | 17.6 |
| 2016 | 93 | 33,922 | 15.6 |
| 2017 | 80 | 224,255 | 6.4 |
| 2018 | 102 | -115,878 | 17.7 |
| 2019 | 98 | 28,993 | 14.8 |
| 2020 | 122 | 169,256 | 24.9 |
| 2021 | 80 | 322,966 | 5.0 |
| 2022 | 92 | 19,729 | 12.5 |
| 2023 | 69 | 99,863 | 6.4 |
| 2024 | 83 | 185,195 | 5.7 |
| 2025 | 89 | -16,358 | 6.4 |
| 2026 | 96 | -80,151 | 7.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 3; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x2_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": 0.1,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
