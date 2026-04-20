"""
Order Manager — places and tracks orders.

Live mode : places a market order via Kite, then a GTT stop-loss.
Paper mode: queues a pending fill; executes at the next candle's open price.
"""

import uuid
from datetime import datetime
from typing import Callable

from kiteconnect import KiteConnect

from trader.core.config import config
from trader.core.logger import get_logger
from trader.data.store import Store
from trader.strategies.base import Direction
from trader.risk.manager import Order

logger = get_logger(__name__)

OrderUpdateCallback = Callable[[dict], None]

_EXCHANGE = "NSE"


class OrderManager:
    def __init__(self, kite: KiteConnect, store: Store, mode: str):
        self._kite = kite
        self._store = store
        self._mode = mode
        self._callbacks: list[OrderUpdateCallback] = []
        # Paper mode: { order_id: Order } waiting for next candle open
        self._pending_paper: dict[str, Order] = {}
        # Live mode: { order_id: Order } so we can enrich Kite's postback
        self._live_orders: dict[str, Order] = {}
        # Live mode: { instrument: gtt_trigger_id } for cancellation on exit
        self._gtt_ids: dict[str, int] = {}
        # Live mode: { instrument: Order } so GTT fills can recover strategy context
        self._instrument_orders: dict[str, Order] = {}

    def register_update_callback(self, cb: OrderUpdateCallback):
        self._callbacks.append(cb)

    def place(self, order: Order) -> str:
        if self._mode == "paper":
            return self._place_paper(order)
        return self._place_live(order)

    def on_candle(self, candle: dict):
        """Fill pending paper orders at this candle's open price."""
        if self._mode != "paper" or not self._pending_paper:
            return
        symbol = candle.get("_symbol")
        fill_price = candle["open"]
        to_fill = [
            (oid, o) for oid, o in self._pending_paper.items()
            if o.instrument == symbol
        ]
        for order_id, order in to_fill:
            del self._pending_paper[order_id]
            record = {
                "order_id": order_id,
                "instrument": order.instrument,
                "order_type": "MARKET",
                "product": config.product,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "price": fill_price,
                "trigger_price": order.stop_loss,
                "status": "COMPLETE",
                "mode": "paper",
                "strategy": order.strategy,
            }
            self._store.upsert_order(record)
            logger.info(
                "Paper fill | %s x%d @ %.2f | strategy=%s",
                order.instrument, order.quantity, fill_price, order.strategy,
            )
            self._dispatch({**record, "fill_price": fill_price,
                            "signal_type": order.signal_type,
                            "target_price": order.target_price})

    def on_kite_order_update(self, kite_update: dict):
        """
        Called by LiveFeed when KiteTicker fires an order status update.
        Normalises Kite's format into the internal record shape and dispatches
        to all registered callbacks (same path as paper fills).
        """
        status = kite_update.get("status", "")
        if status not in ("COMPLETE", "REJECTED", "CANCELLED"):
            return  # ignore OPEN / PENDING / TRIGGER PENDING

        order_id = str(kite_update.get("order_id", ""))
        exchange = kite_update.get("exchange", "NSE")
        symbol = kite_update.get("tradingsymbol", "")
        instrument_fallback = f"{exchange}:{symbol}"

        # Primary lookup by order_id; fall back to instrument map for GTT-triggered fills
        original = self._live_orders.get(order_id)
        if original is None:
            original = self._instrument_orders.get(instrument_fallback)
            if original is not None:
                logger.info(
                    "GTT fill detected | %s | recovered context from instrument map | strategy=%s",
                    instrument_fallback, original.strategy,
                )

        instrument = original.instrument if original else instrument_fallback
        direction = kite_update.get("transaction_type", "")
        fill_price = float(kite_update.get("average_price") or 0)
        quantity = int(kite_update.get("filled_quantity") or 0)
        trigger_price = float(kite_update.get("trigger_price") or 0)

        # GTT exits should be treated as EXIT signal_type so strategy state is reset.
        # _instrument_orders stores the original BUY ENTRY order — if the fill is a
        # SELL, we must override to EXIT regardless of what the original order says.
        from trader.strategies.base import SignalType
        if original is not None:
            if direction == "SELL" and original.signal_type == SignalType.ENTRY:
                recovered_signal_type = SignalType.EXIT
            else:
                recovered_signal_type = original.signal_type
        elif direction == "SELL":
            recovered_signal_type = SignalType.EXIT
        else:
            recovered_signal_type = None

        record = {
            "order_id": order_id,
            "instrument": instrument,
            "order_type": kite_update.get("order_type", "MARKET"),
            "product": kite_update.get("product", "CNC"),
            "direction": direction,
            "quantity": quantity,
            "price": fill_price,
            "fill_price": fill_price,
            "trigger_price": trigger_price,
            "status": status,
            "mode": "live",
            "strategy": original.strategy if original else "",
            "signal_type": recovered_signal_type,
        }
        self._store.upsert_order(record)
        logger.info(
            "Live fill | %s %s x%d @ %.2f | status=%s | strategy=%s",
            direction, instrument, quantity, fill_price, status,
            record["strategy"],
        )
        self._dispatch(record)
        # Clean up completed/terminal orders from in-flight maps
        if status in ("COMPLETE", "REJECTED", "CANCELLED"):
            self._live_orders.pop(order_id, None)
            if status == "COMPLETE" and direction == "SELL":
                self._instrument_orders.pop(instrument, None)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _place_paper(self, order: Order) -> str:
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        self._pending_paper[order_id] = order
        record = {
            "order_id": order_id,
            "instrument": order.instrument,
            "order_type": "MARKET",
            "product": config.product,
            "direction": order.direction.value,
            "quantity": order.quantity,
            "price": None,
            "trigger_price": order.stop_loss,
            "status": "PENDING",
            "mode": "paper",
        }
        self._store.upsert_order(record)
        logger.info(
            "Paper order queued | %s x%d | SL=%.2f target=%.2f | strategy=%s",
            order.instrument, order.quantity, order.stop_loss, order.target_price, order.strategy,
        )
        return order_id

    def _place_live(self, order: Order) -> str:
        symbol = order.instrument.split(":")[-1]
        if order.direction == Direction.SELL:
            self._cancel_gtt(order.instrument)
        try:
            order_id = self._kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=_EXCHANGE,
                tradingsymbol=symbol,
                transaction_type=order.direction.value,
                quantity=order.quantity,
                product=config.product,
                order_type="MARKET",
            )
            record = {
                "order_id": str(order_id),
                "instrument": order.instrument,
                "order_type": "MARKET",
                "product": config.product,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "price": None,
                "trigger_price": order.stop_loss,
                "status": "PENDING",
                "mode": "live",
            }
            self._store.upsert_order(record)
            self._live_orders[str(order_id)] = order
            if order.direction == Direction.BUY:
                self._instrument_orders[order.instrument] = order
            logger.info(
                "Live order placed | %s x%d | id=%s | strategy=%s",
                order.instrument, order.quantity, order_id, order.strategy,
            )
            if config.gtt_enabled and order.direction == Direction.BUY:
                self._place_gtt_sl(order, symbol)
            return str(order_id)
        except Exception as e:
            logger.error("Failed to place order for %s: %s", order.instrument, e)
            # Dispatch a synthetic REJECTED so the strategy clears _entry_price.
            # Without this, the strategy is permanently stuck — no fill will ever arrive.
            self._dispatch({
                "order_id": "FAILED",
                "instrument": order.instrument,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "price": 0.0,
                "fill_price": 0.0,
                "trigger_price": 0.0,
                "status": "REJECTED",
                "mode": "live",
                "strategy": order.strategy,
                "signal_type": order.signal_type,
                "status_message": str(e),
            })
            raise

    def _place_gtt_sl(self, order: Order, symbol: str):
        try:
            result = self._kite.place_gtt(
                trigger_type=self._kite.GTT_TYPE_TWO_LEG,
                tradingsymbol=symbol,
                exchange=_EXCHANGE,
                trigger_values=[order.stop_loss, order.target_price],
                last_price=order.price_hint,
                orders=[
                    {
                        "transaction_type": "SELL",
                        "quantity": order.quantity,
                        "product": "CNC",
                        "order_type": "MARKET",
                    },
                    {
                        "transaction_type": "SELL",
                        "quantity": order.quantity,
                        "product": "CNC",
                        "order_type": "LIMIT",
                        "price": order.target_price,
                    },
                ],
            )
            trigger_id = result["trigger_id"]
            self._gtt_ids[order.instrument] = trigger_id
            logger.info(
                "GTT OCO placed | %s | SL=%.2f target=%.2f | gtt_id=%s",
                symbol, order.stop_loss, order.target_price, trigger_id,
            )
        except Exception as e:
            logger.error("Failed to place GTT for %s: %s", symbol, e)

    def _cancel_gtt(self, instrument: str):
        trigger_id = self._gtt_ids.pop(instrument, None)
        if trigger_id is None:
            return
        try:
            self._kite.delete_gtt(trigger_id)
            logger.info("GTT cancelled | %s | gtt_id=%s", instrument, trigger_id)
        except Exception as e:
            logger.error("Failed to cancel GTT for %s (gtt_id=%s): %s", instrument, trigger_id, e)

    def _dispatch(self, record: dict):
        for cb in self._callbacks:
            try:
                cb(record)
            except Exception:
                logger.exception("Error in order update callback")
