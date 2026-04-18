"""
Risk Manager — validates signals before order placement.

Checks:
  1. Daily loss limit — halt if breached
  2. Max open positions
  3. Already in a position for this instrument

Sizing: fixed % stop-loss, quantity = max_risk_per_trade / sl_distance
"""

from dataclasses import dataclass

from trader.core.config import config
from trader.core.logger import get_logger
from trader.strategies.base import Direction, Signal, SignalType

logger = get_logger(__name__)


@dataclass
class Order:
    instrument: str
    direction: Direction
    quantity: int
    price_hint: float
    stop_loss: float
    target_price: float
    strategy: str
    mode: str


class RiskManager:
    def __init__(self):
        self._open_positions: dict[str, int] = {}   # instrument → filled quantity
        self._realised_pnl: float = 0.0
        self._halted: bool = False

    def validate(self, signal: Signal) -> Order | None:
        if self._halted:
            logger.warning("Signal rejected — daily halt | %s", signal.instrument)
            return None

        if signal.signal_type == SignalType.EXIT:
            return self._validate_exit(signal)

        if len(self._open_positions) >= config.max_open_positions:
            logger.warning("Signal rejected — max open positions | %s", signal.instrument)
            return None

        if signal.instrument in self._open_positions:
            logger.warning("Signal rejected — already in position | %s", signal.instrument)
            return None

        price = signal.price_hint

        # Use signal-supplied levels if provided (e.g. strategy-driven GTT safety nets),
        # otherwise fall back to config defaults.
        if signal.stop_loss_hint is not None:
            sl_price = round(signal.stop_loss_hint, 2)
        else:
            sl_price = round(price * (1 - config.default_sl_pct / 100), 2)

        sl_distance = price - sl_price

        if sl_distance <= 0:
            logger.error("SL distance is zero for %s", signal.instrument)
            return None

        quantity = int(config.max_risk_per_trade // sl_distance)

        # Cap quantity so total capital deployed doesn't exceed max_capital_per_stock
        max_qty_by_capital = int(config.max_capital_per_stock // price)
        if quantity > max_qty_by_capital:
            logger.info(
                "Quantity capped by capital limit | %s | risk-based=%d capped=%d"
                " (max_capital=%.0f @ %.2f)",
                signal.instrument, quantity, max_qty_by_capital,
                config.max_capital_per_stock, price,
            )
            quantity = max_qty_by_capital

        if quantity <= 0:
            logger.warning(
                "Quantity is 0 for %s — price %.2f exceeds max capital per stock %.0f",
                signal.instrument, price, config.max_capital_per_stock,
            )
            return None

        if signal.target_price is not None:
            target_price = round(signal.target_price, 2)
        else:
            target_price = round(price + sl_distance * config.risk_reward, 2)

        logger.info(
            "Signal approved | %s x%d @ ~%.2f SL=%.2f target=%.2f (RR=%.1f)",
            signal.instrument, quantity, price, sl_price, target_price, config.risk_reward,
        )
        return Order(
            instrument=signal.instrument,
            direction=signal.direction,
            quantity=quantity,
            price_hint=price,
            stop_loss=sl_price,
            target_price=target_price,
            strategy=signal.strategy,
            mode=config.env,
        )

    def _validate_exit(self, signal: Signal) -> Order | None:
        """Return a SELL order to close an open position."""
        quantity = self._open_positions.get(signal.instrument, 0)
        if quantity <= 0:
            logger.warning("Exit signal for instrument not in positions | %s", signal.instrument)
            return None
        logger.info("Exit approved | %s x%d @ ~%.2f", signal.instrument, quantity, signal.price_hint)
        return Order(
            instrument=signal.instrument,
            direction=Direction.SELL,
            quantity=quantity,
            price_hint=signal.price_hint,
            stop_loss=0.0,
            target_price=0.0,
            strategy=signal.strategy,
            mode=config.env,
        )

    def on_order_filled(self, instrument: str, fill_price: float, quantity: int):
        self._open_positions[instrument] = quantity
        logger.info("Position opened | %s x%d @ %.2f", instrument, quantity, fill_price)

    def is_halted(self) -> bool:
        return self._halted

    def realised_pnl(self) -> float:
        return self._realised_pnl

    def close_position(self, instrument: str):
        """Remove a position from tracking (called when SL/exit is confirmed)."""
        self._open_positions.pop(instrument, None)

    def reset_day(self):
        self._realised_pnl = 0.0
        self._halted = False
        logger.info("Risk manager daily reset")
