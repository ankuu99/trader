"""Filesystem layout of the Model Lab.

Everything lives under lab_data/model_lab/ — never in data/market.db, which
backtest.py / backtest_rolling.py / walk_forward.py wipe via clear_backtest_data().
Bars are parquet (not a second SQLite Store): the disk had 7.8 GB free on
2026-10-18 and parquet is ~10x smaller per candle (DECISIONS 2026-10-18).
"""
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAB_ROOT = REPO_ROOT / "lab_data" / "model_lab"

BARS_DIR = LAB_ROOT / "bars"            # bars/<kite interval>/<SYMBOL>.parquet  (native: 15minute, day)
UNIVERSE_DIR = LAB_ROOT / "universe"    # instrument snapshots + liquidity panel
FACTORS_DIR = LAB_ROOT / "factors"      # factors/<tf>/<SYMBOL>.parquet
TARGETS_DIR = LAB_ROOT / "targets"      # targets/<tf>/<SYMBOL>.parquet
LOGS_DIR = LAB_ROOT / "logs"
RUNS_DIR = LAB_ROOT / "runs"            # runs/<run_id>/{meta.json, folds.parquet, scores/<SYMBOL>.parquet}
PORTFOLIOS_DIR = LAB_ROOT / "portfolios"  # portfolios/<sim_id>/{trades,equity}.parquet, summary.json (portfolio.py)
NSE_BHAV_DIR = LAB_ROOT / "nse_bhav"    # nse_bhav/{raw/<YYYY>/<YYYYMMDD>.zip, panel/<YYYY>.parquet, securities.parquet, ...} (nse_bhav.py)
REFS_DIR = LAB_ROOT / "refs"            # refs/<tf>/<ref_name>/<SYMBOL>.parquet (timestamp, score[, p_max])

MIN_FREE_GB = 3.0                       # writers refuse to run below this much free disk


def sym_file(symbol: str) -> str:
    """'NSE:M&MFIN' -> 'M&MFIN', 'NSE:NIFTY 50' -> 'NIFTY_50' (file stem)."""
    return symbol.split(":", 1)[-1].replace(" ", "_")


def file_sym(stem: str) -> str:
    """Inverse of sym_file: 'NIFTY_50' -> 'NSE:NIFTY 50'."""
    return "NSE:" + stem.replace("_", " ")


def free_gb(path: Path = REPO_ROOT) -> float:
    return shutil.disk_usage(path).free / 1e9


def check_disk(min_free_gb: float = MIN_FREE_GB) -> None:
    """Raise before writing when the disk is nearly full."""
    free = free_gb()
    if free < min_free_gb:
        raise RuntimeError(f"only {free:.1f} GB free (< {min_free_gb} GB) — free disk before writing lab data")
