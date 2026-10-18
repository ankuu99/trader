# Portfolio sim `SC3-P60-x4_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,219,825 · trades 1032 · win rate 52.6% · PF 1.53 · money-weighted win % 60.4 · avg ₹1,182/trade · max DD ₹473,184 (37.9%) · ann. return 12.9% · Calmar 0.34 · mean utilisation 96.8% · avg held 56.5 bars

## Excluding 2020

net ₹1,172,590 · trades 962 · win rate 52.8% · PF 1.57 · money-weighted win % 61.1 · avg ₹1,219/trade · max DD ₹282,535 (37.9%) · ann. return 13.4% · Calmar 0.35 · mean utilisation 96.8% · avg held 56.7 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -35,802 |
| TIME | 873 | 975,372 |
| TRAIL | 144 | 280,255 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 60 | -150,445 | 37.9 |
| 2012 | 62 | 116,145 | 21.7 |
| 2013 | 64 | 10,372 | 25.9 |
| 2014 | 65 | 453,302 | 10.4 |
| 2015 | 64 | -29,267 | 15.3 |
| 2016 | 64 | 54,947 | 11.3 |
| 2017 | 63 | 209,816 | 3.9 |
| 2018 | 69 | 12,137 | 11.1 |
| 2019 | 63 | -118,611 | 15.3 |
| 2020 | 70 | 47,235 | 26.6 |
| 2021 | 65 | 362,365 | 3.4 |
| 2022 | 66 | -39,258 | 9.6 |
| 2023 | 64 | 127,906 | 4.9 |
| 2024 | 66 | 184,660 | 3.6 |
| 2025 | 63 | 18,922 | 5.6 |
| 2026 | 64 | -40,402 | 5.2 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 8; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC3-P60-x4_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 60,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 2,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": 0.15,
  "trail_activate_pct": 0.1,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 0,
  "queue_max_runup": null
}
```
