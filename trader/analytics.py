"""
Shared, pure trade-analytics helpers — no I/O, no Kite, no backtest engine.

Safe to import from both the live/UI path and the backtest scripts: these
functions only operate on plain trade dicts and return plain dicts.
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta


def match_trades(orders: list[dict]) -> list[dict]:
    """FIFO-match BUY and SELL fills per instrument into closed-trade records.

    Correctly handles scale-out (partial) exits: one BUY lot can be split
    across several SELLs (and vice-versa), so a 7-share entry exited as 4 + 3
    yields two closed-trade records of 4 and 3 — not one phantom record of 7.

    Args:
        orders: dicts with keys ``instrument``, ``direction`` ('BUY'|'SELL'),
            ``price``, ``quantity``, ``ts`` (sortable), and optional
            ``exit_reason`` (read off SELL legs).

    Returns one record per matched slice:
        {instrument, entry_price, exit_price, quantity, gross_pnl,
         entry_time, exit_time, exit_reason}
    gross_pnl is None when either price is missing. A SELL with no open BUY lot
    left is ignored (defensive — e.g. an entry that predates the order history).
    """
    lots: dict[str, deque] = defaultdict(deque)  # instrument -> [ [qty, price, ts], ... ]
    trades: list[dict] = []
    for o in sorted(orders, key=lambda x: str(x.get("ts") or "")):
        inst = o["instrument"]
        qty = int(o.get("quantity") or 0)
        if qty <= 0:
            continue
        price = o.get("price")
        ts = o.get("ts")
        if o["direction"] == "BUY":
            lots[inst].append([qty, price, ts])
            continue
        # SELL — consume open BUY lots FIFO.
        remaining = qty
        dq = lots[inst]
        while remaining > 0 and dq:
            lot = dq[0]
            take = min(remaining, lot[0])
            entry_price, exit_price = lot[1], price
            gross = ((exit_price - entry_price) * take
                     if entry_price is not None and exit_price is not None else None)
            trades.append({
                "instrument": inst,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": take,
                "gross_pnl": gross,
                "entry_time": lot[2],
                "exit_time": ts,
                "exit_reason": o.get("exit_reason"),
            })
            lot[0] -= take
            remaining -= take
            if lot[0] == 0:
                dq.popleft()
    return trades


def compute_utilisation(
    trades: list[dict],
    capital: float,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    bucket: str = "month",
) -> dict:
    """Reconstruct capital deployment and open-position count over time from a
    trades list — to judge whether capital is under-utilised (i.e. whether
    `max_capital_per_stock_pct` / `max_open_positions` can be raised).

    A trade occupies `entry × qty` of capital from `entry_date` to `exit_date`.
    State only changes at fills, so we sample on a daily (weekday) grid and bucket
    monthly. Utilisation % is measured against the *compounding* available capital
    at that time (base capital + realised P&L of trades already closed), matching
    how RiskManager sizes positions.

    Returns:
        {
          "monthly": [ {month, entries, avg_deployed, peak_deployed,
                        avg_util_pct, peak_util_pct, avg_positions, peak_positions}, ... ],
          "overall": {time_avg_util_pct, peak_util_pct, peak_deployed,
                      avg_positions, peak_positions, peak_date},
        }
    All keys present (zeroed) when there are no trades.
    """
    empty_overall = {
        "time_avg_util_pct": 0.0, "peak_util_pct": 0.0, "peak_deployed": 0.0,
        "avg_positions": 0.0, "peak_positions": 0, "peak_date": None,
    }
    dated = [t for t in trades if t.get("entry_date") and t.get("exit_date")]
    if not dated:
        return {"monthly": [], "overall": empty_overall}

    start = from_dt or min(t["entry_date"] for t in dated)
    end = to_dt or max(t["exit_date"] for t in dated)

    # Daily weekday grid.
    days: list[datetime] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    if not days:
        days = [start]

    monthly: dict[str, dict] = {}
    util_all: list[float] = []
    pos_all: list[int] = []
    peak_util = 0.0
    peak_dep = 0.0
    peak_pos = 0
    peak_date = None

    for s in days:
        deployed = sum(t["entry"] * t["qty"] for t in dated if t["entry_date"] <= s < t["exit_date"])
        npos = sum(1 for t in dated if t["entry_date"] <= s < t["exit_date"])
        realised = sum(t["pnl"] for t in dated if t["exit_date"] <= s)
        avail = capital + realised
        util = deployed / avail * 100 if avail > 0 else 0.0

        mk = s.strftime("%Y-%m-%d" if bucket == "day" else "%Y-%m")
        b = monthly.setdefault(mk, {"dep": [], "util": [], "pos": [], "entries": 0})
        b["dep"].append(deployed); b["util"].append(util); b["pos"].append(npos)

        util_all.append(util); pos_all.append(npos)
        if util > peak_util:
            peak_util = util
        if deployed > peak_dep:
            peak_dep = deployed
        if npos > peak_pos:
            peak_pos = npos; peak_date = s

    for t in dated:
        mk = t["entry_date"].strftime("%Y-%m-%d" if bucket == "day" else "%Y-%m")
        if mk in monthly:
            monthly[mk]["entries"] += 1

    monthly_rows = [
        {
            "month": mk,
            "entries": b["entries"],
            "avg_deployed": sum(b["dep"]) / len(b["dep"]),
            "peak_deployed": max(b["dep"]),
            "avg_util_pct": sum(b["util"]) / len(b["util"]),
            "peak_util_pct": max(b["util"]),
            "avg_positions": sum(b["pos"]) / len(b["pos"]),
            "peak_positions": max(b["pos"]),
        }
        for mk, b in sorted(monthly.items())
    ]
    overall = {
        "time_avg_util_pct": sum(util_all) / len(util_all) if util_all else 0.0,
        "peak_util_pct": peak_util,
        "peak_deployed": peak_dep,
        "avg_positions": sum(pos_all) / len(pos_all) if pos_all else 0.0,
        "peak_positions": peak_pos,
        "peak_date": peak_date,
    }
    return {"monthly": monthly_rows, "overall": overall}
