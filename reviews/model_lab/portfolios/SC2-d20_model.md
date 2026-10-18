# Portfolio sim `SC2-d20_model` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹1,039,836 · trades 2823 · win rate 51.5% · PF 1.24 · money-weighted win % 55.4 · avg ₹368/trade · max DD ₹314,232 (40.1%) · ann. return 11.0% · Calmar 0.27 · mean utilisation 90.2% · avg held 19.9 bars

## Excluding 2020

net ₹877,827 · trades 2641 · win rate 51.0% · PF 1.22 · money-weighted win % 55.1 · avg ₹332/trade · max DD ₹292,500 (40.1%) · ann. return 10.1% · Calmar 0.25 · mean utilisation 90.2% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -10,711 |
| TIME | 2808 | 1,050,547 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 166 | -174,574 | 34.5 |
| 2012 | 176 | 272,559 | 10.9 |
| 2013 | 180 | -29,920 | 39.4 |
| 2014 | 174 | 147,558 | 10.0 |
| 2015 | 179 | -19,352 | 15.5 |
| 2016 | 173 | 93,465 | 14.3 |
| 2017 | 181 | 318,049 | 17.7 |
| 2018 | 179 | -176,406 | 18.9 |
| 2019 | 177 | 85,072 | 15.4 |
| 2020 | 182 | 162,009 | 22.7 |
| 2021 | 174 | 135,718 | 5.7 |
| 2022 | 180 | 15,030 | 11.3 |
| 2023 | 179 | 151,018 | 5.9 |
| 2024 | 183 | 46,925 | 5.3 |
| 2025 | 180 | -11,379 | 5.5 |
| 2026 | 160 | 24,062 | 5.9 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 38; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC2-d20_model",
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
  "queue_max_runup": null
}
```
