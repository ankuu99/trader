"""
Shared, pure trade-analytics helpers — no I/O, no Kite, no backtest engine.

Safe to import from both the live/UI path and the backtest scripts: these
functions only operate on plain trade dicts and return plain dicts.
"""

from bisect import bisect_right
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


# --------------------------------------------------------------------------- #
# Return stats (cumulative + annualized) and the Nifty benchmark             #
# --------------------------------------------------------------------------- #

#: Benchmark instrument for the dashboard's "vs market" line. Cached as `day`
#: candles in the normal candles table (main.py warms it at startup/pre/post
#: market); the UI only ever reads it. NSE index instruments live in
#: `kite.instruments("NSE")` with this tradingsymbol.
BENCHMARK_INSTRUMENT = "NSE:NIFTY 50"

#: Annualizing a window shorter than this is extrapolation, not measurement
#: (a +2% week reads as ~180% p.a.). The dashboard blanks `ann_pct` below it.
ANNUALIZE_MIN_DAYS = 90


def annualize(cum_frac: float, days: float, min_days: float = ANNUALIZE_MIN_DAYS) -> float | None:
    """CAGR for a cumulative return fraction earned over `days` calendar days.
    None when the span is below `min_days` or the base is wiped out (1 + r <= 0)."""
    if days is None or days < min_days or days <= 0:
        return None
    base = 1.0 + cum_frac
    if base <= 0:
        return None
    return base ** (365.0 / days) - 1.0


def return_stats(
    net_pnl: float,
    capital: float,
    start: datetime | None,
    end: datetime | None,
    *,
    time_avg_util_pct: float | None = None,
    unrealised_pnl: float | None = None,
    min_days: float = ANNUALIZE_MIN_DAYS,
) -> dict:
    """Cumulative and annualized return of the strategy over [start, end].

    Headline is on `capital` (the config/effective total — what the account
    earned). Two secondaries:
      * on deployed — same P&L over `capital × time_avg_util_pct`, i.e. the edge
        per rupee actually at risk (None when util is unknown / zero);
      * incl. open  — mark-to-market: `net_pnl + unrealised_pnl` on `capital`
        (None when unrealised is not supplied).

    `days` is the calendar span; start should be the later of the window start
    and the first fill (idle time before the bot's first trade must not dilute
    the figure), end is "now" — capital stays at risk through today.

    All `*_ann_pct` keys are None below `min_days` (see `annualize`).
    Everything is None when capital <= 0 or the span cannot be established."""
    out = {
        "days": None, "cum_pct": None, "ann_pct": None,
        "deployed_cum_pct": None, "deployed_ann_pct": None,
        "mtm_cum_pct": None, "mtm_ann_pct": None,
        "annualized": False, "min_days": min_days,
    }
    if not capital or capital <= 0 or start is None or end is None or end < start:
        return out
    days = (end - start).total_seconds() / 86400.0
    out["days"] = days
    cum = net_pnl / capital
    out["cum_pct"] = cum * 100.0
    ann = annualize(cum, days, min_days)
    out["ann_pct"] = ann * 100.0 if ann is not None else None
    out["annualized"] = ann is not None

    if time_avg_util_pct and time_avg_util_pct > 0:
        dep_cap = capital * time_avg_util_pct / 100.0
        dcum = net_pnl / dep_cap
        out["deployed_cum_pct"] = dcum * 100.0
        dann = annualize(dcum, days, min_days)
        out["deployed_ann_pct"] = dann * 100.0 if dann is not None else None

    if unrealised_pnl is not None:
        mcum = (net_pnl + unrealised_pnl) / capital
        out["mtm_cum_pct"] = mcum * 100.0
        mann = annualize(mcum, days, min_days)
        out["mtm_ann_pct"] = mann * 100.0 if mann is not None else None
    return out


def benchmark_return(
    closes: list[dict],
    min_days: float = ANNUALIZE_MIN_DAYS,
) -> dict:
    """Buy-and-hold return of a daily close series (dicts with `timestamp`,
    `close`, already restricted to the window and sorted ascending): enter at
    the first close, mark at the last. Annualized over the series' own span so a
    stale cache never inflates the figure. None-filled when fewer than 2 points."""
    out = {"cum_pct": None, "ann_pct": None, "days": None,
           "first_close": None, "last_close": None, "first_ts": None, "last_ts": None}
    pts = [(_parse_iso(c.get("timestamp")), c.get("close")) for c in closes]
    pts = [(t, float(c)) for t, c in pts if t is not None and c]
    if len(pts) < 2 or pts[0][1] <= 0:
        return out
    (t0, c0), (t1, c1) = pts[0], pts[-1]
    days = (t1 - t0).total_seconds() / 86400.0
    cum = c1 / c0 - 1.0
    ann = annualize(cum, days, min_days)
    out.update({
        "cum_pct": cum * 100.0, "ann_pct": ann * 100.0 if ann is not None else None,
        "days": days, "first_close": c0, "last_close": c1, "first_ts": t0, "last_ts": t1,
    })
    return out


def trade_matched_benchmark(trades: list[dict], closes: list[dict]) -> dict:
    """Trade-matched index counterfactual: for every closed trade, put the same
    notional (`entry_price × quantity`) into the benchmark at the close of the
    entry day and take it out at the close of the exit day. Answers "the same
    money, deployed on the same days, in the index instead — who won?", which
    buy-and-hold on the full capital conflates with idle-cash and timing.

    `closes` are daily candles (`timestamp`, `close`) sorted ascending; a leg
    uses the last close ON OR BEFORE its date. Trades missing a price/qty/time
    or without a close on either side are skipped (counted in `skipped`). Costs
    are not applied to the index side; compare against OUR GROSS for
    like-for-like (net is the number you bank, shown separately by the UI).

    Returns {pnl, notional, pct, our_gross, our_gross_pct, n_trades, skipped}
    — pct fields are on the summed notional; None when nothing matched."""
    out = {"pnl": None, "notional": 0.0, "pct": None, "our_gross": 0.0,
           "our_gross_pct": None, "n_trades": 0, "skipped": 0}
    series = sorted(
        ((t.date(), float(c)) for t, c in
         ((_parse_iso(r.get("timestamp")), r.get("close")) for r in closes)
         if t is not None and c),
        key=lambda x: x[0],
    )
    if not series:
        out["skipped"] = len(trades)
        return out
    dates = [d for d, _ in series]

    def _close_on_or_before(day):
        i = bisect_right(dates, day) - 1
        return series[i][1] if i >= 0 else None

    pnl = notional = ours = 0.0
    n = skipped = 0
    for t in trades:
        ed, xd = _parse_iso(t.get("entry_time")), _parse_iso(t.get("exit_time"))
        ep, q = t.get("entry_price"), t.get("quantity")
        if not (ed and xd and ep and q):
            skipped += 1
            continue
        c0, c1 = _close_on_or_before(ed.date()), _close_on_or_before(xd.date())
        if not c0 or not c1:
            skipped += 1
            continue
        amt = float(ep) * float(q)
        pnl += amt * (c1 / c0 - 1.0)
        notional += amt
        ours += float(t.get("gross_pnl") or 0.0)
        n += 1
    out.update({"n_trades": n, "skipped": skipped, "notional": notional, "our_gross": ours})
    if n and notional > 0:
        out["pnl"] = pnl
        out["pct"] = pnl / notional * 100.0
        out["our_gross_pct"] = ours / notional * 100.0
    return out


def benchmark_equity(closes: list[dict], dates: list, capital: float) -> list[float | None]:
    """₹ P&L of a buy-and-hold of `capital` in the benchmark, marked at each of
    `dates` (e.g. our trades' exit times), entered at the FIRST close of
    `closes`. Lets the index sit on the same trade-indexed x-axis as our
    equity curve: at the moment of each of our exits, where would full-capital
    Nifty B&H be. `closes` sorted ascending daily candles; a date with no close
    on or before it yields None. Empty list when there is nothing to anchor."""
    series = sorted(
        ((t.date(), float(c)) for t, c in
         ((_parse_iso(r.get("timestamp")), r.get("close")) for r in closes)
         if t is not None and c),
        key=lambda x: x[0],
    )
    if not series or not capital:
        return []
    days = [d for d, _ in series]
    c0 = series[0][1]
    out: list[float | None] = []
    for d in dates:
        dd = _parse_iso(d) if not hasattr(d, "date") else d
        if dd is None:
            out.append(None)
            continue
        i = bisect_right(days, dd.date()) - 1
        out.append(capital * (series[i][1] / c0 - 1.0) if i >= 0 else None)
    return out
