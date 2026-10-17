# Pre-order reject freeze — baseline re-runs (2026-10-16)

**Bug:** `risk.validate()` returning None for an ENTRY never reached the strategy, so its
pending-entry guard stayed armed and the stock emitted nothing for the rest of the backtest
(live: until restart). Fix: `Strategy.on_pre_order_reject()` (engine + both live paths),
`tests/test_pre_order_reject_guard.py`. Every row below is the current code and cache, 21-name
watchlist, ₹40k/stock unless noted, 2025-01-01 → 2026-09-03 (YTD rows 2026-01-01 → 2026-10-15).
"Unpatched" = the hook disabled, i.e. the old engine behaviour.

## Capital / scale-in / slow-TF cap

| Scenario | Unpatched | Fixed |
|---|---|---|
| ₹6L @ 6.67 % (baseline) | ₹472.0k · 820t · DD 6.7 % · Calmar 6.20 | **₹451.2k · 822t · DD 6.7 % · Calmar 5.96** |
| ₹4L @ 10 % | ₹339.0k · 417t · DD 10.4 % · 4.28 | ₹369.8k · 783t · DD 10.7 % · 4.48 |
| ₹5L @ 8 % | ₹394.2k · 653t · DD 8.4 % · 4.98 | ₹444.3k · 807t · DD 8.1 % · 5.70 |
| ₹8L @ 5 % | ₹455.2k · 829t · DD 4.9 % · 6.37 | ₹455.2k · 829t · DD 4.9 % · 6.37 |
| ₹6L + scale-in (50 %/2/10 %) | ₹516.2k · DD 7.6 % · 5.96 | ₹501.7k · DD 7.6 % · 5.81 |
| ₹8L + scale-in | ₹514.8k · DD 6.0 % · 5.81 | ₹514.8k · DD 6.0 % · 5.81 |
| slow-TF cap 4 | ₹195.5k · DD 6.1 % · 3.00 | ₹278.8k · DD 5.6 % · 4.56 |
| slow-TF cap 6 | ₹247.4k · DD 7.2 % · 3.20 | ₹362.5k · DD 7.6 % · 4.31 |
| YTD watchlist | ₹254.0k · 430t · DD 3.7 % | ₹238.7k · 456t · DD 3.7 % |
| YTD + AJANTPHARM/ABCAPITAL/TATASTEEL | ₹244.7k · 351t · DD 3.5 % | ₹253.1k · 484t · DD 3.7 % |

- **Capital scaling saturates at ₹5L, not ₹6L.** Fixed: ₹4L→₹5L +₹74.5k, ₹5L→₹6L only
  +₹6.9k (DD 8.1→6.7 %, Calmar 5.70→5.96), ₹6L→₹8L +₹4.0k (DD 4.9 %). The "sixth lakh
  out-earns the fifth" and "QUESS un-starves only at ₹6L" findings were freeze artifacts — at ₹4L
  the old engine froze ~half the trades (417 vs 783). ₹6L is still fine (better DD), just not
  for the P&L reason recorded. ₹8L had no capital rejects, so it is unchanged.
- **Scale-in unchanged in shape:** +₹50.5k at ₹6L, DD 6.7→7.6 %, Calmar 5.96→5.81.
- **Slow-TF cap stays falsified** (−₹89k / −₹172k) but at half the old magnitude — every
  `slow_tf_limit` reject used to freeze the name.
- **Adding the three discovery names:** −₹9.3k unpatched → **+₹14.4k fixed**, DD unchanged.

## Re-entry guards (all marked FALSIFIED on the old engine)

| Guard | Unpatched vs baseline | Fixed vs baseline |
|---|---|---|
| Same-day cooldown | −₹273.1k · 248t · Calmar 3.73 | **−₹4.3k** · 766t · DD 6.5 % · Calmar **6.10** |
| Loss re-entry block (3 sessions) | −₹363.2k · 157t · Calmar 2.52 | **−₹31.6k** · 695t · DD **5.1 %** · Calmar **7.37** |
| Discount gate 1.5 % one-sided | −₹229.6k · 272t · Calmar 4.50 | **+₹6.0k** · 775t · DD 6.5 % · Calmar 6.23 |
| Discount band ±0.25 % | −₹106.8k · 546t · Calmar 4.92 | +₹4.1k · 822t · Calmar 6.01 |

A blocked re-entry raised a reject → the stock froze for the rest of the run. That was the
"amputated downstream trade sequence" / "idle capital" mechanism blamed in every one of these
write-ups. Fixed, the guards are roughly P&L-neutral, and the **loss re-entry block cuts DD
6.7 → 5.1 % for −7 % P&L (best Calmar of anything tested here)**. These are single-window,
single-run numbers — a few ₹k is noise — so nothing is enabled. The loss block deserves the
same 4-half-year-window validation the stale re-arm got before any decision.

## Other conclusions possibly contaminated (portfolio engine runs, not yet re-run)

Stale re-arm validation (+₹67k), stale runway ×2, all-15m conversion (₹86k vs ₹314k), swing
features / earlier-trail exits (portfolio legs), pattern-top trend guard, per-stock
recalibrations whose regime race ran inside crowded portfolios. Static replays and
stratifications (name-loss budget, knife gate, drawdown-entry study) don't run the engine and
are unaffected.
