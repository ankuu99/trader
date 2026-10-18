"""Markdown run report from score_run's summary + curves.parquet."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.model_lab import paths

REPORT_DIR = paths.REPO_ROOT / "reviews" / "model_lab" / "runs"
LEDGER_PATH = paths.REPO_ROOT / "reviews" / "model_lab" / "LEDGER.md"


def arms_tried(ledger: Path | None = None) -> int | None:
    """Data rows in the '## Arms' table of the ledger (None when the ledger is missing)."""
    p = ledger or LEDGER_PATH
    if not p.exists():
        return None
    n, in_arms, hdr = 0, False, 0
    for line in p.read_text().splitlines():
        if line.startswith("## "):
            in_arms = line.strip() == "## Arms"
            hdr = 0
            continue
        if in_arms and line.startswith("|"):
            hdr += 1
            if hdr > 2:
                n += 1
    return n


def _f(x, d=3):
    return "—" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"


def _table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def _ap_table(ap_t: dict, models: list[str], scope: str) -> str:
    keys = sorted({k for m in models for k in ap_t[m][scope]})
    return _table([scope] + models, [[k] + [_f(ap_t[m][scope].get(k), 4) for m in models] for k in keys])


def write_report(run_id: str, summary: dict, curves: pd.DataFrame | None = None) -> Path:
    if curves is None:
        curves = summary.get("_curves")
    if curves is None:
        curves = pd.read_parquet(paths.RUNS_DIR / run_id / "curves.parquet")
    s = json.loads(json.dumps({k: v for k, v in summary.items() if k != "_curves"}, default=str))
    models = s["models"]
    meta = s["meta"]
    arms = arms_tried()
    L: list[str] = [f"# Model Lab run {run_id}\n"]
    L.append(f"- tf `{s['tf']}` · scheme `{meta.get('scheme')}` · target `{meta.get('target')}` · "
             f"model `{meta.get('model')}` · universe top-N `{meta.get('universe_top_n')}`")
    L.append(f"- folds {len(s['folds'])} · symbols scored {len(s['symbols_scored'])} · rows {s['rows_total']} "
             f"(evaluated {s['rows_evaluated']}) · side `{s['side']}` · pick window {s['tol']} bars · match tolerance per truth {s.get('truth_tol', {})}")
    L.append(f"- **Arms tried so far: {arms if arms is not None else 'unknown (ledger missing)'}** "
             f"(LEDGER.md `## Arms` rows)")
    L.append("- reference coverage (share of the run's rows where the score is non-NaN): "
             + ", ".join(f"`{m}` {_f(v, 3)}" for m, v in s["coverage"].items()))
    L.append("")
    mag = s.get("magnitude")
    if mag:
        L.append(f"## Magnitude verdict: **{mag['overall']}** (headline; run target `{meta.get('target')}`)\n")
        L.append("PASS = WIN vs production P(min)/P(max) AND WIN vs RSI; WIN = signed Spearman of the model score with "
                 "the realised target beats the reference's |Spearman| in >= 2/3 of folds AND >= 2/3 of calendar years "
                 f"(groups with >= 200 evaluated rows; {mag['n_folds']} folds, {mag['n_years']} years).\n")
        L.append(_table(["ref", "fold win share", "folds", "year win share", "years", "verdict"],
                        [[rn, _f(v["fold_win_share"], 2), v["n_folds"], _f(v["year_win_share"], 2), v["n_years"],
                          "WIN" if v["win"] else "—"] for rn, v in mag["verdicts"].items()]))
        L.append("Pooled Spearman with the realised target: "
                 + ", ".join(f"`{m}` {_f(v, 3)}" for m, v in mag["pooled_rho"].items()) + "\n")
        dec = s.get("deciles") or {}
        if dec:
            L.append(f"## Deciles — realised `{dec.get('target')}` by decile of score (1 = lowest)\n")
            names = [k for k in dec if k != "target"]
            rows = []
            for i in range(10):
                row = [i + 1]
                for k in names:
                    r = dec[k]["rows"][i] if len(dec[k]["rows"]) > i else None
                    row.append(f"{_f(r['mean'], 4)} / {_f(r['median'], 4)}" if r else "—")
                rows.append(row)
            L.append("cells: mean / median\n")
            L.append(_table(["decile"] + names, rows))
            L.append("top-minus-bottom decile spread (mean): "
                     + ", ".join(f"`{k}` {_f(dec[k]['spread'], 4)}" for k in names) + "\n")
        L.append(f"## Detection verdict: **{s.get('overall_detection')}**\n")
    else:
        L.append(f"## Verdict: **{s['overall']}** (primary truth `{s['primary_truth']}`; all detection truths: "
                 f"{s['overall_all_truths']})\n")
    L.append("PASS = WIN vs production P(min)/P(max) AND WIN vs coin; WIN = event-AP beaten in >= 2/3 of folds AND "
             ">= 2/3 of years (folds/years with >= 10 pivots).\n")
    rows = []
    for tc, vs in s["verdicts"].items():
        for rn, v in vs.items():
            rows.append([tc, rn, _f(v["fold_win_share"], 2), v["n_folds"], _f(v["year_win_share"], 2), v["n_years"],
                         "WIN" if v["win"] else "—"])
    L.append(_table(["truth", "ref", "fold win share", "folds", "year win share", "years", "verdict"], rows))

    for tc in s["truths"]:
        L.append(f"## Curves — `{tc}` (pooled, all folds)\n")
        sub = curves[(curves.scope == "all") & (curves.truth == tc)]
        rows = []
        for r in s["rates"]:
            row = [f"{r:g}"]
            for m in models:
                x = sub[(sub.model == m) & (np.isclose(sub.rate, r))]
                if len(x):
                    x = x.iloc[0]
                    row.append(f"{_f(x.precision)} / {_f(x.recall)} / {_f(x.picks_per_stock_year, 1)}")
                else:
                    row.append("—")
            rows.append(row)
        L.append("cells: precision / recall / picks per stock-year\n")
        L.append(_table(["rate"] + models, rows))
        L.append(f"event AP (all): " + ", ".join(f"`{m}` {_f(s['ap'][tc][m]['all'], 4)}" for m in models) + "\n")
        for scope, title in (("year", "per year"), ("fold", "per fold"), ("vix", "VIX regime"), ("nifty", "Nifty trend")):
            L.append(f"### Event AP {title} — `{tc}`\n")
            L.append(_ap_table(s["ap"][tc], models, scope))

    if s["t2"]:
        L.append("## Turn classification (T2): ROC-AUC / AP per fold\n")
        for c, per_m in s["t2"].items():
            folds = sorted({f for m in per_m.values() for f in m}, key=int)
            L.append(f"`{c}`\n")
            L.append(_table(["fold"] + models, [[f] + [
                (f"{_f(per_m[m][f]['auc'])} / {_f(per_m[m][f]['ap'], 4)}" if f in per_m.get(m, {}) else "—")
                for m in models] for f in folds]))
    if s["spearman"]:
        L.append("## Spearman rank correlation of score with realised move (per fold)\n")
        for c, per_m in s["spearman"].items():
            folds = sorted({f for m in per_m.values() for f in m}, key=int)
            L.append(f"`{c}`\n")
            L.append(_table(["fold"] + models, [[f] + [_f(per_m[m].get(f)) for m in models] for f in folds]))
    if s["preds"]:
        L.append("## Multi-output predictions\n")
        for c, per_f in s["preds"].items():
            L.append(f"`{c}`: " + ", ".join(f"fold {f}: " + ", ".join(f"{k} {_f(v)}" for k, v in d.items())
                                            for f, d in per_f.items()) + "\n")

    L.append(f"## After-pick profile (H={s['hold_H']}) — informational, not a pass condition\n")
    for rate, per_m in s["after_pick_informational"].items():
        L.append(f"rate {rate}\n")
        L.append(_table(["model", "picks", "mfe mean", "maepre mean", "ttm mean", "ret mean", "net ret mean (−0.22%)",
                         "net ret median", "hit x5/y3", "T5 NaN excl."],
                        [[m, v["picks"], _f(v["mfe_mean"] and v["mfe_mean"] * 100, 2) + "%",
                          _f(v["maepre_mean"] and v["maepre_mean"] * 100, 2) + "%", _f(v["ttm_mean"], 1),
                          _f(v["ret_mean"] and v["ret_mean"] * 100, 2) + "%",
                          _f(v["net_ret_mean"] and v["net_ret_mean"] * 100, 2) + "%",
                          _f(v["net_ret_median"] and v["net_ret_median"] * 100, 2) + "%",
                          _f(v["hit_x5_y3_rate"], 3), v["t5_nan_excluded"]] for m, v in per_m.items()]))
    ay = s.get("afterpick_by_year")
    if ay:
        L.append(f"## After-pick by year (informational — not a pass condition)\n")
        L.append(f"Picks at firing rate {ay['rate']}, net return t5_ret_H{ay['hold_H']} − 0.22% cost.\n")
        names = list(next(iter(ay["by_year"].values())).keys()) if ay["by_year"] else []
        L.append(_table(["year"] + [f"{m} (n / mean / median)" for m in names],
                        [[y] + [f"{v[m]['picks']} / {_f(v[m]['mean'] and v[m]['mean'] * 100, 2)}% / "
                                f"{_f(v[m]['median'] and v[m]['median'] * 100, 2)}%" for m in names]
                         for y, v in ay["by_year"].items()]))
        if ay.get("years_compared") is not None:
            L.append(f"Years model mean > prod: {ay['years_model_mean_gt_prod']}/{ay['years_compared']}; "
                     f"median > prod: {ay['years_model_median_gt_prod']}/{ay['years_compared']}.\n")
        for key, title in (("all", "pooled"), ("ex_qa", "pooled excluding QA-flagged symbols"),
                           ("ex_2020", "pooled excluding 2020")):
            if key in ay["pooled"]:
                L.append(f"{title}: " + "; ".join(
                    f"`{m}` n={v['picks']} mean {_f(v['mean'] and v['mean'] * 100, 2)}% "
                    f"median {_f(v['median'] and v['median'] * 100, 2)}%" for m, v in ay["pooled"][key].items()) + "\n")
        if not ay.get("qa_file_found"):
            L.append("(ex-QA line skipped: QA file not found)\n")
    L.append("---\nScored on the model's own terms (docs/03 §6): hindsight truth across all firing rates; the strategy "
             "does not judge the model.\n")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"{run_id}.md"
    out.write_text("\n".join(L))
    return out
