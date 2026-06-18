---
description: Discover new watchlist candidates ranked by mean-reversion FIT, not backtest P&L. Two modes — a fresh scan of a liquid universe (Nifty 500) computed on today's daily candles, or gating the existing NSE-wide screen CSV. Both apply segment hygiene, dedup, liquidity, and the structural trend guard, then run the qualitative `qualify` gate on the survivors. Advisory only — never edits the watchlist automatically.
argument-hint: [--mode universe|screen] [--max-fetch N]
---

Find new stocks worth paper-trading with the LRExtrema strategy.

## Principle

Discovery is cheap; *fit* is the hard part. Select for the strategy's fit profile — **liquid,
range-bound / oscillating, structurally sound** — NOT for the biggest backtest number and NOT
for what's "trending". Trending / momentum / hot-news names are the *inverted* signal here: a
mean-reversion strategy needs oscillation, and trending names are disproportionately pumps and
event spikes (the AQYLON story-stock, the ELECTHERM fraud-pump). The trend guard's `SPIKE`,
`UPTREND`, `FALLING_KNIFE`, and `DOWNTREND` verdicts all get dropped or demoted for this reason.
Use the same disqualifier-first bar as `/qualify` and `/watchlist-review`.

## Step 1 — Build the candidate shortlist

Both modes drop `-BE/-E1/...` segments, anything already in `config.yaml`, illiquid names
(<₹50L/day turnover), and `FALLING_KNIFE / DOWNTREND / SPIKE` guard verdicts; then rank by fit
(`RANGE_BOUND` first, then choppiest by efficiency ratio, then most liquid). If the Kite token is
expired, run `python scripts/kite_totp_refresh.py` first (the gate needs daily candles).

### Mode A — fresh liquid-universe scan (recommended; forward-looking)

Fetch a current liquid universe — Nifty 500 constituents — and rank by fit on candles computed
*today* (no stale backtest, no microcap/story-stock trap). NSE needs a cookie handshake:

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
curl -s -c /tmp/nse_cookies.txt -A "$UA" "https://www.nseindia.com" -o /dev/null
curl -s -b /tmp/nse_cookies.txt -A "$UA" -H "Referer: https://www.nseindia.com/" \
  "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv" -o /tmp/nifty500.csv
python scripts/discover.py --mode universe --universe-file /tmp/nifty500.csv --max-fetch 500 2>/dev/null
```

(For a faster pass use a smaller index, e.g. `ind_niftymidcap150list.csv`, or lower `--max-fetch`.
A full 500-name first run takes a few minutes — daily candles are then cached for next time.)

### Mode B — gate the existing screen CSV (fast; mines what was already computed)

```bash
python scripts/discover.py --mode screen --max-fetch 60 2>/dev/null
```

Adds a quant floor (`--min-return` / `--min-wr` / `--min-trades`) on the stale screen metrics
before the candle gates. Cheap, but the CSV is a 2024–26 backtest — prefer Mode A for fresh names.

**Reading the output:** prioritise `RANGE_BOUND` with a low efficiency ratio (ER < ~0.3 = choppy
= good mean-reversion fit). `UPTREND` survivors are not loss risks but trend strongly (few minima
→ few signals / trend-regime-dependent edge) — lower priority. `WATCH_RECOVERING` = beaten-down
but basing — treat cautiously. Add `--json` to parse programmatically.

## Step 2 — Qualify the survivors (qualitative red-flag scan)

For each survivor, run the `qualify` skill — it pairs the trend guard (already computed, will
agree) with exchange filings, rating actions, promoter pledge, event window, and governance/
sector news to return **FIT / WATCH / AVOID**:

```
Skill("qualify", "<NSE:SYMBOL>")
```

If there are many survivors, qualify the `RANGE_BOUND` ones first and stop when you have a
healthy handful of FITs — reserve the web-search budget for the best-fit names.

## Step 3 — Write the discovery report

Save to `reviews/discover_YYYYMMDD.md`:

```markdown
# Candidate Discovery — DATE

Mode: <universe (Nifty 500) | screen CSV>. Universe N → M after segment/dedup → K after
liquidity + structural guard.

## Shortlist (ranked, best fit first)
| Symbol | Guard | ER | Turnover | 6m% / 12m% | Gate | Notes |
|--------|-------|----|----------|------------|------|-------|
(RANGE_BOUND + low ER first; then UPTREND/WATCH; cite the decisive qualitative finding. Include
the screen ret/WR only in screen mode.)

## Dropped at the gate
- Brief note on what the gates removed (illiquid, restricted segment, falling knives) — proves
  the gate is doing its job.

## Recommended next step
- The 1–3 strongest FIT candidates to /calibrate then paper-trade for 2–4 weeks before adding.
```

## Step 4 — Advisory follow-up (do NOT act without confirmation)

This skill never edits the watchlist. After printing the shortlist + the single best candidate:
- Offer to add the top FIT candidate(s) to the `interested:` list in `config.yaml` (monitored,
  **not** traded) — only if confirmed.
- Suggest `/calibrate <SYMBOL>` then 2–4 weeks of paper trading before promoting any name to the
  traded `watchlist`.

Never add a name directly to the traded `watchlist`, and never edit `config.yaml` without
explicit confirmation.
