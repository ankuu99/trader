# Portfolio sim `SN-4_coin105` (run `A07n_dayn_hgbq_mfe20`, tf dayn)

Offline lab simulation — survivor-biased universe (TD-022); not a production backtest.

## Headline

net ₹517,946 · trades 2933 · win rate 50.5% · PF 1.11 · money-weighted win % 52.7 · avg ₹177/trade · max DD ₹581,275 (67.8%) · ann. return 5.5% · Calmar 0.08 · mean utilisation 93.6% · avg held 20.0 bars

## Excluding 2020

net ₹405,331 · trades 2741 · win rate 50.2% · PF 1.10 · money-weighted win % 52.3 · avg ₹148/trade · max DD ₹341,753 (57.0%) · ann. return 4.6% · Calmar 0.08 · mean utilisation 93.6% · avg held 19.9 bars

## Exits by reason (counts and ₹ only)

| reason | count | net ₹ |
|---|---|---|
| DELIST | 1 | 2,317 |
| END | 13 | -10,374 |
| TIME | 2919 | 526,003 |

## By calendar year

| year | trades | net ₹ | max DD % |
|---|---|---|---|
| 2011 | 174 | -263,578 | 49.0 |
| 2012 | 186 | 155,660 | 28.2 |
| 2013 | 188 | -107,410 | 51.3 |
| 2014 | 183 | 301,831 | 14.3 |
| 2015 | 185 | -73,822 | 20.7 |
| 2016 | 185 | 65,261 | 18.7 |
| 2017 | 188 | 144,667 | 7.0 |
| 2018 | 182 | -172,806 | 30.4 |
| 2019 | 182 | -99,889 | 25.5 |
| 2020 | 192 | 112,615 | 52.3 |
| 2021 | 183 | 207,796 | 9.5 |
| 2022 | 188 | -11,445 | 18.0 |
| 2023 | 185 | 230,589 | 5.6 |
| 2024 | 183 | 35,559 | 10.8 |
| 2025 | 190 | 38,021 | 8.0 |
| 2026 | 159 | -45,102 | 8.3 |

## Notes

- Rate-mode threshold: (1-rate) quantile of eligible scores pooled over the previous 60 distinct dates (strictly before); the window crosses fold boundaries, so a model refit that shifts the score scale shifts the threshold only gradually.
- Skipped symbols (no scores/bars/ref): 45; qty_zero skips: 9; entries from the carry-over queue: 0 (queue_bars 0).

## Spec

```json
{
  "sim_id": "SN-4_coin105",
  "run_id": "A07n_dayn_hgbq_mfe20",
  "hold_bars": 20,
  "score_source": "coin:105",
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
