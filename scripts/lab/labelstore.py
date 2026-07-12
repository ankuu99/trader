"""
Hand-label persistence for the extrema lab.

Per scenario directory (lab_data/<scenario>/):
  labels.csv    — timestamp,kind   (kind in {dip, peak}); one row per hand label
  coverage.csv  — start_ts,end_ts  (inclusive) ranges the user has REVIEWED
                  (labeled, or confirmed empty). Metrics only count covered bars.

Every mutation writes to disk immediately — files are tiny, Streamlit reruns are
frequent, and losing labeling work is the worst possible UX.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

KINDS = ("dip", "peak")


class LabelStore:
    def __init__(self, scenario_dir: Path):
        self._dir = Path(scenario_dir)
        self._labels_path = self._dir / "labels.csv"
        self._coverage_path = self._dir / "coverage.csv"

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def load(self) -> pd.DataFrame:
        """Return labels df (timestamp: pd.Timestamp, kind: str), sorted."""
        if not self._labels_path.exists():
            return pd.DataFrame(columns=["timestamp", "kind"])
        df = pd.read_csv(self._labels_path, parse_dates=["timestamp"])
        return df.sort_values("timestamp").reset_index(drop=True)

    def _save_labels(self, df: pd.DataFrame) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
        df.to_csv(self._labels_path, index=False)

    def add(self, ts, kind: str) -> None:
        assert kind in KINDS, kind
        df = self.load()
        ts = pd.Timestamp(ts)
        df = df[df["timestamp"] != ts]  # replace any existing label at this bar
        df = pd.concat([df, pd.DataFrame([{"timestamp": ts, "kind": kind}])])
        self._save_labels(df)

    def remove(self, ts) -> None:
        df = self.load()
        self._save_labels(df[df["timestamp"] != pd.Timestamp(ts)])

    def remove_nearest(self, ts, index: pd.Series, tol_bars: int = 2) -> bool:
        """Remove the label nearest to ts within ±tol_bars of the candle index.
        Returns True if something was removed."""
        df = self.load()
        if df.empty:
            return False
        idx = pd.to_datetime(index).reset_index(drop=True)
        pos_of = {t: i for i, t in enumerate(idx)}
        target = pos_of.get(pd.Timestamp(ts))
        if target is None:
            return False
        best_ts, best_d = None, tol_bars + 1
        for t in df["timestamp"]:
            p = pos_of.get(pd.Timestamp(t))
            if p is not None and abs(p - target) < best_d:
                best_ts, best_d = t, abs(p - target)
        if best_ts is None:
            return False
        self.remove(best_ts)
        return True

    def clear_range(self, start_ts, end_ts) -> int:
        """Delete all labels in [start_ts, end_ts]. Returns count removed."""
        df = self.load()
        m = (df["timestamp"] >= pd.Timestamp(start_ts)) & (df["timestamp"] <= pd.Timestamp(end_ts))
        self._save_labels(df[~m])
        return int(m.sum())

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def coverage(self) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """Merged, sorted reviewed ranges."""
        if not self._coverage_path.exists():
            return []
        df = pd.read_csv(self._coverage_path, parse_dates=["start_ts", "end_ts"])
        ranges = sorted(
            (pd.Timestamp(r.start_ts), pd.Timestamp(r.end_ts)) for r in df.itertuples()
        )
        merged: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        for s, e in ranges:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))
        return merged

    def _save_coverage(self, ranges: list[tuple[pd.Timestamp, pd.Timestamp]]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(ranges, columns=["start_ts", "end_ts"]).to_csv(
            self._coverage_path, index=False
        )

    def mark_covered(self, start_ts, end_ts) -> None:
        ranges = self.coverage() + [(pd.Timestamp(start_ts), pd.Timestamp(end_ts))]
        self._save_coverage(ranges)
        # re-merge via coverage() round-trip
        self._save_coverage(self.coverage())

    def unmark_covered(self, start_ts, end_ts) -> None:
        """Punch a hole [start_ts, end_ts] out of the covered ranges."""
        s0, e0 = pd.Timestamp(start_ts), pd.Timestamp(end_ts)
        out = []
        for s, e in self.coverage():
            if e < s0 or s > e0:
                out.append((s, e))
                continue
            if s < s0:
                out.append((s, s0 - pd.Timedelta(seconds=1)))
            if e > e0:
                out.append((e0 + pd.Timedelta(seconds=1), e))
        self._save_coverage(out)

    def coverage_mask(self, index: pd.Series | pd.DatetimeIndex) -> np.ndarray:
        """Bool per candle: True where the bar falls in a reviewed range."""
        idx = pd.to_datetime(pd.Series(index)).reset_index(drop=True)
        mask = np.zeros(len(idx), dtype=bool)
        for s, e in self.coverage():
            mask |= ((idx >= s) & (idx <= e)).to_numpy()
        return mask

    def coverage_pct(self, index: pd.Series | pd.DatetimeIndex) -> float:
        m = self.coverage_mask(index)
        return 100.0 * m.mean() if len(m) else 0.0

    # ------------------------------------------------------------------
    # Pre-seed
    # ------------------------------------------------------------------

    def seed_from_true_extrema(self, meta: dict, start_ts=None, end_ts=None) -> int:
        """Add labels from the generator's noise-free extrema (optionally window-
        restricted). Convenience only — the user is expected to correct them.
        Returns number of labels added."""
        added = 0
        df = self.load()
        existing = set(df["timestamp"])
        rows = []
        for kind, key in (("dip", "minima"), ("peak", "maxima")):
            for t in meta["true_extrema"][key]:
                ts = pd.Timestamp(t)
                if start_ts is not None and ts < pd.Timestamp(start_ts):
                    continue
                if end_ts is not None and ts > pd.Timestamp(end_ts):
                    continue
                if ts in existing:
                    continue
                rows.append({"timestamp": ts, "kind": kind})
                added += 1
        if rows:
            self._save_labels(pd.concat([df, pd.DataFrame(rows)]))
        return added
