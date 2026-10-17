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
