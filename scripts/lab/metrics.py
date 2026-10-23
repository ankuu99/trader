"""
Detection metrics for the extrema lab.

Two separately-reported stages:
  1. label quality  — do the labeler's training labels match hand truth?
     (bounds what any model trained on them can achieve)
  2. model quality  — do the walk-forward score crossings match hand truth?

Matching is event-based: a detection (rising-edge threshold crossing) counts as a
hit if a truth event lies within ±tol_bars. A coverage mask (hand-reviewed
ranges) restricts both sides so partial labeling yields valid precision AND
recall; the mask is shrunk by tol_bars at each range edge so a prediction near a
coverage boundary isn't unfairly scored against truth that may exist just
outside the reviewed range.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class MatchResult:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    lags: list[int] = field(default_factory=list)      # per-TP, bars late (+) / early (-)
    matched: list[tuple[int, int]] = field(default_factory=list)  # (truth_idx, pred_idx)
    fp_idx: list[int] = field(default_factory=list)
    fn_idx: list[int] = field(default_factory=list)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else float("nan")

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else float("nan")

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if np.isnan(p) or np.isnan(r) or (p + r) == 0:
            return float("nan")
        return 2 * p * r / (p + r)

    @property
    def median_lag(self) -> float:
        return float(np.median(self.lags)) if self.lags else float("nan")


def extract_crossings(scores: pd.DataFrame, col: str, thr: float) -> list[int]:
    """Positional indices of rising-edge crossings: value >= thr where the
    previous valid value was < thr (or this is the first valid value)."""
    v = scores[col].to_numpy(dtype=float)
    above = v >= thr
    prev = np.roll(above, 1)
    prev[0] = False
    # a NaN previous bar counts as 'below' (np.nan >= thr is False already)
    return [int(i) for i in np.nonzero(above & ~prev)[0]]


def shrink_mask(mask: np.ndarray, tol_bars: int) -> np.ndarray:
    """Erode each covered range by tol_bars at both edges (boundary fairness)."""
    if tol_bars <= 0:
        return mask.copy()
    m = mask.astype(bool)
    out = m.copy()
    for shift in range(1, tol_bars + 1):
        out &= np.roll(m, shift) & np.roll(m, -shift)
    # roll wraps around; kill the wrapped edges
    out[:tol_bars] &= m[:tol_bars]
    out[-tol_bars:] &= m[-tol_bars:]
    # a range shorter than 2*tol vanishes entirely — acceptable: it can't be
    # scored fairly anyway
    return out


def match_events(pred_idx: list[int], truth_idx: list[int], tol_bars: int,
                 mask: np.ndarray | None = None) -> MatchResult:
    """Greedy chronological matching: walk truths in order, each grabs the
    nearest unmatched prediction within ±tol_bars. Unmatched predictions are FP,
    unmatched truths FN.

    mask: bool per bar (True = covered). Truth events are filtered by the raw
    mask; predictions by the tol-shrunk mask (see module docstring).
    """
    if mask is not None:
        pmask = shrink_mask(np.asarray(mask, dtype=bool), tol_bars)
        tmask = np.asarray(mask, dtype=bool)
        pred_idx = [i for i in pred_idx if pmask[i]]
        truth_idx = [i for i in truth_idx if tmask[i]]

    preds = sorted(pred_idx)
    used = [False] * len(preds)
    res = MatchResult()

    for t in sorted(truth_idx):
        best_j, best_d = -1, tol_bars + 1
        for j, p in enumerate(preds):
            if used[j]:
                continue
            if p < t - tol_bars:
                continue
            if p > t + tol_bars:
                break
            d = abs(p - t)
            if d < best_d:
                best_j, best_d = j, d
        if best_j >= 0:
            used[best_j] = True
            res.tp += 1
            res.matched.append((t, preds[best_j]))
            res.lags.append(preds[best_j] - t)
        else:
            res.fn += 1
            res.fn_idx.append(t)

    res.fp = used.count(False)
    res.fp_idx = [p for j, p in enumerate(preds) if not used[j]]
    return res


# ---------------------------------------------------------------------------
# Higher-level evaluation
# ---------------------------------------------------------------------------

def transition_indices(indices: list[int], classes: list[int]) -> tuple[list[int], list[int]]:
    """Event indices for DENSE directional labelers (labeler.dense == True).

    A dense labeler classifies every bar Up/Down, so its raw class-0 indices are
    the whole of every uptrend — meaningless as events. The events are the label
    *flips*: 1→0 marks a bottom (dip), 0→1 marks a top (peak). Returns
    (dip_indices, peak_indices). Class-2 (neutral) samples are ignored."""
    pairs = sorted((i, c) for i, c in zip(indices, classes) if c in (0, 1))
    dips: list[int] = []
    peaks: list[int] = []
    prev: int | None = None
    for i, c in pairs:
        if prev is not None and c != prev:
            (dips if c == 0 else peaks).append(i)
        prev = c
    return dips, peaks


def truth_positions(truth: pd.DataFrame, index: pd.Series) -> dict[str, list[int]]:
    """Map hand labels (timestamp, kind) to positional indices in the candle index.
    Labels whose timestamp isn't in the index are dropped."""
    lookup = {ts: i for i, ts in enumerate(pd.to_datetime(index))}
    out: dict[str, list[int]] = {"dip": [], "peak": []}
    for _, row in truth.iterrows():
        i = lookup.get(pd.Timestamp(row["timestamp"]))
        if i is not None:
            out[row["kind"]].append(i)
    return out


def evaluate_mechanism(scores: pd.DataFrame, truth: pd.DataFrame,
                       mask: np.ndarray | None, tol_bars: int,
                       thr_min: float, thr_max: float) -> dict[str, MatchResult]:
    """Score one mechanism's walk-forward output against hand truth.
    Returns {"dips": MatchResult, "peaks": MatchResult}."""
    tpos = truth_positions(truth, scores["timestamp"])
    return {
        "dips": match_events(extract_crossings(scores, "p_min", thr_min),
                             tpos["dip"], tol_bars, mask),
        "peaks": match_events(extract_crossings(scores, "p_max", thr_max),
                              tpos["peak"], tol_bars, mask),
    }


def label_quality(candles: list[dict], params: dict, truth: pd.DataFrame,
                  mask: np.ndarray | None, tol_bars: int) -> dict[str, MatchResult]:
    """Stage-1 metric: run the labeler ONCE over the full series (offline, not
    walk-forward) and match its class-0/class-1 sample indices against hand truth.
    This bounds what any model trained on these labels can achieve."""
    from trader.core.config import flatten_strategy_params
    from trader.features.labels import build_labeler

    flat = flatten_strategy_params(params)
    labeler = build_labeler("LAB", flat)
    indices, classes = labeler.label(candles)
    if labeler.dense:
        lab_min, lab_max = transition_indices(indices, classes)
    else:
        lab_min = [i for i, c in zip(indices, classes) if c == 0]
        lab_max = [i for i, c in zip(indices, classes) if c == 1]

    ts = pd.Series([c["timestamp"] for c in candles])
    tpos = truth_positions(truth, ts)
    return {
        "dips": match_events(lab_min, tpos["dip"], tol_bars, mask),
        "peaks": match_events(lab_max, tpos["peak"], tol_bars, mask),
    }


def as_trained_label_quality(retrains, n_bars: int, truth: pd.DataFrame,
                             index: pd.Series, mask: np.ndarray | None,
                             tol_bars: int) -> dict[str, MatchResult]:
    """Stage-1 variant using the union of samples the walk-forward retrains
    actually trained on (what the model really saw, window by window)."""
    seen_min: set[int] = set()
    seen_max: set[int] = set()
    for snap in retrains:
        for gi, cls in zip(snap.sample_indices, snap.sample_classes):
            (seen_min if cls == 0 else seen_max if cls == 1 else set()).add(gi)
    tpos = truth_positions(truth, index)
    return {
        "dips": match_events(sorted(seen_min), tpos["dip"], tol_bars, mask),
        "peaks": match_events(sorted(seen_max), tpos["peak"], tol_bars, mask),
    }


def comparison_table(evals: dict[str, dict[str, MatchResult]]) -> pd.DataFrame:
    """Rows = mechanism, columns = dip/peak precision, recall, F1, median lag, counts."""
    rows = []
    for mech, ev in evals.items():
        d, p = ev["dips"], ev["peaks"]
        rows.append({
            "mechanism": mech,
            "dip P": round(d.precision, 3), "dip R": round(d.recall, 3),
            "dip F1": round(d.f1, 3), "dip lag (bars)": d.median_lag,
            "dip TP/FP/FN": f"{d.tp}/{d.fp}/{d.fn}",
            "peak P": round(p.precision, 3), "peak R": round(p.recall, 3),
            "peak F1": round(p.f1, 3), "peak lag (bars)": p.median_lag,
            "peak TP/FP/FN": f"{p.tp}/{p.fp}/{p.fn}",
        })
    return pd.DataFrame(rows).set_index("mechanism")
