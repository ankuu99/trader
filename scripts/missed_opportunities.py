"""Missed-opportunity analysis against the live EC2 bot.

Detects confirmed swing dips (local minima) and peaks (local maxima) on each
watchlist stock's own strategy timeframe from the remote candle history, then
cross-references actual live fills/signals/model scores to classify every
actionable dip as CAPTURED or MISSED (and why), and every peak that occurred
while holding as an exit that was TAKEN or MISSED.

Read-only with respect to the remote box: the single ssh call opens the DB with
?mode=ro and only SELECTs. Results are cached locally so re-analysis with
different parameters does not re-hit EC2.

Usage:
  python scripts/missed_opportunities.py                       # fetch + analyse + plot
  python scripts/missed_opportunities.py --cached              # reuse local snapshot
  python scripts/missed_opportunities.py --days 60 --min-move 2.0
  python scripts/missed_opportunities.py --symbols NSE:CUPID NSE:GESHIP
"""

import argparse
import base64
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = ROOT / "data" / "missed_opp_snapshot.json"

# ---------------------------------------------------------------- remote fetch

REMOTE_CODE = """
import json, sqlite3, sys
cutoff = {cutoff!r}
cfg_text = open('/opt/trader/config/config.yaml').read()
import yaml
cfg = yaml.safe_load(cfg_text)
symbols = [s for s in cfg.get('watchlist', [])]
c = sqlite3.connect('file:/opt/trader/data/market.db?mode=ro', uri=True)
ph = ','.join('?' * len(symbols))
out = {{'fetched_at': None, 'config': cfg_text, 'symbols': symbols}}
out['candles'] = list(c.execute(
    f"SELECT instrument, timestamp, open, high, low, close FROM candles "
    f"WHERE timeframe='15minute' AND instrument IN ({{ph}}) AND timestamp >= ? "
    f"ORDER BY instrument, timestamp", symbols + [cutoff]))
out['scores'] = list(c.execute(
    f"SELECT instrument, timestamp, p_min, p_max FROM model_scores "
    f"WHERE instrument IN ({{ph}}) ORDER BY instrument, timestamp", symbols))
out['orders'] = list(c.execute(
    "SELECT instrument, direction, quantity, price, status, placed_at "
    "FROM orders ORDER BY placed_at"))
out['signals'] = list(c.execute(
    "SELECT instrument, logged_at, direction, signal_type, price_hint, accepted, "
    "reject_reason, exit_reason FROM signals ORDER BY logged_at"))
json.dump(out, sys.stdout)
"""


def fetch_snapshot(cutoff: str, cache: Path) -> dict:
    code = REMOTE_CODE.format(cutoff=cutoff)
    b64 = base64.b64encode(code.encode()).decode()
    cmd = (
        "sudo -u trader /opt/trader/.venv/bin/python -c "
        f"\"import base64;exec(base64.b64decode('{b64}').decode())\""
    )
    print(f"Fetching snapshot from EC2 (candles since {cutoff}) ...", file=sys.stderr)
    res = subprocess.run(["ssh", "trader", cmd], capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise SystemExit(f"remote fetch failed:\n{res.stderr[-2000:]}")
    snap = json.loads(res.stdout)
    snap["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(snap))
    print(f"Snapshot cached to {cache}", file=sys.stderr)
    return snap


# ---------------------------------------------------------------- config merge

TF_SENSITIVE_DEFAULTS = {"timeframe": "15minute"}


def stock_params(cfg: dict, sym: str) -> dict:
    lr = cfg.get("strategies", {}).get("lr_extrema", {})
    merged = {
        "timeframe": cfg.get("candle_timeframe", "15minute"),
        "threshold": lr.get("threshold", 0.9),
        "veto_threshold": lr.get("veto_threshold", 1.0),
        "extrema_order": lr.get("extrema_order", 10),
    }
    override = (cfg.get("per_stock_params") or {}).get(sym, {}).get("lr_extrema", {}) or {}
    for k in merged:
        if k in override and override[k] is not None:
            merged[k] = override[k]
    return merged


# ------------------------------------------------------------ bar aggregation

def aggregate(candles: list, timeframe: str) -> list:
    """15m rows [ts, o, h, l, c] -> strategy-TF bars with frozen boundaries.

    day  = 09:15-15:15 (the 15:15 candle is the dropped tail)
    4hour = 09:15-13:15 + 13:15-15:15
    Decision timestamp = last member candle's timestamp (completion-based emission).
    """
    if timeframe in ("15minute", "5minute"):
        return [{"ts": r[1], "high": r[3], "low": r[4], "close": r[5]} for r in candles]
    groups = {}
    order = []
    for r in candles:
        ts = r[1]
        date, time = ts[:10], ts[11:16]
        if time >= "15:15":
            continue
        if timeframe == "day":
            key = date
        elif timeframe == "4hour":
            key = (date, "am" if time < "13:15" else "pm")
        else:
            raise ValueError(f"unsupported timeframe {timeframe}")
        if key not in groups:
            groups[key] = {"ts": ts, "high": r[3], "low": r[4], "close": r[5]}
            order.append(key)
        else:
            g = groups[key]
            g["ts"] = ts
            g["high"] = max(g["high"], r[3])
            g["low"] = min(g["low"], r[4])
            g["close"] = r[5]
    return [groups[k] for k in order]


def find_extrema(closes: list, order: int):
    """Strict local minima/maxima over +/-order bars (mirrors the strategy's labeler)."""
    mins, maxs = [], []
    n = len(closes)
    for i in range(order, n - order):
        window = closes[i - order : i] + closes[i + 1 : i + order + 1]
        if all(closes[i] < w for w in window):
            mins.append(i)
        elif all(closes[i] > w for w in window):
            maxs.append(i)
    return mins, maxs


# ------------------------------------------------------------ order intervals

def position_state(orders: list):
    """Per instrument: chronological COMPLETE fills -> holding intervals + fills."""
    buys, sells, intervals = defaultdict(list), defaultdict(list), defaultdict(list)
    qty, open_since = defaultdict(int), {}
    for inst, direction, q, price, status, placed_at in orders:
        if status != "COMPLETE":
            continue
        if direction == "BUY":
            buys[inst].append((placed_at, price, q))
            if qty[inst] == 0:
                open_since[inst] = placed_at
            qty[inst] += q
        else:
            sells[inst].append((placed_at, price, q))
            qty[inst] -= q
            if qty[inst] <= 0 and inst in open_since:
                intervals[inst].append((open_since.pop(inst), placed_at))
                qty[inst] = 0
    for inst, start in open_since.items():
        intervals[inst].append((start, None))
    return buys, sells, intervals


def holding_at(intervals: list, ts: str) -> bool:
    return any(a <= ts and (b is None or ts <= b) for a, b in intervals)


# ---------------------------------------------------------------- analysis

BUCKET_OF = {  # fine-grained reason -> chart bucket
    "below_threshold": "below_threshold",
    "in_position": "in_position",
    "blocked": "blocked",
    "vetoed": "other",
    "no_score": "other",
}
BUCKET_LABELS = {
    "captured": "Captured",
    "below_threshold": "Model below threshold",
    "in_position": "Already in position",
    "blocked": "Rejected / gate anomaly",
    "other": "No score recorded / vetoed",
}


def nearest_score(scores: list, ts: str):
    """Latest score at or before ts, if within ~1 calendar day."""
    best = None
    for s_ts, p_min, p_max in scores:
        if s_ts <= ts:
            best = (s_ts, p_min, p_max)
        else:
            break
    if best is None:
        return None
    gap = datetime.fromisoformat(ts) - datetime.fromisoformat(best[0])
    return best if gap <= timedelta(days=1) else None


def analyse_symbol(sym, bars, params, scores, buys, sells, intervals, signals,
                   min_move, tol_bars, start_ts):
    closes = [b["close"] for b in bars]
    mins, maxs = find_extrema(closes, int(params["extrema_order"]))
    thr, veto = float(params["threshold"]), float(params["veto_threshold"])
    dips, peaks = [], []

    def bar_ts(i):
        return bars[i]["ts"]

    ext = sorted([(i, "min") for i in mins] + [(i, "max") for i in maxs])

    for pos, (i, kind) in enumerate(ext):
        nxt = next(((j, k) for j, k in ext[pos + 1 :] if k != kind), None)
        if bar_ts(i) < start_ts:
            continue
        if kind == "min":
            if nxt is None:
                continue
            j = nxt[0]
            move = (closes[j] - closes[i]) / closes[i] * 100
            if move < min_move:
                continue
            lo = bar_ts(max(0, i - tol_bars))
            hi = bar_ts(j)
            fill = next((b for b in buys if lo <= b[0] <= hi), None)
            if fill:
                outcome, reason = "captured", None
            elif holding_at(intervals, bar_ts(i)):
                outcome, reason = "missed", "in_position"
            else:
                rej = next(
                    (s for s in signals
                     if s[3] == "ENTRY" and lo <= s[1] <= hi and not s[5]),
                    None,
                )
                sc = nearest_score(scores, bar_ts(i))
                if rej:
                    reason = ("in_position" if rej[6] == "already_in_position"
                              else "blocked")
                elif sc is None:
                    reason = "no_score"  # score history trimmed / model untrained
                elif sc[1] < thr:
                    reason = "below_threshold"
                elif sc[2] >= veto:
                    reason = "vetoed"
                else:
                    reason = "blocked"  # gates passed on record, no order — window/pending
                outcome = "missed"
            dips.append({
                "ts": bar_ts(i), "price": closes[i], "bounce_pct": round(move, 2),
                "peak_ts": bar_ts(j), "outcome": outcome, "reason": reason,
                "p_min": (nearest_score(scores, bar_ts(i)) or (None, None, None))[1],
            })
        else:
            if nxt is None:
                continue
            j = nxt[0]
            drop = (closes[i] - closes[j]) / closes[i] * 100
            if drop < min_move:
                continue
            if not holding_at(intervals, bar_ts(i)):
                peaks.append({"ts": bar_ts(i), "price": closes[i],
                              "drop_pct": round(drop, 2), "outcome": "flat"})
                continue
            lo = bar_ts(max(0, i - tol_bars))
            hi = bar_ts(j)
            sold = next((s for s in sells if lo <= s[0] <= hi), None)
            if sold:
                give = (closes[i] - sold[1]) / closes[i] * 100
                peaks.append({"ts": bar_ts(i), "price": closes[i],
                              "drop_pct": round(drop, 2), "outcome": "captured",
                              "giveback_pct": round(max(give, 0.0), 2)})
            else:
                peaks.append({"ts": bar_ts(i), "price": closes[i],
                              "drop_pct": round(drop, 2), "outcome": "missed",
                              "giveback_pct": round(drop, 2)})
    return dips, peaks


# ---------------------------------------------------------------- plotting

PALETTE = {  # dataviz categorical slots 1-5, fixed order (validated)
    "captured": "#2a78d6",
    "below_threshold": "#eb6834",
    "in_position": "#1baf7a",
    "blocked": "#eda100",
    "other": "#e87ba4",
}
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


def plot(results, meta, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    syms = sorted(
        results,
        key=lambda s: sum(1 for d in results[s]["dips"] if d["outcome"] == "missed"),
    )
    labels = [s.replace("NSE:", "") for s in syms]
    n = len(syms)
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(13, max(4.5, 0.42 * n + 2.2)), dpi=150,
        gridspec_kw={"width_ratios": [3, 2]},
    )
    fig.patch.set_facecolor(SURFACE)

    order = ["captured", "below_threshold", "in_position", "blocked", "other"]
    left = [0.0] * n
    for key in order:
        vals = []
        for s in syms:
            dips = results[s]["dips"]
            if key == "captured":
                vals.append(sum(1 for d in dips if d["outcome"] == "captured"))
            else:
                vals.append(sum(1 for d in dips
                                if d["outcome"] == "missed"
                                and BUCKET_OF.get(d["reason"]) == key))
        ax1.barh(range(n), vals, left=left, height=0.62, color=PALETTE[key],
                 edgecolor=SURFACE, linewidth=2, label=BUCKET_LABELS[key])
        for y, (v, l) in enumerate(zip(vals, left)):
            if v >= 1:
                ax1.text(l + v / 2, y, str(int(v)), ha="center", va="center",
                         fontsize=7.5, color=SURFACE if key in ("captured", "below_threshold") else INK,
                         fontweight="bold")
        left = [l + v for l, v in zip(left, vals)]
    ax1.set_title(f"Dips ≥ {meta['min_move']}% bounce — captured vs missed (why)",
                  fontsize=11, color=INK, loc="left", pad=12)

    for ax in (ax1, ax2):
        ax.set_facecolor(SURFACE)
        ax.set_yticks(range(n))
        ax.set_yticklabels(labels, fontsize=8.5, color=INK2)
        ax.tick_params(axis="x", labelsize=8, colors=MUTED)
        ax.tick_params(axis="y", length=0)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color("#c3c2b7")
        ax.xaxis.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        ax.margins(y=0.01)

    pk_order = [("captured", "Exit taken near peak"), ("missed", "Peak missed while holding")]
    pk_colors = {"captured": "#2a78d6", "missed": "#4a3aa7"}
    left = [0.0] * n
    for key, lab in pk_order:
        vals = [sum(1 for p in results[s]["peaks"] if p["outcome"] == key) for s in syms]
        ax2.barh(range(n), vals, left=left, height=0.62, color=pk_colors[key],
                 edgecolor=SURFACE, linewidth=2, label=lab)
        for y, (v, l) in enumerate(zip(vals, left)):
            if v >= 1:
                ax2.text(l + v / 2, y, str(int(v)), ha="center", va="center",
                         fontsize=7.5, color=SURFACE, fontweight="bold")
        left = [l + v for l, v in zip(left, vals)]
    ax2.set_title(f"Peaks ≥ {meta['min_move']}% drop while holding",
                  fontsize=11, color=INK, loc="left", pad=12)
    ax2.set_yticklabels([""] * n)

    t = meta["totals"]
    fig.suptitle("Missed opportunities — live bot vs actual swings", fontsize=14,
                 color=INK, x=0.02, ha="left", fontweight="bold")
    fig.text(0.02, 0.925,
             f"{meta['window'][0][:10]} → {meta['window'][1][:10]}  ·  "
             f"{t['dips']} actionable dips: {t['dips_captured']} captured, "
             f"{t['dips_missed']} missed (avg bounce {t['avg_missed_bounce']:.1f}%)  ·  "
             f"{t['peaks_holding']} peaks while holding: {t['peaks_missed']} missed  ·  "
             f"est. foregone ≈ ₹{t['est_foregone']:,.0f} at ₹{meta['notional']:,.0f}/dip",
             fontsize=9, color=INK2)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    fig.legend(h1 + [h2[1]], l1 + [l2[1]], loc="lower center", ncol=3, frameon=False,
               fontsize=8.5, labelcolor=INK2, bbox_to_anchor=(0.5, 0.0))
    fig.tight_layout(rect=(0, 0.06, 1, 0.9))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, facecolor=SURFACE, bbox_inches="tight")
    print(f"Chart saved to {out_path}", file=sys.stderr)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=90, help="analysis window (days back)")
    ap.add_argument("--min-move", type=float, default=3.0,
                    help="min %% bounce/drop for a dip/peak to count as actionable")
    ap.add_argument("--tolerance-bars", type=int, default=3,
                    help="strategy-TF bars before an extremum a fill still counts")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--cached", action="store_true", help="reuse local snapshot, no ssh")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    ap.add_argument("--output", type=Path, default=None, help="chart PNG path")
    ap.add_argument("--json", type=Path, default=None, help="write full details JSON here")
    args = ap.parse_args()

    fetch_cutoff = (datetime.now() - timedelta(days=args.days + 40)).strftime("%Y-%m-%dT00:00:00")
    if args.cached and args.cache.exists():
        snap = json.loads(args.cache.read_text())
        print(f"Using cached snapshot from {snap.get('fetched_at')}", file=sys.stderr)
    else:
        snap = fetch_snapshot(fetch_cutoff, args.cache)

    cfg = yaml.safe_load(snap["config"])
    start_ts = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%dT00:00:00")
    # never judge candles from before the live order history begins
    first_order = min((o[5] for o in snap["orders"]), default=start_ts)
    start_ts = max(start_ts, first_order[:19])

    symbols = args.symbols or snap["symbols"]
    candles_by = defaultdict(list)
    for r in snap["candles"]:
        candles_by[r[0]].append(r)
    scores_by = defaultdict(list)
    for inst, ts, p_min, p_max in snap["scores"]:
        scores_by[inst].append((ts, p_min, p_max))
    buys, sells, intervals = position_state(snap["orders"])
    signals_by = defaultdict(list)
    for s in snap["signals"]:
        signals_by[s[0]].append(s)

    notional = (cfg.get("capital", {}).get("total", 0)
                * cfg.get("risk", {}).get("max_capital_per_stock_pct", 10) / 100)

    results, skipped = {}, []
    for sym in symbols:
        if not candles_by.get(sym):
            skipped.append(sym)
            continue
        params = stock_params(cfg, sym)
        bars = aggregate(candles_by[sym], str(params["timeframe"]))
        dips, peaks = analyse_symbol(
            sym, bars, params, scores_by.get(sym, []),
            buys.get(sym, []), sells.get(sym, []), intervals.get(sym, []),
            signals_by.get(sym, []), args.min_move, args.tolerance_bars, start_ts,
        )
        results[sym] = {"timeframe": params["timeframe"], "threshold": params["threshold"],
                        "dips": dips, "peaks": peaks}

    all_dips = [d for r in results.values() for d in r["dips"]]
    missed = [d for d in all_dips if d["outcome"] == "missed"]
    peaks_holding = [p for r in results.values() for p in r["peaks"] if p["outcome"] != "flat"]
    peaks_missed = [p for p in peaks_holding if p["outcome"] == "missed"]
    totals = {
        "dips": len(all_dips),
        "dips_captured": len(all_dips) - len(missed),
        "dips_missed": len(missed),
        "avg_missed_bounce": (sum(d["bounce_pct"] for d in missed) / len(missed)) if missed else 0.0,
        "miss_reasons": dict(Counter(d["reason"] for d in missed)),
        "peaks_holding": len(peaks_holding),
        "peaks_missed": len(peaks_missed),
        "est_foregone": sum(d["bounce_pct"] / 100 * notional for d in missed),
    }
    end_ts = max((r[1] for r in snap["candles"]), default=start_ts)
    meta = {"window": (start_ts, end_ts), "min_move": args.min_move,
            "notional": notional, "totals": totals}

    out_png = args.output or (ROOT / "reviews" /
                              f"missed_opportunities_{datetime.now():%Y%m%d}.png")
    plot(results, meta, out_png)

    summary = {"meta": meta, "skipped": skipped, "per_symbol": {
        s: {
            "timeframe": r["timeframe"],
            "dips": len(r["dips"]),
            "dips_captured": sum(1 for d in r["dips"] if d["outcome"] == "captured"),
            "dips_missed": sum(1 for d in r["dips"] if d["outcome"] == "missed"),
            "miss_reasons": dict(Counter(d["reason"] for d in r["dips"] if d["outcome"] == "missed")),
            "avg_missed_bounce_pct": round(
                sum(d["bounce_pct"] for d in r["dips"] if d["outcome"] == "missed")
                / max(1, sum(1 for d in r["dips"] if d["outcome"] == "missed")), 2),
            "peaks_holding": sum(1 for p in r["peaks"] if p["outcome"] != "flat"),
            "peaks_missed": sum(1 for p in r["peaks"] if p["outcome"] == "missed"),
        } for s, r in results.items()
    }, "chart": str(out_png)}
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "detail": results}, indent=1))
        print(f"Details written to {args.json}", file=sys.stderr)
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
