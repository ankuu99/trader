# Portfolio sim `SC1-2a_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹859,466 · trades 2875 · win rate 50.5% · PF 1.20 · money-weighted win % 54.6 · avg ₹299/trade · max DD ₹498,555 (53.6%) · ann. return 9.1% · Calmar 0.17 · mean utilisation 92.0% · avg held 20.0 bars

## Excluding 2020

net ₹707,083 · trades 2688 · win rate 50.0% · PF 1.19 · money-weighted win % 54.3 · avg ₹263/trade · max DD ₹275,587 (43.3%) · ann. return 8.1% · Calmar 0.19 · mean utilisation 92.0% · avg held 20.0 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 14 | -8,882 |
| TIME | 2861 | 868,349 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 130 | -164,329 | 37.1 |
| 2012 | 183 | 122,331 | 26.7 |
| 2013 | 184 | -24,036 | 37.1 |
| 2014 | 181 | 171,759 | 10.9 |
| 2015 | 185 | -1,985 | 11.4 |
| 2016 | 186 | -35,279 | 18.7 |
| 2017 | 182 | 175,112 | 7.8 |
| 2018 | 186 | -46,982 | 18.5 |
| 2019 | 183 | -84,032 | 17.0 |
| 2020 | 187 | 152,384 | 43.0 |
| 2021 | 186 | 337,007 | 5.0 |
| 2022 | 187 | -55,181 | 15.1 |
| 2023 | 183 | 212,821 | 6.8 |
| 2024 | 185 | 97,412 | 6.1 |
| 2025 | 188 | -22,469 | 6.4 |
| 2026 | 159 | 24,932 | 5.5 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 20; entries from the carry-over queue: 1361 (queue_bars 3).

## Spec

```json
{
  "sim_id": "SC1-2a_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "rate",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 0,
  "stop_pct": null,
  "target_pct": null,
  "trail_pct": null,
  "trail_activate_pct": 0.0,
  "reentry_gap_bars": 0,
  "exclusions": [],
  "queue_bars": 3,
  "queue_max_runup": 0.02
}
```
