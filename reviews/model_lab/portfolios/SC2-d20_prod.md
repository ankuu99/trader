# Portfolio sim `SC2-d20_prod` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,159,868 · trades 2887 · win rate 52.5% · PF 1.29 · money-weighted win % 56.3 · avg ₹402/trade · max DD ₹267,674 (40.9%) · ann. return 12.2% · Calmar 0.30 · mean utilisation 92.2% · avg held 19.9 bars

## Excluding 2020

net ₹902,554 · trades 2701 · win rate 52.0% · PF 1.24 · money-weighted win % 55.4 · avg ₹334/trade · max DD ₹267,674 (40.9%) · ann. return 10.4% · Calmar 0.25 · mean utilisation 92.2% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -11,694 |
| TIME | 2872 | 1,171,562 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 167 | -184,709 | 37.2 |
| 2012 | 185 | 209,803 | 18.0 |
| 2013 | 181 | -90,881 | 40.9 |
| 2014 | 178 | 200,745 | 8.9 |
| 2015 | 183 | 22,480 | 9.0 |
| 2016 | 181 | 66,792 | 11.8 |
| 2017 | 184 | 274,256 | 14.7 |
| 2018 | 182 | -31,132 | 8.9 |
| 2019 | 182 | 35,202 | 14.2 |
| 2020 | 186 | 257,315 | 16.5 |
| 2021 | 183 | 87,864 | 5.1 |
| 2022 | 187 | -10,412 | 10.4 |
| 2023 | 178 | 190,062 | 7.2 |
| 2024 | 185 | 71,272 | 5.8 |
| 2025 | 184 | 59,142 | 4.8 |
| 2026 | 161 | 2,072 | 4.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 20; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d20_prod",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:prod_pmin",
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
