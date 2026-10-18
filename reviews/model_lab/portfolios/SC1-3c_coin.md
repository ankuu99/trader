# Portfolio sim `SC1-3c_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,115,561 · trades 2926 · win rate 51.0% · PF 1.27 · money-weighted win % 55.9 · avg ₹381/trade · max DD ₹489,595 (43.9%) · ann. return 11.8% · Calmar 0.27 · mean utilisation 93.8% · avg held 20.0 bars

## Excluding 2020

net ₹936,630 · trades 2736 · win rate 50.5% · PF 1.24 · money-weighted win % 55.5 · avg ₹342/trade · max DD ₹324,047 (43.9%) · ann. return 10.7% · Calmar 0.24 · mean utilisation 93.8% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -11,052 |
| TIME | 2912 | 1,126,613 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 179 | -216,821 | 38.5 |
| 2012 | 181 | 104,536 | 28.8 |
| 2013 | 183 | 24,315 | 33.8 |
| 2014 | 185 | 260,090 | 13.9 |
| 2015 | 187 | -4,616 | 11.7 |
| 2016 | 180 | 80,885 | 16.2 |
| 2017 | 187 | 235,989 | 15.7 |
| 2018 | 188 | -76,907 | 17.7 |
| 2019 | 180 | -42,175 | 13.7 |
| 2020 | 190 | 178,931 | 28.1 |
| 2021 | 185 | 334,255 | 4.0 |
| 2022 | 182 | -20,361 | 12.0 |
| 2023 | 190 | 206,325 | 4.9 |
| 2024 | 183 | 135,054 | 4.6 |
| 2025 | 189 | -48,491 | 6.6 |
| 2026 | 157 | -35,446 | 5.7 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 10; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-3c_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:coin",
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
