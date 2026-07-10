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


def _parse_iso(ts) -> datetime | None:
    try:
        return datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None


def _hold_hours(entry, exit) -> float | None:
    a, b = _parse_iso(entry), _parse_iso(exit)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0


def exit_reason_breakdown(trades: list[dict]) -> list[dict]:
    """Group closed trades by exit reason (#3). Per reason: trade count, total
    gross P&L, average hold (hours), and share of total gross P&L.

    A None/empty reason is relabelled "MANUAL/EXTERNAL" (a non-strategy sell).
    Deliberately NO win-rate-per-reason — that metric is circular for this
    strategy; only descriptive count / P&L / hold are reported.
    """
    groups: dict[str, dict] = {}
    for t in trades:
        reason = t.get("exit_reason") or "MANUAL/EXTERNAL"
        g = groups.setdefault(reason, {"reason": reason, "count": 0,
                                       "total_pnl": 0.0, "_holds": []})
        g["count"] += 1
        g["total_pnl"] += t.get("gross_pnl") or 0.0
        h = _hold_hours(t.get("entry_time"), t.get("exit_time"))
        if h is not None:
            g["_holds"].append(h)
    grand = sum(g["total_pnl"] for g in groups.values())
    rows = []
    for g in groups.values():
        holds = g.pop("_holds")
        g["avg_hold_hours"] = round(sum(holds) / len(holds), 2) if holds else None
        g["pnl_share_pct"] = (g["total_pnl"] / grand * 100.0) if grand else 0.0
        rows.append(g)
    rows.sort(key=lambda r: (r["count"], r["total_pnl"]), reverse=True)
    return rows


def per_stock_scorecard(trades: list[dict], open_positions: list[dict]) -> list[dict]:
    """Per-instrument live performance (#6): trade count, gross P&L, average
    hold, last exit reason/time, and currently-open quantity. Instruments that
    are open but have no closed trade still appear (n_trades=0). Sorted by gross
    P&L descending (winners first). Costs/net are layered on by the caller."""
    cards: dict[str, dict] = {}
    for t in trades:
        inst = t["instrument"]
        c = cards.setdefault(inst, {"instrument": inst, "n_trades": 0,
                                    "gross_pnl": 0.0, "_holds": [],
                                    "last_exit_reason": None, "last_exit_time": None,
                                    "open_qty": 0})
        c["n_trades"] += 1
        c["gross_pnl"] += t.get("gross_pnl") or 0.0
        h = _hold_hours(t.get("entry_time"), t.get("exit_time"))
        if h is not None:
            c["_holds"].append(h)
        xt = t.get("exit_time")
        if xt is not None and (c["last_exit_time"] is None or str(xt) > str(c["last_exit_time"])):
            c["last_exit_time"] = xt
            c["last_exit_reason"] = t.get("exit_reason")
    for p in open_positions:
        inst = p["instrument"]
        c = cards.setdefault(inst, {"instrument": inst, "n_trades": 0,
                                    "gross_pnl": 0.0, "_holds": [],
                                    "last_exit_reason": None, "last_exit_time": None,
                                    "open_qty": 0})
        c["open_qty"] = int(p.get("quantity") or 0)
    rows = []
    for c in cards.values():
        holds = c.pop("_holds")
        c["avg_hold_hours"] = round(sum(holds) / len(holds), 2) if holds else None
        rows.append(c)
    rows.sort(key=lambda r: r["gross_pnl"], reverse=True)
    return rows


def drawdown_stats(trades: list[dict], capital: float) -> dict:
    """Underwater / drawdown stats (#7) over the gross-P&L equity curve of
    closed trades, ordered by exit time. Returns the equity and underwater
    series plus peak, max drawdown, current drawdown (₹ and %), and days spent
    in the current drawdown. All-zero / empty series when there are no trades."""
    dated = sorted((t for t in trades if _parse_iso(t.get("exit_time"))),
                   key=lambda t: _parse_iso(t["exit_time"]))
    if not dated:
        return {"equity": [], "underwater": [], "peak": 0.0,
                "max_dd": 0.0, "max_dd_pct": 0.0,
                "current_dd": 0.0, "current_dd_pct": 0.0, "days_in_drawdown": 0}
    equity, underwater = [], []
    cum = 0.0
    peak = float("-inf")
    peak_time = _parse_iso(dated[0]["exit_time"])
    max_dd = 0.0
    for t in dated:
        cum += t.get("gross_pnl") or 0.0
        if cum > peak:
            peak = cum
            peak_time = _parse_iso(t["exit_time"])
        equity.append(cum)
        dd = cum - peak           # <= 0
        underwater.append(dd)
        max_dd = min(max_dd, dd)
    current_dd = equity[-1] - peak
    last_time = _parse_iso(dated[-1]["exit_time"])
    days = (last_time - peak_time).days if (current_dd < 0 and last_time and peak_time) else 0
    cap = capital or 0.0
    return {
        "equity": equity, "underwater": underwater, "peak": peak,
        "max_dd": abs(max_dd), "max_dd_pct": (abs(max_dd) / cap * 100.0) if cap else 0.0,
        "current_dd": abs(current_dd),
        "current_dd_pct": (abs(current_dd) / cap * 100.0) if cap else 0.0,
        "days_in_drawdown": days,
    }


def position_entry_legs(open_positions: list[dict]) -> dict[str, dict]:
    """Scale-in lot ladder for still-open positions. For each open position with
    at least one add-on lot (from the persisted ``addon_lots`` JSON), returns:
        {instrument: {legs: [{qty, price, time, tier}], addon_qty, parent_qty,
                      total_qty, avg_cost}}
    tier 0 (the parent) is included as the first leg so the UI can render the
    whole ladder. Positions without add-ons are omitted."""
    out: dict[str, dict] = {}
    for p in open_positions:
        lots = p.get("addon_lots") or []
        if not lots:
            continue
        inst = p["instrument"]
        total_qty = int(p.get("quantity") or 0)
        addon_qty = sum(int(l.get("qty") or 0) for l in lots)
        parent_qty = max(total_qty - addon_qty, 0)
        legs = [{"qty": parent_qty, "price": p.get("entry_price"),
                 "time": p.get("entry_time"), "tier": 0}]
        legs += [
            {"qty": int(l.get("qty") or 0), "price": l.get("price"),
             "time": l.get("date"), "tier": i + 1}
            for i, l in enumerate(lots)
        ]
        cost = sum((l["price"] or 0.0) * l["qty"] for l in legs)
        out[inst] = {
            "legs": legs, "addon_qty": addon_qty, "parent_qty": parent_qty,
            "total_qty": total_qty,
            "avg_cost": (cost / total_qty) if total_qty else 0.0,
        }
    return out


def position_exit_legs(orders: list[dict], open_positions: list[dict]) -> dict[str, dict]:
    """Scale-out lifecycle for still-open positions (#14). For each open
    position, collect the SELL legs already taken against the open lot (sells
    placed at/after the position's entry_time). Returns, per instrument with at
    least one such leg: legs [{qty, price, reason, time}], sold_qty, open_qty,
    original_qty (open + sold). Positions with no partial sells are omitted.

    `orders` are the same enriched order dicts fed to match_trades — keys
    instrument, direction, quantity, price, ts, and optional exit_reason."""
    out: dict[str, dict] = {}
    for p in open_positions:
        inst = p["instrument"]
        entry = str(p.get("entry_time") or "")
        legs = [
            {"qty": int(o.get("quantity") or 0), "price": o.get("price"),
             "reason": o.get("exit_reason"), "time": o.get("ts")}
            for o in orders
            if o.get("instrument") == inst and o.get("direction") == "SELL"
            and str(o.get("ts") or "") >= entry
        ]
        legs = [l for l in legs if l["qty"] > 0]
        if not legs:
            continue
        sold = sum(l["qty"] for l in legs)
        open_qty = int(p.get("quantity") or 0)
        out[inst] = {"legs": legs, "sold_qty": sold, "open_qty": open_qty,
                     "original_qty": open_qty + sold}
    return out


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
