# ⏰ Re-check reminder — NSE:INDHOTEL — due 2026-07-01 (post-AGM)

**Why:** Qualified 2026-06-18 as **WATCH** (see `qualify_INDHOTEL_20260618.md`).
Two blockers were time-bound, both clear after the 30 Jun AGM:
1. Structural guard had only 71 days of history (low confidence) and trailing returns
   looked trend-like — couldn't confirm range-bound behaviour.
2. Event cluster through end-June (record date 23 Jun, investor meets 19/22 Jun, AGM 30 Jun).

**Action on/after 1 Jul 2026 (run locally — needs Kite token + data):**
```bash
/qualify NSE:INDHOTEL
# or just the guard:
python scripts/trend_guard.py --symbol NSE:INDHOTEL --fetch
```
- If it holds **RANGE_BOUND** at higher confidence → `/calibrate NSE:INDHOTEL`, then paper-trade before live.
- If it resolves to **UPTREND** → drop it (poor fit for mean-reversion).
