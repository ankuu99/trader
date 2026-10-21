# TD-022: Backtests assume the add-on pool is always funded

Source: discovered 2026-10-22 while reviewing live trading on 2026-10-21. Never delete.

---

The 2026-10-17 enablement of scale-in + loss re-entry block (3 sessions) was validated as a COMBINATION
(`reviews/scalein_lossblock_2020_horizon_20261017.md`): 2020→2026 combo +₹39.1k vs baseline, 6/7 calendar years;
loss block ALONE −₹261.8k, 2/7 years. The backtest funds the add-on pool at budget_pct × capital at all times.

Live, `scale_in_pool()` (`trader/risk/manager.py`) funds it only from Kite equity above base + cumulative P&L.
On 2026-10-21 startup: equity ₹580,590 vs sleeve ₹601,298 → pool 0 → 17 add-on signals rejected
`addon_budget_exhausted` that day, while the loss block rejected 4 QUESS/THANGAMAYL re-entries. So live was running
the block-only configuration — the one that tested worst — not the validated combo.

Context that day: Smallcap 250 −2.26 % (−4.4 % since 10-14), Midcap 100 −1.58 %, NIFTY 50 −0.34 %, VIX 14.6→15.7.
Block-only does pay in sell-offs (Oct-24→Mar-25 correction +₹9.9k, COVID +₹33.9k), so no change was made mid-sell-off.

Owner response: adding funds 2026-10-22 so the pool is funded (~₹21k restores the base sleeve, ~₹81k funds the full
₹60k pool, at estimated equity ≈ ₹5.77L at cost). Equity is read only at boot (`_apply_effective_capital`; pre_market
retries only if boot fetch failed), so a deposit after ~06:46 IST is not seen until the next boot.

Open options (owner to decide; none applied):
1. Gate the loss block on a funded pool (block only when add-ons can fire), or
2. Model the live funding rule in the backtest (pool = equity above sleeve) and re-validate the combo, or
3. Keep the account funded ≥ base + cum P&L + ₹60k as an operating rule and note it in the Scale-in section.
