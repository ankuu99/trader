"""
Order Manager — places, tracks, and logs all orders.

In live mode  : calls Kite REST API to place real orders.
In paper mode : simulates fills at the next candle's open price.

The order manager never makes risk decisions — it only executes
what the risk manager has already approved.
"""

import uuid
from datetime import datetime
from typing import Callable

from kiteconnect import KiteConnect

from trader.core.config import config
from trader.core.logger import get_logger
from trader.data.store import Store
from trader.risk.manager import Order
from trader.strategies.base import Direction, SignalType

logger = get_logger(__name__)

# Kite product and order type constants
_ORDER_MARKET = "MARKET"
_ORDER_SL = "SL-M"
_EXCHANGE = "NSE"

# Callback type: called when an order status changes
OrderUpdateCallback = Callable[[dict], None]


class OrderManager:
    def __init__(self, kite: KiteConnect, store: Store, mode: str):
        """
        Args:
            kite  : authenticated KiteConnect instance
            store : Store for persisting order records
            mode  : "live" or "paper"
        """
        self._kite = kite
        self._store = store
        self._mode = mode
        self._callbacks: list[OrderUpdateCallback] = []

        # Paper mode: pending fills waiting for next candle open
        # { order_id: Order }
        self._pending_paper: dict[str, Order] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def register_update_callback(self, cb: OrderUpdateCallback):
        """Register a function to call when any order status changes."""
        self._callbacks.append(cb)

    def place(self, order: Order) -> str:
        """
        Place an entry or exit order.
        Returns an order_id string.
        """
        if self._mode == "paper":
            return self._place_paper(order)
        return self._place_live(order)

    def on_candle(self, candle: dict):
        """
        Called on each new candle.
        In paper mode, fills pending orders for this instrument at the candle's open price.
        instrument must be the resolved symbol string (e.g. "NSE:INDHOTEL").
        """
        if self._mode == "paper":
            self._fill_pending_paper(candle["open"], instrument=candle.get("_symbol"))

    def on_kite_order_update(self, update: dict):
        """
        Called by KiteTicker when Kite pushes an order status update.
        Only relevant in live mode.
        """
        order_id = update.get("order_id")
        status = update.get("status")
        if not order_id:
            return

        record = {
            "order_id": order_id,
            "status": status,
            "instrument": update.get("tradingsymbol", ""),
            "order_type": update.get("order_type", ""),
            "product": update.get("product", ""),
            "direction": update.get("transaction_type", ""),
            "quantity": update.get("quantity", 0),
            "price": update.get("average_price"),
            "trigger_price": update.get("trigger_price"),
            "mode": "live",
        }
        self._store.upsert_order(record)
        logger.info("Order update | %s | %s", order_id, status)
        self._dispatch(record)

    # ------------------------------------------------------------------ #
    # Live order placement                                                 #
    # ------------------------------------------------------------------ #

    def _place_live(self, order: Order) -> str:
        symbol = order.instrument.split(":")[-1]  # "NSE:RELIANCE" → "RELIANCE"
        transaction = order.direction.value       # "BUY" or "SELL"

        try:
            # Primary order — market
            order_id = self._kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=_EXCHANGE,
                tradingsymbol=symbol,
                transaction_type=transaction,
                quantity=order.quantity,
                product=config.product,
                order_type=_ORDER_MARKET,
            )

            record = {
                "order_id": str(order_id),
                "instrument": order.instrument,
                "order_type": _ORDER_MARKET,
                "product": config.product,
                "direction": transaction,
                "quantity": order.quantity,
                "price": None,
                "trigger_price": None,
                "status": "PENDING",
                "mode": "live",
                "signal_type": order.signal_type.value,
            }
            self._store.upsert_order(record)
            logger.info(
                "Live order placed | %s %s x%d | id=%s",
                transaction, order.instrument, order.quantity, order_id,
            )

            # Place SL order for entry orders
            if order.signal_type == SignalType.ENTRY and order.stop_loss > 0:
                self._place_live_sl(order, symbol)

            return str(order_id)

        except Exception as e:
            logger.error("Failed to place live order for %s: %s", order.instrument, e)
            raise

    def _place_live_sl(self, order: Order, symbol: str):
        sl_transaction = "SELL" if order.direction == Direction.BUY else "BUY"
        try:
            sl_id = self._kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=_EXCHANGE,
                tradingsymbol=symbol,
                transaction_type=sl_transaction,
                quantity=order.quantity,
                product=config.product,
                order_type=_ORDER_SL,
                trigger_price=order.stop_loss,
            )
            logger.info(
                "SL order placed | %s x%d @ trigger=%.2f | id=%s",
                symbol, order.quantity, order.stop_loss, sl_id,
            )
        except Exception as e:
            logger.error("Failed to place SL order for %s: %s", symbol, e)

    # ------------------------------------------------------------------ #
    # Paper order simulation                                               #
    # ------------------------------------------------------------------ #

    def _place_paper(self, order: Order) -> str:
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        self._pending_paper[order_id] = order

        record = {
            "order_id": order_id,
            "instrument": order.instrument,
            "order_type": _ORDER_MARKET,
            "product": config.product,
            "direction": order.direction.value,
            "quantity": order.quantity,
            "price": None,
            "trigger_price": None,
            "status": "PENDING",
            "mode": "paper",
            "signal_type": order.signal_type.value,
        }
        self._store.upsert_order(record)
        logger.info(
            "Paper order queued | %s %s x%d | id=%s | signal_price=%.2f SL=%.2f",
            order.direction.value, order.instrument,
            order.quantity, order_id, order.price_hint, order.stop_loss,
        )
        return order_id

    def _fill_pending_paper(self, open_price: float, instrument: str | None = None):
        """Fill pending paper orders at the given open price.
        If instrument is provided, only fills orders for that instrument.
        """
        for order_id, order in list(self._pending_paper.items()):
            if instrument and order.instrument != instrument:
                continue
            fill_price = open_price
            record = {
                "order_id": order_id,
                "instrument": order.instrument,
                "order_type": _ORDER_MARKET,
                "product": config.product,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "price": fill_price,
                "trigger_price": None,
                "status": "COMPLETE",
                "mode": "paper",
                "signal_type": order.signal_type.value,
            }
            self._store.upsert_order(record)

            trade = {
                "trade_id": f"T-{order_id}",
                "order_id": order_id,
                "instrument": order.instrument,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "price": fill_price,
                "traded_at": datetime.now().isoformat(),
            }
            self._store.write_trade(trade)

            slippage = fill_price - order.price_hint
            if abs(slippage) > order.price_hint * 0.02:  # warn if >2% slippage
                logger.warning(
                    "Paper fill SLIPPAGE | %s | signal=%.2f fill=%.2f diff=%.2f (%.1f%%)",
                    order.instrument, order.price_hint, fill_price,
                    slippage, slippage / order.price_hint * 100,
                )
            logger.info(
                "Paper fill | %s %s x%d @ %.2f (signal was %.2f) | id=%s",
                order.direction.value, order.instrument,
                order.quantity, fill_price, order.price_hint, order_id,
            )
            del self._pending_paper[order_id]
            self._dispatch({**record, "fill_price": fill_price})

    def _dispatch(self, update: dict):
        for cb in self._callbacks:
            try:
                cb(update)
            except Exception:
                logger.exception("Error in order update callback")
