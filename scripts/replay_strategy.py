"""
replay_strategy.py — Replay LRExtremaStrategy on a single stock using cached candles.

Feeds every candle through the strategy and prints a per-candle table showing
the model's P(local-min) and P(local-max) at every bar, regardless of position state.

Usage:
    python scripts/replay_strategy.py NSE:MCX
    python scripts/replay_strategy.py NSE:MCX --from 2026-05-01
    python scripts/replay_strategy.py NSE:MCX --from 2026-05-01 --show-from 2026-06-01
"""

import argparse
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

from trader.core.config import config
from trader.data.store import Store
from trader.strategies.lr_extrema import LRExtremaStrategy


def _model_proba(strategy):
    """Compute P(local-min), P(local-max), and raw features from the trained model."""
    if not strategy._trained:
        return 0.0, 0.0, None
    x = strategy._compute_features(strategy._candles)
    if x is None:
        return 0.0, 0.0, None
    x_scaled = strategy._scaler.transform(x.reshape(1, -1))
    classes = list(strategy._model.classes_)
    proba = strategy._model.predict_proba(x_scaled)[0]
    p_min = proba[classes.index(0)] if 0 in classes else 0.0
    p_max = proba[classes.index(1)] if 1 in classes else 0.0
    return p_min, p_max, x


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", help="e.g. NSE:MCX")
    parser.add_argument("--from", dest="from_date", default=None,
                        help="Start date for candle window fed to strategy (default: 2023-01-01)")
    parser.add_argument("--show-from", default=None,
                        help="Only print rows from this date onward (strategy still warms up from --from)")
    parser.add_argument("--features", action="store_true",
                        help="Print raw feature vector alongside each row")
    args = parser.parse_args()

    symbol    = args.symbol
    from_date = args.from_date or "2023-01-01"
    show_from = (
        datetime.datetime.strptime(args.show_from, "%Y-%m-%d")
        if args.show_from else None
    )

    store   = Store(config.db_path)
    from_dt = datetime.datetime.strptime(from_date, "%Y-%m-%d")
    df      = store.read_candles(symbol, config.candle_timeframe, from_dt, datetime.datetime.now())

    if df.empty:
        print(f"No cached candles for {symbol}. Run a live fetch first.")
        sys.exit(1)

    candles = df.to_dict("records")
    print(f"Loaded {len(candles)} candles for {symbol} "
          f"({candles[0]['timestamp']} → {candles[-1]['timestamp']})",
          file=sys.stderr)

    params   = config.get_strategy_params(symbol, "lr_extrema")
    strategy = LRExtremaStrategy(symbol, params)

    threshold      = params.get("threshold", 0.90)
    sell_threshold = params.get("sell_threshold", 0.85)

    has_depth = params.get("depth_feature", {}).get("enabled", True)
    feat_names = ["vol_ratio", "norm_price", "slope3", "slope5", "slope10", "slope20"]
    if has_depth:
        feat_names.append("depth")

    print(f"\nParams: threshold={threshold}  sell_threshold={sell_threshold}  "
          f"profit_pct={params.get('profit_pct', 10.0)}  "
          f"trail_pct={params.get('trail_pct', 2.5)}")
    print()
    header = (f"{'Timestamp':<22} {'Close':>9} {'Change%':>8} "
              f"{'P(min)':>8} {'P(max)':>8}  Notes")
    if args.features:
        header += f"   [{', '.join(feat_names)}]"
    print(header)
    print("-" * (90 + (55 if args.features else 0)))

    prev_close = None
    for candle in candles:
        ts    = candle["timestamp"]
        ts_dt = datetime.datetime.fromisoformat(str(ts))

        # Advance the strategy's internal candle buffer and retrain schedule,
        # but suppress the signal — we'll compute probabilities ourselves.
        strategy.on_candle(candle)

        # Reset position guard so every candle runs the entry-prediction path
        # (we only want raw probabilities — no fill simulation needed).
        strategy._entry_price = None
        strategy.position     = None

        # Compute model probabilities directly (unaffected by position state)
        p_min, p_max, feat_vec = _model_proba(strategy)

        # Skip display rows before show_from
        if show_from is not None and ts_dt < show_from:
            prev_close = candle["close"]
            continue

        close = candle["close"]
        chg   = (close - prev_close) / prev_close * 100 if prev_close else 0.0

        notes = []
        if p_min >= threshold:
            notes.append(f"ENTRY_GATE (p_min≥{threshold})")
        if p_max >= sell_threshold:
            notes.append(f"SELL_GATE (p_max≥{sell_threshold})")

        note_str = "  " + ", ".join(notes) if notes else ""
        row = (f"{str(ts):<22} {close:>9.2f} {chg:>+7.2f}% "
               f"{p_min:>8.3f} {p_max:>8.3f}{note_str}")
        if args.features and feat_vec is not None:
            feat_str = "  [" + ", ".join(f"{v:+.4f}" for v in feat_vec) + "]"
            row += feat_str
        print(row)

        prev_close = close


if __name__ == "__main__":
    main()
