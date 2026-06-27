---
description: Completely purge every trace of a single stock from the live bot database on the remote EC2 server — orders, trades, open_positions, signals, and per-stock state keys — then reconcile cumulative_pnl. Use when a manual/external trade (a buy or sell done by hand in Kite, outside the bot) has polluted the bot's accounting and you need the trade history and P&L to read as if the bot never touched that symbol. Destructive and remote: always backup, validate exact rowcounts, and commit only on the expected count. Pass one NSE:SYMBOL.
argument-hint: NSE:SYMBOL [--dry-run]
---

Remove all evidence of one stock from the bot's **live** SQLite DB on EC2 so the trade
history and P&L stay clean of manual instructions. The bot only auto-accounts its own
fills; an **external** sell/buy you did by hand in Kite never gets matched against the
bot's open position, so it leaves a phantom open position, an orphan order, stale trailing
state, and a `cumulative_pnl` that no longer adds up. This skill purges the symbol cleanly.

## Non-negotiable safety rules (this writes to the live production DB)

1. **Never run a bare `DELETE`/`UPDATE`.** Every mutation runs inside a Python block that
   checks `cursor.rowcount` against the **exact** number you confirmed in the inspect step,
   and `commit()`s **only** if it matches — otherwise `rollback()`. One unexpected row = abort.
2. **Always take an online backup first** (`sqlite3.backup()` — consistent, no downtime).
   Keep the backup until the user has validated the UI looks right, then remove it.
3. **Inspect before you touch.** Print every row you intend to change, and show it to the user.
4. **Get explicit user confirmation** before the mutation step. This is irreversible-in-practice.
5. **Do not stop the service.** `sqlite3.backup()` and rowcount-guarded writes are safe while
   the bot runs. (If the bot holds the symbol in memory, a restart after the purge clears it.)

## Environment (from CLAUDE.md / ssh config)

- Host alias: `ssh trader` (port 9654)
- DB: `/opt/trader/data/market.db`, owned by the `trader` user
- Always run as: `sudo -u trader /opt/trader/.venv/bin/python -c "..."`
- Tables keyed by `instrument`: `orders`, `trades`, `open_positions`, `signals`
- Per-stock `state` keys: `<INST>.paused`, `<INST>.peak_close`, `<INST>.max_gain_pct`
- Global `state` key: `cumulative_pnl` (lifetime P&L; persisted, survives restarts)
- **Keep `candles`** — that's market data, not trade history; purging it loses price history for no benefit.
- **Watch the exchange prefix.** A manual trade may be logged as `BSE:SYMBOL` while the bot
  trades `NSE:SYMBOL`. Always match with `instrument LIKE '%SYMBOL%'` in the inspect step and
  reconcile both rows. (In the GAIL cleanup the manual sell came through as `BSE:GAIL`.)

Require a symbol in `$ARGUMENTS` (e.g. `NSE:GAIL`). If none, ask for one and stop. Derive the
bare symbol (`GAIL`) for `LIKE` matching.

## `--dry-run` mode (read-only — run, then stop)

If `$ARGUMENTS` contains `--dry-run`, do **only Step 1 (inspect)** and **Step 3's P&L
computation as a preview**, then **stop without backup or any write**. Nothing touches the DB.
Produce exactly the plan the real run would execute:

- The rows found per table (`orders`, `trades`, `open_positions`, `signals`, `state` keys),
  with the exchange-prefix variants spelled out.
- The **exact DELETE/UPDATE/rekey statements** that the real run would issue, and the
  **expected rowcount** for each (these become the `EXPECT_*` guards in Step 4).
- The `cumulative_pnl` reconciliation: `old_pnl`, the symbol's realised P&L, and the resulting
  `new_pnl` — clearly labelled "would set" (not set).
- A one-line summary: "Real run would commit N orders, N trades, … and set cumulative_pnl X→Y."

End with: re-run without `--dry-run` to execute. Do not ask for confirmation in dry-run — there
is nothing to confirm; it is purely informational.

---

## Step 1 — Inspect (read-only; show the user everything)

```bash
ssh trader "sudo -u trader /opt/trader/.venv/bin/python -c \"
import sqlite3
c=sqlite3.connect('/opt/trader/data/market.db'); c.row_factory=sqlite3.Row
SYM='GAIL'   # bare symbol
print('=== orders (ALL statuses, any exchange) ===')
for r in c.execute(\\\"SELECT order_id,instrument,direction,quantity,price,status,mode,placed_at FROM orders WHERE instrument LIKE '%'||?||'%' ORDER BY placed_at\\\",(SYM,)): print(dict(r))
print('=== trades ===')
for r in c.execute(\\\"SELECT trade_id,order_id,instrument,direction,quantity,price,traded_at FROM trades WHERE instrument LIKE '%'||?||'%' ORDER BY traded_at\\\",(SYM,)): print(dict(r))
print('=== open_positions ===')
for r in c.execute(\\\"SELECT instrument,entry_price,quantity,entry_time FROM open_positions WHERE instrument LIKE '%'||?||'%'\\\",(SYM,)): print(dict(r))
print('=== signals (count only) ===')
print(c.execute(\\\"SELECT COUNT(*) n FROM signals WHERE instrument LIKE '%'||?||'%'\\\",(SYM,)).fetchone()['n'],'rows')
print('=== state keys ===')
for r in c.execute(\\\"SELECT key,value FROM state WHERE key LIKE '%'||?||'%'\\\",(SYM,)): print(dict(r))
print('=== cumulative_pnl ===')
print(dict(c.execute(\\\"SELECT key,value FROM state WHERE key='cumulative_pnl'\\\").fetchone()))
\"" 2>&1
```

Also pull recent logs for context on what the bot did vs. what was manual:

```bash
ssh trader "sudo journalctl -u trader --since '$(date +%Y-%m-%d) 03:00' --no-pager 2>/dev/null | grep -i SYMBOL"
```

From the inspect output, decide the realised-P&L reconciliation (Step 3) and present a plan:
list the exact rows to delete/rekey and the expected rowcount for each.

---

## Step 2 — Backup (online, consistent)

```bash
ssh trader "sudo -u trader /opt/trader/.venv/bin/python -c \"
import sqlite3
s=sqlite3.connect('/opt/trader/data/market.db')
d=sqlite3.connect('/opt/trader/data/market.db.bak-SYMBOL-$(date +%Y%m%d)')
s.backup(d); d.close()
print('BACKUP ok -> market.db.bak-SYMBOL-$(date +%Y%m%d)')
\"" 2>&1
```

---

## Step 3 — Reconcile cumulative_pnl (the careful part)

`cumulative_pnl` is lifetime realised P&L. Purging a symbol's **realised** (closed, bot-made)
round-trips means its P&L must be **subtracted** from `cumulative_pnl`, or the equity curve
double-counts a stock that no longer exists in the history.

- Compute the symbol's net realised P&L from its **COMPLETE** bot orders only
  (`sum(SELL qty*price) - sum(BUY qty*price)` for matched bot fills; exclude the manual order).
  Present the number to the user.
- A still-**open** phantom position has no realised P&L — deleting `open_positions` alone needs
  no `cumulative_pnl` change.
- If `cumulative_pnl` itself is corrupted (e.g. it was overwritten with a capital cap rather
  than true P&L — a known past bug), don't subtract piecemeal; recompute the correct lifetime
  value and set it directly. The store exposes `RiskManager.reset_cumulative_pnl(value)` for the
  in-memory side, but the **persisted** value is just `state.cumulative_pnl` — set it with the
  guarded write below and let the next restart seed from it.

Always show the user `old_pnl`, the symbol's realised P&L, and `new_pnl` and get a yes before writing.

---

## Step 4 — Execute (rowcount-guarded; commit only on exact match)

Fill in the **exact** expected counts confirmed in Step 1. Example shape (adapt the WHERE
clauses and `EXPECT_*` to what you actually found):

```bash
ssh trader "sudo -u trader /opt/trader/.venv/bin/python -c \"
import sqlite3
SYM='GAIL'
NEW_PNL=<new_cumulative_pnl>            # from Step 3, or omit the state write if unchanged
con=sqlite3.connect('/opt/trader/data/market.db')
n_ord = con.execute(\\\"DELETE FROM orders        WHERE instrument LIKE '%'||?||'%'\\\",(SYM,)).rowcount
n_trd = con.execute(\\\"DELETE FROM trades        WHERE instrument LIKE '%'||?||'%'\\\",(SYM,)).rowcount
n_pos = con.execute(\\\"DELETE FROM open_positions WHERE instrument LIKE '%'||?||'%'\\\",(SYM,)).rowcount
n_sig = con.execute(\\\"DELETE FROM signals       WHERE instrument LIKE '%'||?||'%'\\\",(SYM,)).rowcount
n_st  = con.execute(\\\"DELETE FROM state          WHERE key LIKE '%'||?||'%'\\\",(SYM,)).rowcount
con.execute(\\\"UPDATE state SET value=? WHERE key='cumulative_pnl'\\\",(NEW_PNL,))
print('orders',n_ord,'trades',n_trd,'open_pos',n_pos,'signals',n_sig,'state',n_st)
EXPECT_ORD, EXPECT_TRD, EXPECT_POS, EXPECT_SIG, EXPECT_ST = <fill from Step 1>
if (n_ord,n_trd,n_pos,n_sig,n_st)==(EXPECT_ORD,EXPECT_TRD,EXPECT_POS,EXPECT_SIG,EXPECT_ST):
    con.commit(); print('COMMITTED')
else:
    con.rollback(); print('ROLLED BACK (unexpected rowcounts)')
con.close()
\"" 2>&1
```

If you only need to **keep** a legitimate bot round-trip but drop a phantom position (the GAIL
case: a real BSE-logged sell that should be rekeyed to NSE and matched, plus a stale open row to
delete), rekey instead of delete — same rowcount guard:

```python
c1 = con.execute("UPDATE orders SET instrument='NSE:SYMBOL' WHERE order_id='<id>' AND instrument='BSE:SYMBOL' AND direction='SELL'")
c2 = con.execute("DELETE FROM open_positions WHERE instrument='NSE:SYMBOL'")
if c1.rowcount==1 and c2.rowcount==1: con.commit()
else: con.rollback()
```

---

## Step 5 — Verify, then clean up

1. Re-run the Step 1 inspect — every section should now be empty (or show only the intentionally
   kept/rekeyed rows) and `cumulative_pnl` should equal `new_pnl`.
2. Ask the user to confirm the **UI** reads correctly (trade history, open positions, P&L,
   drawdown). The bot may need a restart if it still holds the symbol in memory:
   `ssh trader "sudo systemctl restart trader"` — only if the user wants it.
3. **After** the user validates the UI, remove the backup:
   `ssh trader "sudo -u trader rm -v /opt/trader/data/market.db.bak-SYMBOL-<date>"`
   Do **not** remove it before validation.

## Output

Report: what was found, the backup path, the realised-P&L reconciliation (old → new), the exact
rowcounts committed per table, and the verification result. If anything rolled back, stop and
surface the mismatch — do not retry blindly.
