# Portfolio sim `SN-4_coin104` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹424,804 · trades 2934 · win rate 50.4% · PF 1.09 · money-weighted win % 52.2 · avg ₹145/trade · max DD ₹535,140 (72.3%) · ann. return 4.5% · Calmar 0.06 · mean utilisation 93.6% · avg held 19.9 bars

## Excluding 2020

net ₹278,758 · trades 2743 · win rate 49.8% · PF 1.07 · money-weighted win % 51.6 · avg ₹102/trade · max DD ₹335,538 (55.9%) · ann. return 3.2% · Calmar 0.06 · mean utilisation 93.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 3 | 1,868 |
| END | 14 | -4,006 |
| TIME | 2917 | 426,943 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 173 | -247,736 | 48.6 |
| 2012 | 187 | 170,296 | 31.3 |
| 2013 | 187 | -131,286 | 51.2 |
| 2014 | 185 | 227,624 | 14.1 |
| 2015 | 183 | -115,251 | 29.8 |
| 2016 | 186 | 72,423 | 18.9 |
| 2017 | 189 | 122,665 | 8.6 |
| 2018 | 182 | -99,578 | 29.6 |
| 2019 | 183 | -170,753 | 31.1 |
| 2020 | 191 | 146,046 | 56.4 |
| 2021 | 183 | 262,052 | 8.1 |
| 2022 | 187 | 45,783 | 15.3 |
| 2023 | 185 | 191,663 | 5.2 |
| 2024 | 185 | 24,495 | 6.8 |
| 2025 | 188 | -56,591 | 11.4 |
| 2026 | 160 | -17,049 | 10.0 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 12; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_coin104",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
  "score_source": "coin:104",
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
  "sources": [],
  "delist_grace_days": 7
}
```
