"""
Price layer — bridges Kite daily candles to the FVM engine's `price_data` dict.

Reuses the generic `trader.data.historical` + `Store` (candles cached in the existing DB;
FVM uses the "day" timeframe — no native week interval, so weekly is resampled in
`technical.resample_weekly`). Kite has no week/month interval (CORE_INFRASTRUCTURE §A4).

Provides:
- resolve_tokens(kite, symbols)         : NSE code -> Kite instrument_token
- load_universe_prices(...)             : {symbol: daily OHLCV df}  (cache-first; kite=None ok)
- price_provider(price_data, asof)      : callable(symbol) -> last close <= asof  (for PEG/P-E)
"""

import pandas as pd

from trader.core.logger import get_logger
from trader.data import historical

logger = get_logger(__name__)


def resolve_tokens(kite, symbols: list[str]) -> dict[str, int]:
    """Map NSE trading symbols -> Kite instrument tokens (EQ segment).

    Tolerant of segment suffixes: NSE lists trade-to-trade / surveillance names
    with a `-BE` (or similar) suffix (e.g. `IDEAFORGE-BE`), so an exact match on
    the bare symbol would miss them. We match on the suffix-stripped base too and
    key the result by the requested symbol.
    """
    want = {s.upper() for s in symbols}
    out: dict[str, int] = {}
    for inst in kite.instruments("NSE"):
        if inst.get("instrument_type") != "EQ":
            continue
        ts = inst.get("tradingsymbol", "").upper()
        base = ts.split("-")[0]                # IDEAFORGE-BE -> IDEAFORGE
        if ts in want:
            out[ts] = inst["instrument_token"]
        elif base in want:
            out[base] = inst["instrument_token"]
    missing = want - set(out)
    if missing:
        logger.warning("resolve_tokens: %d symbols unresolved (not found in NSE EQ "
                       "instrument dump): %s", len(missing), sorted(missing)[:5])
    return out


def load_universe_prices(kite, store, symbols, from_dt, to_dt,
                         token_map: dict[str, int] | None = None,
                         min_bars: int = 60) -> dict[str, pd.DataFrame]:
    """{symbol: daily df} for symbols with >= min_bars cached/fetched. kite=None = cache-only."""
    token_map = token_map or (resolve_tokens(kite, symbols) if kite is not None else {})
    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        tok = token_map.get(s.upper(), 0)
        if not tok and kite is not None:             # unresolved symbol — don't pass token 0 to Kite
                                                     # (cache-only mode keys by instrument string, token unused)
            logger.warning("skipping %s: no Kite instrument token (symbol not found in NSE EQ "
                           "dump; check the trading symbol / segment suffix)", s.upper())
            continue
        try:
            df = historical.get_candles(kite, store, tok, f"NSE:{s.upper()}", "day", from_dt, to_dt)
        except Exception as e:                       # one symbol failing must not abort the run
            logger.warning("price fetch failed for %s: %s", s, e)
            continue
        if len(df) >= min_bars:
            out[s.upper()] = df
    return out


def price_provider(price_data: dict[str, pd.DataFrame], asof: str):
    """Return f(symbol) -> last daily close on/before `asof` (for valuation factors)."""
    ts = pd.to_datetime(asof)

    def _f(symbol: str):
        df = price_data.get(symbol.upper())
        if df is None or df.empty:
            return None
        d = df[pd.to_datetime(df["timestamp"]) <= ts]
        return float(d["close"].iloc[-1]) if len(d) else None

    return _f
