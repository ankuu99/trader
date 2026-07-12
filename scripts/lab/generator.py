"""
Synthetic candle generator for the extrema lab.

Produces ~4 years of 15-minute candles per scenario: a noise-free signal path
(sines + trend + regime switches + optional falling knife) plus gaussian noise,
turned into OHLCV bars. The noise-free signal's extrema are stored in meta.json
as `true_extrema` — used only for optional label pre-seeding in the UI, never as
ground truth directly (truth is hand-labeled).

Everything is deterministic given (spec, seed): the time index depends only on
days/start_date, so hand labels keyed by timestamp survive regeneration.

Persistence: lab_data/<scenario>/candles.csv + meta.json (CSV keeps us free of a
parquet dependency; ~25k rows is trivial).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
LAB_DATA_DIR = ROOT / "lab_data"

BARS_PER_DAY = 25  # 09:15 + k*15min for k=0..23 (09:15..15:00), plus 15:30
GENERATOR_VERSION = 1


def make_session_index(days: int = 990, start_date: str = "2022-07-01") -> list[pd.Timestamp]:
    """Tz-naive 15m session timestamps for `days` weekdays: 09:15..15:00 + 15:30."""
    out: list[pd.Timestamp] = []
    day = datetime.fromisoformat(start_date)
    added = 0
    while added < days:
        if day.weekday() < 5:  # Mon-Fri
            base = day.replace(hour=9, minute=15)
            for k in range(24):
                out.append(pd.Timestamp(base + timedelta(minutes=15 * k)))
            out.append(pd.Timestamp(day.replace(hour=15, minute=30)))
            added += 1
        day += timedelta(days=1)
    return out


@dataclass
class ScenarioSpec:
    name: str
    seed: int = 7
    base_price: float = 500.0
    days: int = 990
    start_date: str = "2022-07-01"
    # (period_bars, amplitude_pct) per sine component
    sine_cycles: list[tuple[float, float]] = field(default_factory=list)
    trend_pct_per_year: float = 0.0
    noise_pct: float = 0.0  # per-bar gaussian sigma as % of base price
    # piecewise noise override: list of (start_bar, noise_pct) — for the noise ladder
    noise_schedule: list[tuple[int, float]] = field(default_factory=list)
    # regime switches: list of (start_bar, {"sine_cycles": [...], "trend_pct_per_year": x})
    regime_switches: list[tuple[int, dict]] = field(default_factory=list)
    # falling knife: {"start_bar": int, "len_bars": int, "drop_pct": float,
    #                 "recover_bars": int, "recover_pct": float}
    knife: dict | None = None
    volume_spike_at_extrema: bool = True
    # half-window used to derive true extrema from the noise-free signal
    truth_order: int = 25


BARS_PER_YEAR = BARS_PER_DAY * 250  # ≈ trading year


def _signal_path(spec: ScenarioSpec, n: int) -> np.ndarray:
    """Noise-free close path: piecewise (regime-switched) sines + trend + knife."""
    # Regime segments: (start_bar, cycles, trend)
    segments: list[tuple[int, list[tuple[float, float]], float]] = [
        (0, spec.sine_cycles, spec.trend_pct_per_year)
    ]
    for start_bar, overrides in spec.regime_switches:
        prev = segments[-1]
        segments.append((
            start_bar,
            overrides.get("sine_cycles", prev[1]),
            overrides.get("trend_pct_per_year", prev[2]),
        ))

    signal = np.zeros(n)
    level = 0.0  # cumulative trend level (pct of base) carried across segments
    for si, (start, cycles, trend) in enumerate(segments):
        end = segments[si + 1][0] if si + 1 < len(segments) else n
        t = np.arange(end - start)
        seg = np.zeros(end - start)
        for period, amp_pct in cycles:
            # phase continuity across segments is not needed — a regime switch is
            # allowed to look like a structural break
            seg += (amp_pct / 100.0) * spec.base_price * np.sin(2 * math.pi * t / period)
        seg += level * spec.base_price / 100.0
        seg += (trend / 100.0) * spec.base_price * (t / BARS_PER_YEAR)
        level += trend * (end - start) / BARS_PER_YEAR
        signal[start:end] = seg

    if spec.knife:
        k = spec.knife
        s, ln = int(k["start_bar"]), int(k["len_bars"])
        drop = float(k["drop_pct"]) / 100.0 * spec.base_price
        rec_ln = int(k.get("recover_bars", ln))
        rec = float(k.get("recover_pct", k["drop_pct"] * 0.6)) / 100.0 * spec.base_price
        e = min(s + ln, n)
        # linear drop, then partial linear recovery, then permanent offset
        knife_path = np.zeros(n)
        knife_path[s:e] = -drop * (np.arange(e - s) + 1) / ln
        re_ = min(e + rec_ln, n)
        knife_path[e:re_] = -drop + rec * (np.arange(re_ - e) + 1) / rec_ln
        knife_path[re_:] = -drop + rec
        signal += knife_path

    return spec.base_price + signal


def _noise_sigma_per_bar(spec: ScenarioSpec, n: int) -> np.ndarray:
    sigma = np.full(n, spec.noise_pct / 100.0 * spec.base_price)
    for start_bar, pct in spec.noise_schedule:
        sigma[start_bar:] = pct / 100.0 * spec.base_price
    return sigma


def _collapse_clusters(indices: list[int], max_gap: int) -> list[int]:
    """Collapse runs of nearby indices (gap <= max_gap) to the cluster centre."""
    if not indices:
        return []
    out, cluster = [], [indices[0]]
    for idx in indices[1:]:
        if idx - cluster[-1] <= max_gap:
            cluster.append(idx)
        else:
            out.append(cluster[len(cluster) // 2])
            cluster = [idx]
    out.append(cluster[len(cluster) // 2])
    return out


def generate(spec: ScenarioSpec) -> tuple[pd.DataFrame, dict]:
    """Return (candles_df[timestamp,open,high,low,close,volume], meta)."""
    from trader.features.indicators import find_local_extrema

    index = make_session_index(spec.days, spec.start_date)
    n = len(index)
    rng = np.random.default_rng(spec.seed)

    signal = _signal_path(spec, n)
    sigma = _noise_sigma_per_bar(spec, n)
    close = signal + rng.normal(0.0, 1.0, n) * sigma
    close = np.maximum(close, spec.base_price * 0.02)  # floor > 0

    # True extrema of the NOISE-FREE signal (pre-seed aid only). Zero-noise
    # scenarios produce plateaus (runs of equal values) where every bar in the run
    # qualifies as an extremum — collapse each cluster to its centre.
    minima, maxima = find_local_extrema(signal.tolist(), spec.truth_order)
    minima = _collapse_clusters(minima, spec.truth_order)
    maxima = _collapse_clusters(maxima, spec.truth_order)

    # OHLC from the close path
    open_ = np.empty(n)
    open_[0] = spec.base_price
    open_[1:] = close[:-1]
    body = np.abs(close - open_)
    tick_floor = spec.base_price * 0.0005
    wick_hi = np.abs(rng.normal(0.0, 0.35, n)) * np.maximum(body, tick_floor)
    wick_lo = np.abs(rng.normal(0.0, 0.35, n)) * np.maximum(body, tick_floor)
    high = np.maximum(open_, close) + wick_hi
    low = np.maximum(np.minimum(open_, close) - wick_lo, spec.base_price * 0.01)

    # Volume: log-normal base × U-shaped intraday × optional extrema bump
    volume = np.exp(rng.normal(math.log(50_000), 0.35, n))
    bar_of_day = np.arange(n) % BARS_PER_DAY
    u_shape = np.where((bar_of_day < 2) | (bar_of_day >= BARS_PER_DAY - 2), 1.6, 1.0)
    volume *= u_shape
    if spec.volume_spike_at_extrema and (minima or maxima):
        ext = np.array(sorted(minima + maxima))
        # distance to nearest true extremum, vectorised via searchsorted
        pos = np.searchsorted(ext, np.arange(n))
        left = ext[np.clip(pos - 1, 0, len(ext) - 1)]
        right = ext[np.clip(pos, 0, len(ext) - 1)]
        dist = np.minimum(np.abs(np.arange(n) - left), np.abs(np.arange(n) - right))
        volume *= 1.0 + 1.5 * np.exp(-((dist / 3.0) ** 2))
    volume = np.round(volume).astype(int)

    df = pd.DataFrame({
        "timestamp": index,
        "open": np.round(open_, 2),
        "high": np.round(high, 2),
        "low": np.round(low, 2),
        "close": np.round(close, 2),
        "volume": volume,
    })

    meta = {
        "generator_version": GENERATOR_VERSION,
        "spec": asdict(spec),
        "n_bars": n,
        "true_extrema": {
            "minima": [index[i].isoformat() for i in minima],
            "maxima": [index[i].isoformat() for i in maxima],
        },
    }
    return df, meta


# ---------------------------------------------------------------------------
# Scenario registry — increasing difficulty
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, ScenarioSpec] = {
    # 1. Sanity floor: one clean sine (~10-day cycle), zero noise.
    "s1_clean_sine": ScenarioSpec(
        name="s1_clean_sine",
        sine_cycles=[(250, 4.0)],
        noise_pct=0.0,
    ),
    # 2. Same sine on a rising baseline — dips on a drifting trend.
    "s2_sine_trend": ScenarioSpec(
        name="s2_sine_trend",
        sine_cycles=[(250, 4.0)],
        trend_pct_per_year=15.0,
        noise_pct=0.05,
    ),
    # 3. Multi-frequency: fast + medium + slow cycles, light noise.
    "s3_multi_freq": ScenarioSpec(
        name="s3_multi_freq",
        sine_cycles=[(250, 4.0), (60, 1.5), (1000, 8.0)],
        noise_pct=0.05,
    ),
    # 4. Noise ladder: s1 sine, noise steps up each quarter of the series.
    "s4_noise_ladder": ScenarioSpec(
        name="s4_noise_ladder",
        sine_cycles=[(250, 4.0)],
        noise_schedule=[(0, 0.05), (6188, 0.10), (12375, 0.20), (18563, 0.40)],
    ),
    # 5. Regime switch: range → trend → range with changed cycle geometry.
    "s5_regime_switch": ScenarioSpec(
        name="s5_regime_switch",
        sine_cycles=[(250, 4.0)],
        noise_pct=0.08,
        regime_switches=[
            (6000, {"sine_cycles": [(400, 2.0)], "trend_pct_per_year": 40.0}),
            (12000, {"sine_cycles": [(150, 5.0)], "trend_pct_per_year": 0.0}),
            (18000, {"sine_cycles": [(250, 3.0)], "trend_pct_per_year": -20.0}),
        ],
    ),
    # 6. Falling knife: multi-freq base plus a 30% drop over 750 bars mid-series,
    #    partial recovery — the known failure mode.
    "s6_falling_knife": ScenarioSpec(
        name="s6_falling_knife",
        sine_cycles=[(250, 4.0), (60, 1.5), (1000, 8.0)],
        noise_pct=0.08,
        knife={"start_bar": 12000, "len_bars": 750, "drop_pct": 30.0,
               "recover_bars": 1500, "recover_pct": 18.0},
    ),
    # 7. Realistic headline case: trend AND noise together (s2 + meaningful noise).
    #    Real stocks are never one without the other.
    "s7_trend_noise": ScenarioSpec(
        name="s7_trend_noise",
        sine_cycles=[(250, 4.0)],
        trend_pct_per_year=15.0,
        noise_pct=0.18,
    ),
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def scenario_dir(name: str) -> Path:
    return LAB_DATA_DIR / name


def save_scenario(spec: ScenarioSpec, out_dir: Path | None = None) -> Path:
    df, meta = generate(spec)
    d = (out_dir or LAB_DATA_DIR) / spec.name
    d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / "candles.csv", index=False)
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    return d


def load_scenario(name: str, base_dir: Path | None = None) -> tuple[pd.DataFrame, dict]:
    d = (base_dir or LAB_DATA_DIR) / name
    df = pd.read_csv(d / "candles.csv", parse_dates=["timestamp"])
    meta = json.loads((d / "meta.json").read_text())
    return df, meta


def scenario_exists(name: str, base_dir: Path | None = None) -> bool:
    d = (base_dir or LAB_DATA_DIR) / name
    return (d / "candles.csv").exists() and (d / "meta.json").exists()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    names = sys.argv[1:] or list(SCENARIOS)
    for nm in names:
        spec = SCENARIOS[nm]
        d = save_scenario(spec)
        df, meta = load_scenario(nm)
        assert (df["low"] <= df[["open", "close"]].min(axis=1) + 1e-9).all()
        assert (df["high"] >= df[["open", "close"]].max(axis=1) - 1e-9).all()
        assert (df["volume"] > 0).all()
        assert not df.isna().any().any()
        print(f"{nm}: {len(df)} bars, "
              f"{len(meta['true_extrema']['minima'])} true minima, "
              f"{len(meta['true_extrema']['maxima'])} true maxima -> {d}")
