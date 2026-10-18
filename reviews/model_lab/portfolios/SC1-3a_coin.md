# Portfolio sim `SC1-3a_coin` (run `A01_day_logit_t1z5`, tf day)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹795,735 · trades 2879 · win rate 50.7% · PF 1.19 · money-weighted win % 54.2 · avg ₹276/trade · max DD ₹459,798 (63.5%) · ann. return 8.4% · Calmar 0.13 · mean utilisation 92.1% · avg held 19.9 bars

## Excluding 2020

net ₹650,790 · trades 2695 · win rate 50.1% · PF 1.17 · money-weighted win % 53.8 · avg ₹241/trade · max DD ₹380,864 (63.5%) · ann. return 7.5% · Calmar 0.12 · mean utilisation 92.1% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| END | 15 | -808 |
| TIME | 2864 | 796,542 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 166 | -208,505 | 41.0 |
| 2012 | 183 | 8,204 | 44.6 |
| 2013 | 181 | 24,157 | 47.4 |
| 2014 | 181 | 213,133 | 16.5 |
| 2015 | 181 | 37,569 | 10.9 |
| 2016 | 184 | 21,178 | 16.2 |
| 2017 | 183 | 178,956 | 7.0 |
| 2018 | 180 | -84,863 | 18.0 |
| 2019 | 180 | -58,363 | 16.2 |
| 2020 | 184 | 144,945 | 41.2 |
| 2021 | 183 | 202,296 | 5.4 |
| 2022 | 183 | -568 | 15.8 |
| 2023 | 182 | 216,374 | 7.3 |
| 2024 | 183 | 153,885 | 5.9 |
| 2025 | 185 | -8,533 | 8.3 |
| 2026 | 160 | -44,131 | 7.8 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 31; qty_zero skips: 13; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SC1-3a_coin",
  "run_id": "A01_day_logit_t1z5",
  "hold_bars": 20,
  "score_source": "ref:coin",
  "capital": 600000,
  "slot": 40000,
  "entry_mode": "topk",
  "rate": 0.01,
  "window_sessions": 60,
  "topk": 1,
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
