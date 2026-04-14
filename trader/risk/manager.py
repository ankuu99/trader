"""
Risk Manager — the single gatekeeper between strategy signals and order placement.

Checks performed on every signal before an order is allowed through:
  1. Daily loss limit — halt all new entries if breached
  2. Weekly loss limit — halt new entries if weekly limit breached (resets Monday)
  3. Regime filter — halt new entries when market regime is unfavourable (NIFTY < 200 DMA)
  4. Max open positions — reject new entries if at the limit
  5. Position sizing — ATR-based or risk/SL-distance formula (config-driven)
  6. Stop-loss price — calculated from ATR or a fixed % fallback

Also responsible for:
  - Tracking realised P&L (daily and weekly)
  - Optionally logging every signal decision to SQLite via an injected callable
"""

from dataclasses import dataclass
from datetime import datetime

from trader.core.config import config
from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType

logger = get_logger(__name__)



@dataclass
class Order:
    """Validated, ready-to-place order produced by the risk manager."""
    instrument: str
    direction: Direction
    signal_type: SignalType
    quantity: int
    price_hint: float        # indicative entry price
    stop_loss: float         # mandatory SL price
    strategy: str
    mode: str                # "live" or "paper"
    target_price: float | None = None  # for GTT OCO (live) and candle HIGH check (backtest)


class RiskManager:
    def __init__(self, signal_logger=None):
        """
        Args:
            signal_logger: optional callable for signal audit logging.
                Signature: (timestamp, instrument, strategy, direction, signal_type,
                            price_hint, accepted, reject_reason)
                Pass store.log_signal to persist signal decisions to SQLite.
        """
        self._open_positions: dict[str, Direction] = {}
        self._realised_pnl: float = 0.0
        self._weekly_realised_pnl: float = 0.0
        self._entry_prices: dict[str, float] = {}
        self._entry_quantities: dict[str, int] = {}
        self._halted: bool = False
        self._weekly_halted: bool = False
        self._regime_allowed: bool = True
        self._mode: str = config.env
        self._signal_logger = signal_logger

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def validate(self, signal: Signal, atr: float | None = None) -> Order | None:
        """
        Validate a strategy signal against all risk rules.
        Returns an Order if the signal passes all checks, else None.
        Logs the outcome to the signal logger if one was provided.
        """
        if signal.signal_type == SignalType.ENTRY:
            order = self._validate_entry(signal, atr)
        else:
            order = self._validate_exit(signal)

        if self._signal_logger is not None:
            try:
                self._signal_logger(
                    timestamp=datetime.now(),
                    instrument=signal.instrument,
                    strategy=signal.strategy or "",
                    direction=signal.direction.value,
                    signal_type=signal.signal_type.value,
                    price_hint=signal.price_hint,
                    accepted=order is not None,
                    reject_reason=None,
                )
            except Exception as e:
                logger.debug("Signal logging failed: %s", e)

        return order

    def on_order_filled(self, instrument: str, direction: Direction,
                        quantity: int, fill_price: float, signal_type: SignalType):
        """Called by order manager when an order is confirmed filled."""
        if signal_type == SignalType.ENTRY:
            self._open_positions[instrument] = direction
            self._entry_prices[instrument] = fill_price
            self._entry_quantities[instrument] = quantity
            logger.info(
                "Position opened | %s %s x%d @ %.2f",
                direction.value, instrument, quantity, fill_price,
            )
        elif signal_type == SignalType.EXIT:
            entry_price = self._entry_prices.pop(instrument, fill_price)
            quantity = self._entry_quantities.pop(instrument, quantity)
            direction = self._open_positions.pop(instrument, direction)

            pnl = self._calc_pnl(direction, entry_price, fill_price, quantity)
            self._realised_pnl += pnl
            self._weekly_realised_pnl += pnl
            logger.info(
                "Position closed | %s x%d | entry=%.2f exit=%.2f pnl=%.2f"
                " | day_pnl=%.2f | week_pnl=%.2f",
                instrument, quantity, entry_price, fill_price, pnl,
                self._realised_pnl, self._weekly_realised_pnl,
            )

            if self._realised_pnl <= -config.daily_loss_limit:
                self._halted = True
                logger.warning(
                    "Daily loss limit breached (%.2f). Trading halted for the day.",
                    self._realised_pnl,
                )

            weekly_limit = config.weekly_loss_limit
            if weekly_limit > 0 and self._weekly_realised_pnl <= -weekly_limit:
                self._weekly_halted = True
                logger.warning(
                    "Weekly loss limit breached (%.2f). Trading halted for the week.",
                    self._weekly_realised_pnl,
                )

    def update_regime(self, allowed: bool):
        """
        Update the regime state used by the entry gate.
        Call this after computing NIFTY 200 DMA — pass False to block new entries.
        Has no effect when regime_filter is disabled in config.
        """
        if self._regime_allowed != allowed:
            logger.info(
                "Regime state updated: new entries %s",
                "ALLOWED" if allowed else "BLOCKED",
            )
        self._regime_allowed = allowed

    def is_halted(self) -> bool:
        return self._halted

    def is_weekly_halted(self) -> bool:
        return self._weekly_halted

    def open_position_count(self) -> int:
        return len(self._open_positions)

    def realised_pnl(self) -> float:
        return self._realised_pnl

    def weekly_realised_pnl(self) -> float:
        return self._weekly_realised_pnl

    def reset_day(self, is_monday: bool = False):
        """
        Reset daily P&L counter and halt flag. Positions are preserved.
        Pass is_monday=True to also reset the weekly circuit breaker.
        """
        self._realised_pnl = 0.0
        self._halted = False
        if is_monday:
            self._weekly_realised_pnl = 0.0
            self._weekly_halted = False
            logger.info("Risk manager daily + weekly P&L reset (Monday)")
        else:
            logger.info("Risk manager daily P&L reset")

    def reset_positions(self):
        """Clear all tracked open positions."""
        self._open_positions.clear()
        self._entry_prices.clear()
        self._entry_quantities.clear()
        logger.info("Risk manager positions cleared")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _validate_entry(self, signal: Signal, atr: float | None) -> Order | None:
        if self._halted:
            logger.warning(
                "Signal rejected — daily loss limit. | %s", signal.instrument
            )
            return None

        if config.weekly_loss_limit > 0 and self._weekly_halted:
            logger.warning(
                "Signal rejected — weekly loss limit. | %s", signal.instrument
            )
            return None

        if config.regime_filter_enabled and not self._regime_allowed:
            logger.warning(
                "Signal rejected — regime filter: market unfavourable. | %s",
                signal.instrument,
            )
            return None

        if self.open_position_count() >= config.max_open_positions:
            logger.warning(
                "Signal rejected — max open positions (%d) reached. | %s",
                config.max_open_positions, signal.instrument,
            )
            return None

        if signal.instrument in self._open_positions:
            logger.warning(
                "Signal rejected — already in a position for %s", signal.instrument
            )
            return None

        stop_loss = self._calc_stop_loss(signal, atr)
        sl_distance = abs(signal.price_hint - stop_loss)

        if sl_distance <= 0:
            logger.error(
                "SL distance is zero for %s — rejecting signal", signal.instrument
            )
            return None

        quantity = self._calc_quantity(sl_distance, atr=atr, price=signal.price_hint)

        if quantity <= 0:
            logger.warning(
                "Calculated quantity is 0 for %s — rejecting signal", signal.instrument
            )
            return None

        order = Order(
            instrument=signal.instrument,
            direction=signal.direction,
            signal_type=SignalType.ENTRY,
            quantity=quantity,
            price_hint=signal.price_hint,
            stop_loss=stop_loss,
            strategy=signal.strategy,
            mode=self._mode,
            target_price=signal.target_price,
        )
        logger.info(
            "Signal approved | %s %s x%d @ ~%.2f SL=%.2f",
            signal.direction.value, signal.instrument,
            quantity, signal.price_hint, stop_loss,
        )
        return order

    def _validate_exit(self, signal: Signal) -> Order | None:
        if signal.instrument not in self._open_positions:
            logger.warning(
                "Exit signal ignored — no open position for %s", signal.instrument
            )
            return None

        qty = self._entry_quantities.get(signal.instrument, 1)
        return Order(
            instrument=signal.instrument,
            direction=signal.direction,
            signal_type=SignalType.EXIT,
            quantity=qty,
            price_hint=signal.price_hint,
            stop_loss=0.0,
            strategy=signal.strategy,
            mode=self._mode,
        )

    def _calc_stop_loss(self, signal: Signal, atr: float | None) -> float:
        price = signal.price_hint
        sl_distance = atr if atr else price * config.default_sl_pct / 100
        if signal.direction == Direction.BUY:
            return round(price - sl_distance, 2)
        else:
            return round(price + sl_distance, 2)

    def _calc_quantity(
        self, sl_distance: float, atr: float | None = None, price: float = 0.0
    ) -> int:
        """
        Compute position size.

        When atr_based sizing is enabled in config and ATR is available:
            qty = risk_amount / (atr_multiplier × ATR)
        Otherwise:
            qty = max_risk_per_trade / sl_distance

        In both cases, qty is then capped at max_position_pct of total capital.
        """
        if atr and config.atr_sizing_enabled:
            risk_amount = config.total_capital * config.max_risk_per_trade_pct / 100
            qty = int(risk_amount / (config.atr_sizing_multiplier * atr))
        else:
            qty = int(config.max_risk_per_trade // sl_distance)

        # Apply max_position_pct cap regardless of sizing method
        if price > 0 and config.max_position_pct > 0:
            cap_qty = int(config.total_capital * config.max_position_pct / 100 / price)
            qty = min(qty, cap_qty)

        return qty

    @staticmethod
    def _calc_pnl(direction: Direction, entry: float, exit_price: float, qty: int) -> float:
        if direction == Direction.BUY:
            return (exit_price - entry) * qty
        else:
            return (entry - exit_price) * qty
