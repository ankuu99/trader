"""
Risk Manager — validates signals before order placement.

Checks:
  1. Daily loss limit — halt if breached
  2. Max open positions
  3. Already in a position for this instrument
  4. SL cooldown — blocks re-entry after a hard stop-loss for a configurable period

Sizing: fixed % stop-loss, quantity = max_risk_per_trade / sl_distance
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

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
        self._pending_orders: dict[str, float] = {}   # instrument → expected cost (pre-fill lock)
        self._realised_pnl: float = 0.0
        self._cumulative_pnl: float = 0.0  # lifetime P&L — never resets; persisted to DB in live mode
        self._halted: bool = False
        self._last_reject_reason: str | None = None   # set whenever validate() returns None
        self._sl_cooldown: dict[str, datetime] = {}          # instrument → cooldown expiry (set after SL hit)
        self._pending_exit_reasons: dict[str, str] = {}      # instrument → exit_reason (set in _validate_exit, consumed in close_position)

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

        # SL cooldown — block re-entry for a period after a hard stop-loss
        now = datetime.now()
        until = self._sl_cooldown.get(signal.instrument)
        if until is not None:
            if now < until:
                logger.warning(
                    "Signal rejected — SL cooldown active | %s | until=%s",
                    signal.instrument, until.strftime("%Y-%m-%d %H:%M"),
                )
                self._last_reject_reason = "sl_cooldown"
                return None
            else:
                del self._sl_cooldown[signal.instrument]  # expired — clear it

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
        # Capture exit_reason so close_position() can apply SL cooldown without needing the param
        reason = getattr(signal, "exit_reason", None) or ""
        if reason:
            self._pending_exit_reasons[signal.instrument] = reason
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

    def close_position(self, instrument: str, exit_price: float = 0.0, exit_reason: str = ""):
        """Remove a position from tracking and accumulate realised P&L.

        exit_reason: pass explicitly (backtest engine) or omit to use the reason captured
        in _validate_exit() (live/paper mode). When "SL", applies the configured cooldown.
        """
        qty = self._open_positions.pop(instrument, None)
        freed = self._position_values.pop(instrument, 0.0)
        self._capital_deployed = max(0.0, self._capital_deployed - freed)

        # Resolve exit_reason — prefer explicit arg, fall back to what _validate_exit stored
        reason = exit_reason or self._pending_exit_reasons.pop(instrument, "")

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
                "Position closed | %s x%d | entry=%.2f exit=%.2f | trade_pnl=%.2f | daily_pnl=%.2f | reason=%s",
                instrument, qty, entry_price, exit_price, pnl, self._realised_pnl, reason or "?",
            )
            if not self._halted and self._realised_pnl <= -config.daily_loss_limit:
                self._halted = True
                logger.warning(
                    "Daily loss limit breached | daily_pnl=%.2f limit=%.2f — halting",
                    self._realised_pnl, config.daily_loss_limit,
                )
                telegram.notify_halt(self._realised_pnl, config.daily_loss_limit, config.env)

        # SL cooldown — block re-entry after a hard stop
        if reason == "SL":
            cooldown_bars = int(config._data.get("risk", {}).get("sl_cooldown_bars", 0))
            if cooldown_bars > 0:
                delta = self._bars_to_timedelta(cooldown_bars)
                until = datetime.now() + delta
                self._sl_cooldown[instrument] = until
                logger.info(
                    "SL cooldown set | %s | bars=%d | until=%s",
                    instrument, cooldown_bars, until.strftime("%Y-%m-%d %H:%M"),
                )

    def seed_sl_cooldown(self, instrument: str, expiry_ts: float) -> None:
        """Restore a persisted SL cooldown on startup (live mode only).

        expiry_ts: Unix timestamp (float) as stored in SQLite state table.
        Ignores already-expired entries so stale DB rows are harmless.
        """
        until = datetime.fromtimestamp(expiry_ts)
        if until > datetime.now():
            self._sl_cooldown[instrument] = until
            logger.info("Seeded SL cooldown | %s | until=%s", instrument, until.strftime("%Y-%m-%d %H:%M"))

    def _bars_to_timedelta(self, bars: int) -> timedelta:
        """Convert a bar count to a calendar timedelta.

        Uses config.candle_minutes and assumes a 6.5-hour trading day (375 minutes),
        then scales to calendar days (×7/5 for weekends).
        """
        bars_per_day = 375 / max(config.candle_minutes, 1)
        trading_days = bars / bars_per_day
        calendar_days = trading_days * (7 / 5)
        return timedelta(days=calendar_days)

    def reset_day(self):
        self._realised_pnl = 0.0
        self._halted = False
        logger.info("Risk manager daily reset")
        # SL cooldowns are multi-day — intentionally NOT reset here
