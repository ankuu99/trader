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
from trader.notifications import telegram
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
    signal_type: SignalType = SignalType.ENTRY


class RiskManager:
    def __init__(self):
        self._open_positions: dict[str, int] = {}     # instrument → filled quantity
        self._position_values: dict[str, float] = {}  # instrument → entry_price * qty
        self._capital_deployed: float = 0.0
        self._realised_pnl: float = 0.0
        self._halted: bool = False

    @property
    def capital_available(self) -> float:
        return max(0.0, config.total_capital - self._capital_deployed)

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

        # Cap quantity by available portfolio capital
        max_qty_by_available = int(self.capital_available // price)
        if quantity > max_qty_by_available:
            logger.info(
                "Quantity capped by available capital | %s | before=%d after=%d"
                " (available=%.0f)",
                signal.instrument, quantity, max_qty_by_available, self.capital_available,
            )
            quantity = max_qty_by_available

        if quantity <= 0:
            logger.warning(
                "Quantity is 0 for %s — price %.2f vs available capital %.0f",
                signal.instrument, price, self.capital_available,
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
            signal_type=signal.signal_type,
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
            signal_type=signal.signal_type,
        )

    def on_order_filled(self, instrument: str, fill_price: float, quantity: int):
        self._open_positions[instrument] = quantity
        deployed = fill_price * quantity
        self._position_values[instrument] = deployed
        self._capital_deployed += deployed
        logger.info(
            "Position opened | %s x%d @ %.2f | deployed=%.0f available=%.0f",
            instrument, quantity, fill_price,
            self._capital_deployed, self.capital_available,
        )

    def seed_from_kite(self, kite_positions: dict):
        """Seed position state from broker on startup to survive restarts (live mode only)."""
        for p in kite_positions.get("net", []):
            if p["quantity"] <= 0:
                continue
            instrument = f"NSE:{p['tradingsymbol']}"
            qty = p["quantity"]
            avg = float(p["average_price"])
            self._open_positions[instrument] = qty
            self._position_values[instrument] = avg * qty
            self._capital_deployed += avg * qty
            logger.info(
                "Seeded position from broker | %s x%d @ %.2f | deployed=%.0f",
                instrument, qty, avg, self._capital_deployed,
            )

    def is_halted(self) -> bool:
        return self._halted

    def realised_pnl(self) -> float:
        return self._realised_pnl

    def close_position(self, instrument: str, exit_price: float = 0.0):
        """Remove a position from tracking and accumulate realised P&L."""
        qty = self._open_positions.pop(instrument, None)
        freed = self._position_values.pop(instrument, 0.0)
        self._capital_deployed = max(0.0, self._capital_deployed - freed)
        if qty and exit_price and freed:
            entry_price = freed / qty
            pnl = (exit_price - entry_price) * qty
            self._realised_pnl += pnl
            logger.info(
                "Position closed | %s x%d | entry=%.2f exit=%.2f | trade_pnl=%.2f | daily_pnl=%.2f",
                instrument, qty, entry_price, exit_price, pnl, self._realised_pnl,
            )
            if not self._halted and self._realised_pnl <= -config.daily_loss_limit:
                self._halted = True
                logger.warning(
                    "Daily loss limit breached | daily_pnl=%.2f limit=%.2f — halting",
                    self._realised_pnl, config.daily_loss_limit,
                )
                telegram.notify_halt(self._realised_pnl, config.daily_loss_limit, config.env)

    def reset_day(self):
        self._realised_pnl = 0.0
        self._halted = False
        logger.info("Risk manager daily reset")
