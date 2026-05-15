"""
Risk Manager — validates signals before order placement.

Checks:
  1. Daily loss limit — halt if breached
  2. Max open positions
  3. Already in a position for this instrument

Sizing: fixed % stop-loss, quantity = max_risk_per_trade / sl_distance
"""

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from trader.core.config import config

_IST = ZoneInfo("Asia/Kolkata")


# TODO: move _signal_time_ist to a shared trader/core/time_utils.py utility and
#       replace all other raw .time() calls on candle/tick timestamps throughout
#       the codebase (lr_extrema.py, live.py, etc.) with it for consistency.
def _signal_time_ist(ts) -> time | None:
    """Extract the time component of a timestamp, normalised to IST.

    Kite returns naive IST datetimes, but handles tz-aware datetimes safely
    by converting to IST before extracting .time(), preventing stale UTC
    comparisons if the data source ever changes.
    """
    if ts is None or not hasattr(ts, "time"):
        return None
    if getattr(ts, "tzinfo", None) is not None:
        ts = ts.astimezone(_IST)
    return ts.time()
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
        self._pending_orders: dict[str, float] = {}   # instrument → expected cost (pre-fill lock)
        self._realised_pnl: float = 0.0
        self._cumulative_pnl: float = 0.0  # lifetime P&L — never resets; persisted to DB in live mode
        self._halted: bool = False
        self._last_reject_reason: str | None = None   # set whenever validate() returns None

    @property
    def capital_available(self) -> float:
        pending = sum(self._pending_orders.values())
        return max(0.0, config.total_capital + self._cumulative_pnl - self._capital_deployed - pending)

    @property
    def cumulative_pnl(self) -> float:
        return self._cumulative_pnl

    def seed_cumulative_pnl(self, pnl: float) -> None:
        """Restore persisted cumulative P&L on startup (live mode only)."""
        self._cumulative_pnl = pnl
        logger.info("Seeded cumulative P&L | pnl=%.2f | effective_capital=%.0f",
                    pnl, config.total_capital + pnl)

    def validate(self, signal: Signal) -> Order | None:
        self._last_reject_reason = None
        if self._halted:
            if signal.signal_type == SignalType.EXIT:
                return self._validate_exit(signal)  # exits always allowed, even when halted
            logger.warning("Signal rejected — daily halt | %s", signal.instrument)
            self._last_reject_reason = "daily_halt"
            return None

        if signal.signal_type == SignalType.EXIT:
            return self._validate_exit(signal)

        if len(self._open_positions) + len(self._pending_orders) >= config.max_open_positions:
            logger.warning("Signal rejected — max open positions | %s", signal.instrument)
            self._last_reject_reason = "max_positions"
            return None

        if signal.instrument in self._open_positions:
            logger.warning("Signal rejected — already in position | %s", signal.instrument)
            self._last_reject_reason = "already_in_position"
            return None

        if signal.instrument in self._pending_orders:
            logger.warning("Signal rejected — pending order already exists | %s", signal.instrument)
            self._last_reject_reason = "pending_order_exists"
            return None

        candle_time = _signal_time_ist(signal.timestamp)
        if candle_time is not None and not (config.trading_start <= candle_time <= config.trading_end):
            logger.debug(
                "Signal rejected — outside trading window | %s | %s not in [%s, %s]",
                signal.instrument, candle_time, config.trading_start, config.trading_end,
            )
            self._last_reject_reason = "outside_trading_window"
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
            self._last_reject_reason = "sl_distance_zero"
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
            self._last_reject_reason = "quantity_zero"
            return None

        if signal.target_price is not None:
            target_price = round(signal.target_price, 2)
        else:
            target_price = round(price + sl_distance * config.risk_reward, 2)

        expected_cost = price * quantity
        self._pending_orders[signal.instrument] = expected_cost
        logger.info(
            "Signal approved | %s x%d @ ~%.2f SL=%.2f target=%.2f (RR=%.1f) | pending_lock=%.0f",
            signal.instrument, quantity, price, sl_price, target_price, config.risk_reward,
            expected_cost,
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

    def on_order_cancelled(self, instrument: str):
        """Release capital locked for a pending order that was cancelled or rejected."""
        released = self._pending_orders.pop(instrument, None)
        if released is not None:
            logger.info(
                "Pending capital released | %s | ₹%.0f | available=%.0f",
                instrument, released, self.capital_available,
            )

    def on_order_filled(self, instrument: str, fill_price: float, quantity: int):
        self._pending_orders.pop(instrument, None)  # release pending lock, fill takes over
        if fill_price <= 0:
            logger.error(
                "BUY fill with price=0 for %s qty=%d — skipping capital tracking",
                instrument, quantity,
            )
            return
        self._open_positions[instrument] = quantity
        deployed = fill_price * quantity
        self._position_values[instrument] = deployed
        self._capital_deployed += deployed
        logger.info(
            "Position opened | %s x%d @ %.2f | deployed=%.0f available=%.0f",
            instrument, quantity, fill_price,
            self._capital_deployed, self.capital_available,
        )

    def seed_position(self, instrument: str, qty: int, avg_price: float):
        """Seed a single position into risk state (called from startup reconciliation)."""
        self._open_positions[instrument] = qty
        self._position_values[instrument] = avg_price * qty
        self._capital_deployed += avg_price * qty
        logger.info(
            "Seeded position | %s x%d @ %.2f | deployed=%.0f",
            instrument, qty, avg_price, self._capital_deployed,
        )

    def seed_pending_order(self, instrument: str, estimated_cost: float):
        """Re-lock capital for a BUY order that was pending when the bot restarted."""
        self._pending_orders[instrument] = estimated_cost
        logger.info(
            "Seeded pending order | %s | estimated_cost=%.0f | available=%.0f",
            instrument, estimated_cost, self.capital_available,
        )

    def seed_realised_pnl(self, pnl: float):
        """Seed today's already-realised P&L on startup (e.g. GTT fired while system was down)."""
        if pnl == 0.0:
            return
        self._realised_pnl = pnl
        logger.info("Seeded realised P&L from broker | pnl=%.2f", pnl)
        if not self._halted and self._realised_pnl <= -config.daily_loss_limit:
            self._halted = True
            logger.warning(
                "Halt triggered from seeded P&L on startup | pnl=%.2f limit=%.2f",
                self._realised_pnl, config.daily_loss_limit,
            )
            telegram.notify_halt(self._realised_pnl, config.daily_loss_limit, config.env)

    def is_halted(self) -> bool:
        return self._halted

    def realised_pnl(self) -> float:
        return self._realised_pnl

    def close_position(self, instrument: str, exit_price: float = 0.0):
        """Remove a position from tracking and accumulate realised P&L."""
        qty = self._open_positions.pop(instrument, None)
        freed = self._position_values.pop(instrument, 0.0)
        self._capital_deployed = max(0.0, self._capital_deployed - freed)
        if qty and freed and not exit_price:
            logger.warning(
                "close_position called with exit_price=0 for %s — P&L and halt check skipped",
                instrument,
            )
        if qty and exit_price and freed:
            entry_price = freed / qty
            pnl = (exit_price - entry_price) * qty
            self._realised_pnl += pnl
            self._cumulative_pnl += pnl
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
