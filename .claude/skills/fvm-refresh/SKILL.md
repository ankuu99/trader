---
description: Run the FVM daily data-refresh loop in sequence — fundamentals ingest (mid-cap-first), price cache, then re-run the Milestone-A validation gate. Use when the user asks to "refresh FVM", "run the FVM ingest", "do the daily FVM data run", or similar. The user updates TRENDLYNE_COOKIE manually; this skill assumes it's already current.
argument-hint: [--no-gate] [--max N]
---

Run the three FVM data-refresh steps **in order**, stopping early only on a hard failure.
This is the daily loop from `docs/FVM_Forward_Plan.md` steps 2–4. The user keeps
`TRENDLYNE_COOKIE` in `config/.env` fresh themselves — do **not** try to refresh it.

Always `source .venv/bin/activate` first. Run each step with `run_in_background: true` if it
looks long; otherwise inline is fine. Report a short summary after each step.

## Step 1 — Fundamentals ingest (mid-cap-first)
```bash
python scripts/fvm_ingest.py
```
- Fills the daily Trendlyne quota (~40 stocks) from the mid-cap-first priority order, resumable
  (already-ingested names are skipped). One-shot index/membership scaffolding runs automatically.
- Pass `--max-financials N` if the user gave `--max N`.
- **Stop the whole skill** and tell the user if you see a **403 / cookie** message ("likely a
  stale TRENDLYNE_COOKIE — refresh it in config/.env and re-run") or a **429 / quota** message
  ("daily Trendlyne quota reached"). These are expected, not bugs — the user fixes the cookie or
  waits for the quota reset. Do not retry.
- Note from the output how many financials were fetched and the new total (`~X/399`).

## Step 2 — Price cache
```bash
python scripts/fvm_prices.py
```
- Cache-only-cheap: only fetches daily candles for names newly scoreable since the last run.
  Auto-refreshes the Kite token if needed. Report how many names were resolved / how many bars.
- If it reports a Kite auth failure, tell the user to run `python scripts/kite_totp_refresh.py`
  (or wait for the 08:15 cron) and stop — don't proceed to the gate on stale prices.

## Step 3 — Re-run the Milestone-A gate  (skip if the user passed `--no-gate`)
```bash
python scripts/fvm_milestone_a.py
```
- Heavy (~minutes). Skip it if the user passed `--no-gate`, or if Step 1 ingested **zero** new
  names (coverage didn't change, so the gate result won't either) — say so instead of running it.
- Surface the verdict line: GATE PASS/FAIL, beats-benchmark and profitable counts, mean edge,
  and the thin-universe caveat if it prints. **Do not tune any parameters to change the result**
  (overfit risk on a thin/overlapping-fold universe — this is a standing rule in the forward plan).

## After the run
Print a 3–4 line summary: names ingested this run + new coverage (`X/399`), price names added,
and the gate verdict (or why it was skipped). If the universe grew meaningfully, remind the user
they can eyeball candidates in the cockpit (`streamlit run scripts/fvm_ui.py`) or
`python scripts/fvm_shortlist.py`.

Do not edit config, the watchlist, or any strategy parameters. This skill only moves data.
