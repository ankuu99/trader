# Production-safety review — scale-in + loss block + pre-order-reject fix (2026-10-17)

Independent read-only review (subagent) of d9e7bc7 + 15d2fca, as deployed on EC2 (server clean at
15d2fca), focused on the daily restart and parameter restore. Report reproduced verbatim below.
Tracked as ISS-01 … ISS-09 (`ISSUES.md`). Throwaway repro test: `/tmp/review_tests/test_restart_divergence.py`.

---

## Production-safety review: d9e7bc7 + 15d2fca (deployed on EC2, server is clean at 15d2fca)

**In short:** nothing here can lose money today. The account is at ₹4.79L, below the ₹6L base, so the scale-in pool is ₹0 and no add-on order can be placed. The loss block and the pre-order-reject fix work as intended. There are four real problems, though, and they start to matter as soon as the account goes above ₹6L or a position has both an add-on and a partial sale. I made no changes to the repo or the server. My throwaway test is in `/tmp/review_tests/`.

### Findings, most important first

**1. MEDIUM-HIGH: the scale-in pool can be funded by money that isn't there after a same-day restart.** (main.py:84-85, 494)
- `margins["available"]["cash"]` is the **opening** balance. It does not drop when the bot buys during the day.
- After a restart on the same day as some buys, equity = cash + deployed counts those buys twice.
- Seen in the server logs: the 10-15 evening restart logged `account_equity=611981 (cash=157733 + deployed=454248)`. The next boot showed the real figure, about ₹4.88L.
- With the new code that restart would create a ₹12k pool, and lift effective capital to ₹6L, from money that doesn't exist.
- Effect: during a mid-session crash or deploy, add-on and base orders compete for cash that isn't there, and Kite rejects them for insufficient funds. A same-day sell does the opposite (understates equity), which is the safe direction.
- Fix: use `available.live_balance` or `net`. Confidence: verified (logs plus code).

**2. MEDIUM: a broker-rejected add-on is re-placed on every decision candle.** (risk/manager.py:384-475, lr_extrema.py:289-306)
- Add-on signals carry no state. After a REJECTED, `on_order_cancelled` frees the pending lock, and the spacing and tier checks still pass.
- So a new add-on order goes out every 15m bar while P(min) stays above threshold, with a Telegram reject alert each time.
- Insufficient-funds rejects (#1, #3, #6) trigger this directly.
- Suggest: after a broker reject, set `last_invest_date` to today or mark the add-on blocked. Confidence: verified by reading.

**3. MEDIUM (old bug, new exposure): `cumulative_pnl` is counted twice.** (risk/manager.py:128)
- `capital_available` adds `cumulative_pnl` on top of a Kite equity figure that already includes realised P&L.
- Now that the pool equals equity above ₹6L, base entries plus pool together promise ₹cum_pnl more than the account's cash.
- It's harmless right now only because `cumulative_pnl` is 0.0 in the state table. It comes back as profitable trades close.

**4. MEDIUM: a partial scale-out on a position with add-ons gets different accounting after the overnight reboot.** (risk/manager.py:685-699 vs store.py:583-611)
- In memory, a partial sale reduces the add-on cost basis pro rata. The DB uses FIFO (parent lot sold first).
- Since the box reboots daily, every such multi-day position goes through this.
- After the reboot the pool usage, blended average entry, realised P&L, cumulative P&L and **whether the loss block arms** all change.
- `/tmp/review_tests/test_restart_divergence.py` shows it: parent 100@100, add-on 50@90, partial 75@105, close @95.
  - Pool: 2,250 without reboot vs 4,500 after reboot.
  - Average entry: 96.67 vs 93.33.
  - Loss block: armed without reboot, **not armed** after reboot.
- The backtest has no reboots, so live and backtest disagree. Confidence: verified by test.

**5. LOW-MEDIUM: the loss block counts sessions with a wall clock, not a trading calendar.**
- The scheduler and the box both run Mon–Fri with no holiday list. On 2026-10-02 (an NSE holiday) post_market ran and logged "Risk manager daily reset" (verified). Each weekday holiday therefore makes the block one trading session shorter than in the backtest.
- The opposite happens on a trading day where post_market never runs (crash through 15:35, box down). The block then lasts one session longer.
- A 15m exit on the 15:15 candle fills the next morning in the backtest but the same day live, so live is one more session shorter in that case.
- Otherwise the "earliest re-entry is D+3" rule matches `engine.reset_day`.

**6. LOW: if Kite margins fail at both boot and the 09:00 retry, the pool falls back to 10% of ₹6L = ₹60k of unfunded cash for the whole session.** (config.py `scale_in_budget`)
- Suggest `set_scale_in_budget(0)` at live boot, before the margins call.
- The margins call has never failed at boot since September (checked in the logs).

**7. LOW: add-on fills that arrive outside the normal path.**
- **Pending at restart:** a pending add-on order is not re-locked, because main.py:468 skips held instruments.
- **Fill while down:** that fill is never delivered, so the DB misses the lot. A full exit then sells only what the DB holds and leaves orphan shares, and the next signal can place a second add-on.
- **Unknown order ID:** a fill that arrives later with an unknown order ID is booked as a *parent* BUY. That overwrites the position quantity and entry price.
- **Partial fill then CANCELLED:** the filled quantity is ignored.
- **No quantity check:** startup and post-market only check whether a holding exists, never its quantity. A mismatch is never detected, and if the DB holds more than Kite, the exit SELL is rejected in a loop.
- All of this needs a seconds-long window with MARKET orders, and most of it existed before for parent orders.

**8. LOW: `_instrument_orders` keeps the add-on order as the fallback context** (orders/manager.py:327-328). A manual BUY of a held symbol would be recorded as an add-on lot.

**9. LOW: blocks for removed stocks come back.** `load_loss_reentry` only reads watchlist stocks, so a removed stock's key stays in the DB and its old countdown returns if the stock is re-added.

**10. LOW, by design:** while a stock is loss-blocked, stock-paused or `quantity_zero`, it now writes one rejected signal row per decision candle instead of freezing silently.

### Checked and OK
- **`on_pre_order_reject`:**
  - It does nothing for EXIT signals and for any signal while `position` is set, so add-ons are never touched.
  - It keeps the guard for `already_in_position` and `pending_order_exists`.
  - Live positions are restored from the DB before the feed starts, so after a restart no normal path leaves the strategy flat while risk holds the position.
  - No signals come from the tick path. The broker-reject re-fire loop is unchanged.
- **Loss block:**
  - It arms only on a real-price losing full close. The post-market eviction close (exit price 0) and the startup "closed externally" deletion don't arm it.
  - It is saved after every full close and after post-market `reset_day`, and restored at boot before any trading.
  - Evening deploys and mid-session restarts restore it correctly.
- **Parent-frozen anchor across restart:** the restart's synthetic fill uses the DB parent `entry_price`. `lr_extrema` returns early for add-on fills, cancels and rejects. `add_position_lot` doesn't touch the parent entry.
- **Tier count, spacing date and `_scale_in_deployed`** are rebuilt from `addon_lots` when there has been no partial sale.
- **Pool setup:** `set_scale_in_budget` is applied before the feed starts, and equity now includes add-on cost basis.
- **Ceiling change:** switching the effective-capital ceiling to `base_capital` makes no practical difference (the retry only runs when startup never set it). It is safe with compounding, since the per-stock cap already uses `base_capital`.
- **Eviction:** post-market eviction checks positions() plus holdings() and only looks at whether a holding exists, so add-ons cause no duplicate buys there.
- **Dashboard:** the new rows handle a missing `account_equity`.
- **Tests:** at a clean HEAD copy, 520 pass and 2 fail (`test_parity_golden`, the health-strip test). Both already fail at 3c5234c, so these commits didn't cause them. The uncommitted swing-feature edits in the local working tree are not deployed.

---

## Owner decisions (2026-10-17)

> 1. yes,
> 2 note it was tried, but dont block, given the model continues to remain bullish on that. let;s discuss this beofre we dicde
> 3 did not understand
> 4. yes we shoudl fix.
> remainig can be noted for later.

Mapping (numbering of the summary given to the owner, not the review's): 1 = finding 1 (ISS-01), 2 = finding 2
(ISS-02), 3 = finding 4 (ISS-03), 4 = finding 3 (ISS-04). Everything else → noted for later.
