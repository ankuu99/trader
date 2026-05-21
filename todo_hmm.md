# HMM Regime Gate — Porting Guide

Port these changes to a clean branch. All changes are self-contained and additive
(no existing behaviour changes when `hmm_enabled: false`, which is the default).

Also bundled here: the **Bollinger Band squeeze entry filter** added in the same
session. It lives entirely inside `lr_extrema.py` and is also off by default.

---

## Files to create (new)

### `trader/strategies/regime_hmm.py` — create from scratch

```python
"""
Gaussian HMM market regime filter.

Trains on daily Nifty 50 returns extracted from _nifty_close values injected
into candle dicts by the backtest engine (and live feed, when wired).

Two hidden states are learned:
  - Favourable  : low-variance state — calm, trending market; LR entries are reliable
  - Unfavourable: high-variance state — choppy, volatile market; LR entries degrade

Used as an entry gate inside LRExtremaStrategy. Fail-open: when not fitted (e.g.
insufficient Nifty data in warmup) the gate passes all entries through.

Requires: hmmlearn (pip install hmmlearn)
"""

import numpy as np

try:
    from hmmlearn.hmm import GaussianHMM as _GaussianHMM
    _HMMLEARN_AVAILABLE = True
except ImportError:
    _HMMLEARN_AVAILABLE = False

from trader.core.logger import get_logger

logger = get_logger(__name__)

_MIN_DAILY_OBS = 30  # minimum daily return observations to fit


class RegimeHMM:
    """2-state Gaussian HMM trained on daily Nifty 50 returns."""

    def __init__(self, n_states: int = 2, lookback_days: int = 120):
        self._n_states = n_states
        self._lookback_days = lookback_days
        self._model = None
        self._favourable_state: int | None = None
        self._current_state: int | None = None
        self._fitted: bool = False

    def fit(self, candles: list[dict]) -> bool:
        if not _HMMLEARN_AVAILABLE:
            logger.warning("RegimeHMM | hmmlearn not installed — regime gate disabled")
            return False

        daily: dict[str, float] = {}
        for c in candles:
            nifty = c.get("_nifty_close")
            ts = c.get("timestamp")
            if nifty is None or ts is None:
                continue
            daily[ts.date().isoformat()] = nifty  # last candle of day wins

        dates = sorted(daily)[-self._lookback_days - 1:]
        if len(dates) < _MIN_DAILY_OBS + 1:
            return False

        closes = [daily[d] for d in dates]
        returns = np.array(
            [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))],
            dtype=float,
        ).reshape(-1, 1)

        if len(returns) < _MIN_DAILY_OBS:
            return False

        try:
            model = _GaussianHMM(
                n_components=self._n_states,
                covariance_type="full",
                n_iter=200,
                random_state=42,
            )
            model.fit(returns)
        except Exception as exc:
            logger.warning("RegimeHMM fit failed: %s", exc)
            return False

        variances = [float(model.covars_[s][0][0]) for s in range(self._n_states)]
        self._favourable_state = int(np.argmin(variances))
        self._current_state = int(model.predict(returns)[-1])
        self._model = model
        self._fitted = True

        logger.info(
            "RegimeHMM fitted | states=%d | favourable=%d | current=%d | "
            "variances=%s | obs=%d",
            self._n_states, self._favourable_state, self._current_state,
            [f"{v:.2e}" for v in variances], len(returns),
        )
        return True

    def is_favourable(self) -> bool:
        """Fail-open: returns True when model not fitted."""
        if not self._fitted or self._current_state is None:
            return True
        return self._current_state == self._favourable_state
```

---

## Files to modify

### 1. `requirements.txt`

Add after the `xgboost` line:

```
hmmlearn>=0.3.0
```

Install locally: `pip install "hmmlearn>=0.3.0"`

---

### 2. `trader/strategies/lr_extrema.py`

#### 2a. Add to docstring (after `regime_vix_symbol` line)

```
    bb_squeeze_period        : BB period for squeeze filter (default 20)
    bb_squeeze_lookback      : bars to compute width percentile over (default 50)
    bb_squeeze_max_percentile: block entry when BB width percentile > this; 0 = disabled (default 0)
    hmm_enabled              : enable HMM regime gate (default false)
    hmm_n_states             : number of HMM hidden states (default 2)
    hmm_lookback_days        : days of Nifty history for HMM training (default 120)
```

#### 2b. Add import (after the existing `from trader.strategies.base import ...` line)

```python
from trader.strategies.regime_hmm import RegimeHMM
```

#### 2c. Add to `__init__` (after the `_entry_require_prior_decline` line)

```python
        # --- Bollinger Band squeeze filter (0 = disabled) ---
        # Blocks entry when BB width percentile > bb_squeeze_max_percentile, meaning
        # volatility is unusually wide/choppy relative to recent history.
        # e.g. max_percentile=75 → only enter when width is in the calmer 75% of history.
        self._bb_squeeze_period: int = params.get("bb_squeeze_period", 20)
        self._bb_squeeze_lookback: int = params.get("bb_squeeze_lookback", 50)
        self._bb_squeeze_max_percentile: float = params.get("bb_squeeze_max_percentile", 0.0)

        # --- HMM regime gate (disabled by default) ---
        # When enabled, blocks entries during the high-volatility HMM regime state.
        # Trains on daily Nifty 50 returns from _nifty_close values in the candle buffer.
        self._hmm_enabled: bool = bool(params.get("hmm_enabled", False))
        self._hmm_n_states: int = params.get("hmm_n_states", 2)
        self._hmm_lookback_days: int = params.get("hmm_lookback_days", 120)
        self._regime_hmm: RegimeHMM | None = (
            RegimeHMM(n_states=self._hmm_n_states, lookback_days=self._hmm_lookback_days)
            if self._hmm_enabled else None
        )
```

#### 2d. Add to the entry filter gates block in `on_candle` (after the `entry_require_prior_decline` check, before the `if blocks:` check)

```python
                    if self._bb_squeeze_max_percentile > 0:
                        bw_pct = self._bb_width_percentile(list(self._candles))
                        if bw_pct is not None and bw_pct > self._bb_squeeze_max_percentile:
                            blocks.append(f"bb_width_pct={bw_pct:.1f}>{self._bb_squeeze_max_percentile}")
                    if self._regime_hmm is not None and not self._regime_hmm.is_favourable():
                        blocks.append("hmm_regime=unfavourable")
```

#### 2e. Add at the end of `_train()` (after `self._trained = True`)

```python
        if self._regime_hmm is not None:
            self._regime_hmm.fit(candles)
```

#### 2f. Add `_bb_width_percentile` method (alongside other static/instance helpers, before `_find_local_extrema`)

```python
    def _bb_width_percentile(self, candles: list[dict]) -> float | None:
        """Return the percentile (0–100) of the current BB width within the recent lookback.

        BB width = (upper - lower) / middle, where bands use bb_squeeze_period SMA ± 2σ.
        Percentile = fraction of the last bb_squeeze_lookback widths that are <= current width.
        Returns None when not enough candles are available.
        """
        period = self._bb_squeeze_period
        lookback = self._bb_squeeze_lookback
        needed = period + lookback - 1
        if len(candles) < needed:
            return None
        closes = [c["close"] for c in candles[-(needed):]]

        def _bw(window: list[float]) -> float:
            n = len(window)
            mean = sum(window) / n
            std = (sum((p - mean) ** 2 for p in window) / n) ** 0.5
            return (4 * std) / mean if mean > 0 else 0.0

        widths = [_bw(closes[i: i + period]) for i in range(lookback)]
        current_bw = widths[-1]
        rank = sum(1 for w in widths if w <= current_bw)
        return rank / len(widths) * 100.0
```

---

### 3. `trader/data/live.py`

#### 3a. Add to `__init__` (after `self._tokens: list[int] = []`)

```python
        # Regime index tokens — tracked but never emitted as candles.
        # Maps instrument_token → key ("nifty" | "vix") and stores latest close.
        self._regime_token_map: dict[int, str] = {}   # token → "nifty" | "vix"
        self._regime_closes: dict[str, float] = {}    # "nifty" | "vix" → latest last_price
```

#### 3b. Add new public method `set_regime_tokens` (after the `subscribe` method)

```python
    def set_regime_tokens(
        self,
        nifty_token: int | None = None,
        vix_token: int | None = None,
    ) -> None:
        """Register NIFTY 50 and INDIA VIX tokens for regime close injection.

        These tokens are subscribed alongside watchlist tokens but their ticks are
        never assembled into candles — only the latest last_price is tracked and
        injected as _nifty_close / _vix_close into every emitted watchlist candle.
        """
        if nifty_token:
            self._regime_token_map[nifty_token] = "nifty"
            logger.info("Regime token registered | nifty_token=%d", nifty_token)
        if vix_token:
            self._regime_token_map[vix_token] = "vix"
            logger.info("Regime token registered | vix_token=%d", vix_token)
```

#### 3c. Replace `_on_connect` subscribe block

```python
    def _on_connect(self, ws, response):
        logger.info("KiteTicker connected")
        all_tokens = list(self._tokens)
        regime_tokens = list(self._regime_token_map.keys())
        if all_tokens or regime_tokens:
            ws.subscribe(all_tokens + regime_tokens)
            ws.set_mode(ws.MODE_FULL, all_tokens + regime_tokens)
```

#### 3d. Add regime-tick interception in `_process_tick` (after the `logger.debug("Tick | ...")` line, before `volume = tick.get(...)`)

```python
        # Regime index ticks — update latest close and skip candle assembly
        if token in self._regime_token_map:
            if ltp is not None:
                key = self._regime_token_map[token]
                self._regime_closes[key] = ltp
            return
```

#### 3e. Add regime injection in `_emit_candle` (add two keys to the candle dict)

```python
            "_nifty_close": self._regime_closes.get("nifty"),
            "_vix_close": self._regime_closes.get("vix"),
```

---

### 4. `main.py`

#### 4a. After building `symbol_to_token` / `token_to_symbol` — add regime token lookup

```python
    # Regime index tokens (NIFTY 50, INDIA VIX) — used for HMM regime gate features
    _NIFTY_SYMBOL = "NSE:NIFTY 50"
    _VIX_SYMBOL   = "NSE:INDIA VIX"
    nifty_token = symbol_to_token.get(_NIFTY_SYMBOL)
    vix_token   = symbol_to_token.get(_VIX_SYMBOL)
    if not nifty_token:
        logger.warning("NIFTY 50 token not found — regime features will be unavailable")
    if not vix_token:
        logger.warning("INDIA VIX token not found — regime features will be unavailable")
```

#### 4b. After the watchlist `warm_up` loop — add regime warm-up

```python
    # Warm up regime index history so _nifty_close/_vix_close can be injected
    # into warm-up candles — lets the HMM regime model train from the first retrain.
    for regime_sym, regime_tok in ((_NIFTY_SYMBOL, nifty_token), (_VIX_SYMBOL, vix_token)):
        if regime_tok:
            warm_up(kite, store, regime_tok, regime_sym, config.candle_timeframe,
                    config.historical_cache_days)
```

#### 4c. Before the warmup strategy-feed loop — build timestamp→close maps

```python
    # Build timestamp→close maps for regime injection during warm-up
    _regime_ts_maps: dict[str, dict] = {}
    for regime_sym, key in ((_NIFTY_SYMBOL, "_nifty_close"), (_VIX_SYMBOL, "_vix_close")):
        df_r = store.read_candles(regime_sym, config.candle_timeframe, warmup_from, datetime.now())
        if not df_r.empty:
            _regime_ts_maps[key] = dict(zip(df_r["timestamp"], df_r["close"]))
            logger.info("Regime warm-up map built | %s | bars=%d", regime_sym, len(df_r))
        else:
            _regime_ts_maps[key] = {}
            logger.warning("No regime candles cached for %s — HMM warm-up skipped", regime_sym)
```

#### 4d. Inside the warmup candle loop (after `candle["instrument_token"] = ...`) — inject regime closes

```python
            ts = candle.get("timestamp")
            for key, ts_map in _regime_ts_maps.items():
                candle[key] = ts_map.get(ts)
```

#### 4e. Inside `pre_market()` — add regime refresh (after the watchlist warm_up loop)

```python
        for regime_sym, regime_tok in ((_NIFTY_SYMBOL, nifty_token), (_VIX_SYMBOL, vix_token)):
            if regime_tok:
                warm_up(kite, store, regime_tok, regime_sym, config.candle_timeframe,
                        config.historical_cache_days)
```

#### 4f. After `feed.subscribe(tokens)` — wire regime tokens to feed

```python
    feed.set_regime_tokens(nifty_token=nifty_token, vix_token=vix_token)
```

---

## Config changes (`config/config.yaml`)

Add under `strategies.lr_extrema` to enable HMM:

```yaml
    hmm_enabled: true
    hmm_lookback_days: 120    # days of Nifty history to train on

    # BB squeeze filter (optional, independent of HMM)
    # bb_squeeze_max_percentile: 75.0
```

---

## Notes

- **HMM is fail-open**: when `hmmlearn` is not installed, or fewer than 30 daily
  Nifty returns are in the buffer, `is_favourable()` returns `True` — entries are
  never blocked. Safe to enable on day 1.
- **Live mode caveat**: `_nifty_close` and `_vix_close` are only injected into
  live candles after `set_regime_tokens()` is wired (step 4f above). Before that,
  the HMM trains on empty data and stays fail-open.
- **BB squeeze filter** is independent of HMM — it only requires candle close
  prices and needs no external data. Enable separately with
  `bb_squeeze_max_percentile: 75.0`.
- **Backtest**: regime injection is handled by the backtest engine already (injects
  `_nifty_close`/`_vix_close` from cached NIFTY 50 / INDIA VIX candles). No engine
  changes are needed for HMM to work in backtest.
- **`hmmlearn` install on EC2**: `pip install hmmlearn>=0.3.0` works directly on
  Ubuntu. No system-level dependencies needed (unlike XGBoost which needs libomp on macOS).
