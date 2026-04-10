"""
Risk Manager — the single gatekeeper between strategy signals and order placement.

Checks performed on every signal before an order is allowed through:
  1. Daily loss limit — halt all new entries if breached
  2. Max open positions — reject new entries if at the limit
  3. Position sizing — compute quantity based on risk per trade and SL distance
  4. Stop-loss price — calculated from ATR or a fixed % fallback

Also responsible for:
  - Tracking realised and unrealised P&L
  - Triggering square-off of all positions at the configured time
"""

from dataclasses import dataclass
from datetime import datetime, time

from trader.core.config import config
from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType

logger = get_logger(__name__)

# Default SL as % of price when ATR is not available
_DEFAULT_SL_PCT = 0.01  # 1%


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


class RiskManager:
    def __init__(self):
        self._open_positions: dict[str, Direction] = {}  # instrument → direction
        self._realised_pnl: float = 0.0
        self._entry_prices: dict[str, float] = {}        # instrument → entry price
        self._entry_quantities: dict[str, int] = {}      # instrument → quantity
        self._halted: bool = False
        self._mode: str = config.env                     # "paper" or "live"

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def validate(self, signal: Signal, atr: float | None = None) -> Order | None:
        """
        Validate a strategy signal against all risk rules.

        Returns an Order if the signal passes all checks, else None.
        Logs the reason for every rejection.
        """
        if signal.signal_type == SignalType.ENTRY:
            return self._validate_entry(signal, atr)
        else:
            return self._validate_exit(signal)

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
            logger.info(
                "Position closed | %s x%d | entry=%.2f exit=%.2f pnl=%.2f | day_pnl=%.2f",
                instrument, quantity, entry_price, fill_price, pnl, self._realised_pnl,
            )

            # Re-check daily loss limit after realising a loss
            if self._realised_pnl <= -config.daily_loss_limit:
                self._halted = True
                logger.warning(
                    "Daily loss limit breached (%.2f). Trading halted for the day.",
                    self._realised_pnl,
                )

    def square_off_all(self) -> list[Order]:
        """
        Generate EXIT orders for all open positions.
        Called at the configured square-off time (default 3:15 PM).
        """
        orders = []
        for instrument, direction in list(self._open_positions.items()):
            exit_direction = Direction.SELL if direction == Direction.BUY else Direction.BUY
            qty = self._entry_quantities.get(instrument, 1)
            entry_price = self._entry_prices.get(instrument, 0)
            orders.append(Order(
                instrument=instrument,
                direction=exit_direction,
                signal_type=SignalType.EXIT,
                quantity=qty,
                price_hint=entry_price,
                stop_loss=0.0,    # no SL needed on forced square-off
                strategy="square_off",
                mode=self._mode,
            ))
            logger.info("Square-off order generated for %s", instrument)
        return orders

    def is_halted(self) -> bool:
        return self._halted

    def open_position_count(self) -> int:
        return len(self._open_positions)

    def realised_pnl(self) -> float:
        return self._realised_pnl

    def reset_day(self):
        """Reset daily P&L counters and halt flag. Positions are preserved."""
        self._realised_pnl = 0.0
        self._halted = False
        logger.info("Risk manager daily P&L reset")

    def reset_positions(self):
        """Clear all tracked open positions. Call at intraday session end."""
        self._open_positions.clear()
        self._entry_prices.clear()
        self._entry_quantities.clear()
        logger.info("Risk manager positions cleared")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _validate_entry(self, signal: Signal, atr: float | None) -> Order | None:
        if self._halted:
            logger.warning("Signal rejected — trading halted (daily loss limit). | %s", signal.instrument)
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
            logger.error("SL distance is zero for %s — rejecting signal", signal.instrument)
            return None

        quantity = self._calc_quantity(sl_distance)

        if quantity <= 0:
            logger.warning("Calculated quantity is 0 for %s — rejecting signal", signal.instrument)
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
        sl_distance = atr if atr else price * _DEFAULT_SL_PCT
        if signal.direction == Direction.BUY:
            return round(price - sl_distance, 2)
        else:
            return round(price + sl_distance, 2)

    def _calc_quantity(self, sl_distance: float) -> int:
        """How many shares can we buy such that max loss <= max_risk_per_trade."""
        return int(config.max_risk_per_trade // sl_distance)

    @staticmethod
    def _calc_pnl(direction: Direction, entry: float, exit_price: float, qty: int) -> float:
        if direction == Direction.BUY:
            return (exit_price - entry) * qty
        else:
            return (entry - exit_price) * qty


def should_square_off(now: datetime | None = None) -> bool:
    """Returns True if it is at or past the configured square-off time."""
    t = (now or datetime.now()).time()
    h, m = config.square_off_time.split(":")
    return t >= time(int(h), int(m))
