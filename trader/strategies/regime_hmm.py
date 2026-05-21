"""
Gaussian HMM market regime filter.

Trains on daily Nifty 50 returns extracted from _nifty_close values injected
into candle dicts by the backtest engine (and live feed, when wired).

Two hidden states are learned:
  - Favourable  : low-variance state — calm, trending market; LR entries are reliable
  - Unfavourable: high-variance state — choppy, volatile market; LR entries degrade

Key design: RegimeHMM maintains a persistent accumulator of Nifty daily closes across
all fit() calls. This means history grows over the full backtest period rather than
being capped by the strategy's short candle deque (~47 trading days at 15-min).
The HMM becomes meaningful after ~30 unique days and improves as history grows.

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
    """2-state Gaussian HMM trained on daily Nifty 50 returns.

    Maintains a persistent accumulator of daily closes so history grows across
    retrains. Call fit() on every strategy retrain cycle; call is_favourable()
    before emitting an entry signal.
    """

    def __init__(self, n_states: int = 2, lookback_days: int = 500):
        self._n_states = n_states
        self._lookback_days = lookback_days
        self._model: "_GaussianHMM | None" = None
        self._favourable_state: int | None = None
        self._current_state: int | None = None
        self._fitted: bool = False
        # Persistent accumulator: date_str → daily close (last candle of each day wins).
        # Grows across all fit() calls — not capped by the strategy's candle deque size.
        self._daily_closes: dict[str, float] = {}

    def fit(self, candles: list[dict]) -> bool:
        """Merge new daily closes from candles into accumulator, then refit the HMM.

        Extracts one close per calendar day (last candle of each day), accumulates
        into a persistent dict, computes daily % returns, and fits a GaussianHMM.
        The low-variance state is labelled as favourable. Returns True on success.
        """
        if not _HMMLEARN_AVAILABLE:
            logger.warning("RegimeHMM | hmmlearn not installed — regime gate disabled")
            return False

        # Merge new daily closes into the persistent accumulator
        for c in candles:
            nifty = c.get("_nifty_close")
            ts = c.get("timestamp")
            if nifty is None or ts is None:
                continue
            self._daily_closes[ts.date().isoformat()] = nifty

        # Use the last lookback_days from accumulated history
        dates = sorted(self._daily_closes)[-self._lookback_days - 1:]
        if len(dates) < _MIN_DAILY_OBS + 1:
            logger.debug(
                "RegimeHMM | not enough daily obs (%d < %d) — skipping fit",
                len(dates) - 1, _MIN_DAILY_OBS,
            )
            return False

        closes = [self._daily_closes[d] for d in dates]
        returns = np.array(
            [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))],
            dtype=float,
        ).reshape(-1, 1)

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

        # State with lowest variance = calmest = favourable
        variances = [float(model.covars_[s][0][0]) for s in range(self._n_states)]
        self._favourable_state = int(np.argmin(variances))
        self._current_state = int(model.predict(returns)[-1])
        self._model = model
        self._fitted = True

        logger.info(
            "RegimeHMM fitted | states=%d | favourable=%d | current=%d | "
            "variances=%s | daily_obs=%d (accumulated=%d)",
            self._n_states,
            self._favourable_state,
            self._current_state,
            [f"{v:.2e}" for v in variances],
            len(returns),
            len(self._daily_closes),
        )
        return True

    def is_favourable(self) -> bool:
        """Return True when the current regime is good for entries.

        Fail-open: returns True when the model is not fitted so warmup and
        data-starved runs are not penalised.
        """
        if not self._fitted or self._current_state is None:
            return True
        return self._current_state == self._favourable_state
