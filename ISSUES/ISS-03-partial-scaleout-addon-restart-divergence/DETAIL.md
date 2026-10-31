# ISS-03: Partial scale-out on an add-on position: pro-rata in memory vs FIFO in DB — reboot changes avg entry, pool, loss-block arming

Source: Independent production-safety review 2026-10-17, finding 4. Reproduced verbatim; dated addenda below. Never delete.

---

**4. MEDIUM: a partial scale-out on a position with add-ons gets different accounting after the overnight reboot.** (risk/manager.py:685-699 vs store.py:583-611)
- In memory, a partial sale reduces the add-on cost basis pro rata. The DB uses FIFO (parent lot sold first).
- Since the box reboots daily, every such multi-day position goes through this.
- After the reboot the pool usage, blended average entry, realised P&L, cumulative P&L and **whether the loss block arms** all change.
- `/tmp/review_tests/test_restart_divergence.py` shows it: parent 100@100, add-on 50@90, partial 75@105, close @95.
  - Pool: 2,250 without reboot vs 4,500 after reboot.
  - Average entry: 96.67 vs 93.33.
  - Loss block: armed without reboot, **not armed** after reboot.
- The backtest has no reboots, so live and backtest disagree. Confidence: verified by test.

## Addendum 2026-10-17 — impact traced through the code (for the owner)

Worked example: parent 100 @ ₹100 + add-on 50 @ ₹90 (cost ₹14,500, avg ₹96.67) → scale-out 75 @ ₹105 → reboot → final 75 @ ₹95.
True round-trip P&L = ₹15,000 − ₹14,500 = **+₹500**.

| | No reboot (in-memory, proportional) | After reboot (DB, oldest-first) |
|---|---|---|
| Left after scale-out | 50 @100 + 25 @90, avg 96.67 | 25 @100 + 50 @90, avg 93.33 |
| Scale-out P&L booked | +₹625 | +₹625 (booked before the reboot) |
| Final sale P&L | −₹125 → **loss block arms** | +₹125 → **no block** |
| Cumulative P&L added | +₹500 (correct) | +₹750 (**₹250 phantom**) |
| Add-on pool in use | ₹2,250 | ₹4,500 |

Mixing the two conventions books phantom P&L into `cumulative_pnl`, which since ISS-04 sizes the base sleeve.

Where each part of the system reads from:
- Decisions (loss-block arming, pool usage, tier count, cumulative P&L → capital) — `RiskManager`, proportional in memory;
  re-seeded from the DB `addon_lots` at every boot (`main.py` ~352/424 → `seed_position` + `seed_scale_in`).
- Dashboard open-position lot ladder / avg cost / deployed — `analytics.position_entry_legs` reads the DB `addon_lots`
  directly → shows the oldest-first numbers **immediately after a scale-out**, not only after the reboot.
- Dashboard closed trades / monthly round trips / cumulative P&L cards — rebuilt from the orders table
  (`match_trades`, FIFO); round-trip totals are identical under either convention → not affected.
- Backtest — RiskManager proportional (no reboots) → the validated behaviour is the proportional one.
- Stale exits — anchored on the parent entry price only → not affected.

Proposed fix: `Store.consume_position_lots` reduces the parent and every add-on lot proportionally (integer shares,
largest-remainder rounding, ≤ 1 share off the in-memory ₹ split); the reviewer's repro becomes a permanent
reboot-vs-no-reboot equality test. RiskManager, backtest and dashboard code unchanged. No migration (no live add-on
positions exist yet).

## Addendum 2026-10-17 — fixed

Guide: `to_develop/completed/2026-10-17_ISS-03_proportional-lot-consumption.md`. Follow-up TD-015 (parent-only notional after scale-out + reboot).
