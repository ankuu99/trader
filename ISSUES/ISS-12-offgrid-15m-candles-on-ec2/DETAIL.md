# ISS-12: Same-day re-warm-ups write off-grid '15minute' rows (15:16..15:25) into the EC2 candle cache

Source: Memory note `project_offgrid_candles_ec2` (2026-10-12/13). Reproduced verbatim; dated addenda below. Never delete.

---

Found 2026-10-12 while backtesting the pattern-top trail idea. `historical.get_candles` resumes at `cached_latest + 1 minute`; when warm_up runs again the SAME day after a bar was persisted (evening deploy/restart = 2 warm_up calls each, intraday crash-restart loops), Kite returns a 15m bucket anchored at that minute (15:16 bucket = 15:16–15:31, next restart 15:17, ...). 2,751 rows across 26 days (2026-04-27 → 2026-10-12), 426 since 2026-08-14 (inside live 1200-bar windows); 06-03 restart loop made 1,656 mid-session ones. Cross-day morning fetches don't create them. CAS names stopped getting them after Aug. Local data/market.db is clean (0). Aligned bars are complete on every recent stray day (25/25), so deleting strays leaves no gaps; 04-27/04-30/06-03 have a few missing aligned bars.

They mattered: removing ATHER's 138 strays changed its standalone backtest by ~₹3k and flipped variant rankings. Day/4h aggregator drops ≥15:15 tail rows, but mid-session strays get summed into slow-TF bars.

**How to apply:** fix before/with cleanup — resume at the next timeframe boundary (cached_latest + interval) and reject off-grid timestamps at write; delete only off-hours, then the next boot warm-up rebuilds models clean. Cleanup alone gets re-created on the next same-day restart. When pulling EC2 candles for backtests, filter off-grid rows first. Related: [[project_cas_1515_amo_rejects]].

**Live impact measured 2026-10-13** (per-session morning-warm-up replay, polluted vs clean, 27 Apr→12 Oct, 14,960 decision bars; replay reproduces 90% / 97.5%-since-Sep of live ENTRY signals): mean |ΔP(min)| 0.012 (0.007 since Sep). 17 entry flips (16 polluted-only → strays make entries slightly trigger-happier), 8 became live trades, 5 of those clean would have taken within 45 min–1 day anyway; only 3 trades existed purely because of strays (THANGAMAYL 09-09 −1.3k, KPL 09-17 +3.2k, CGPOWER 07-15 −2.3k = net −₹0.4k). Pattern-top: 2 live-relevant flips, trivial. Day/4h names: zero flips. Verdict: real but small; fix for hygiene, not urgency.
