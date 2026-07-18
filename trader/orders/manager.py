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
from trader.notifications import telegram
from trader.strategies.base import Direction
from trader.risk.manager import Order

logger = get_logger(__name__)

OrderUpdateCallback = Callable[[dict], None]

_EXCHANGE = "NSE"


class OrderManager:
    def __init__(self, kite: KiteConnect, store: Store, mode: str,
                 position_lookup: Callable[[], list[str]] | None = None):
        self._kite = kite
        self._store = store
        self._mode = mode
        self._callbacks: list[OrderUpdateCallback] = []
        # Optional accessor returning the currently-held position instrument keys
        # (e.g. risk._open_positions). Used to reconcile cross-exchange / external
        # SELL fills against the position we actually hold.
        self._position_lookup = position_lookup
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

    def clear_pending(self):
        """Discard stale pending paper orders (EOD or day-boundary cancellation).

        Dispatches CANCELLED for each order so strategies clear _entry_price and
        the risk manager can release pending capital locks.
        """
        if not self._pending_paper:
            return
        logger.warning(
            "Cancelling %d unfilled pending paper order(s): %s",
            len(self._pending_paper),
            [o.instrument for o in self._pending_paper.values()],
        )
        for order_id, order in list(self._pending_paper.items()):
            self._dispatch({
                "order_id": order_id,
                "instrument": order.instrument,
                "order_type": config.order_type,
                "product": config.product,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "price": 0.0,
                "fill_price": 0.0,
                "trigger_price": 0.0,
                "status": "CANCELLED",
                "mode": "paper",
                "strategy": order.strategy,
                "signal_type": order.signal_type,
                "addon": getattr(order, "addon", False),
            })
        self._pending_paper.clear()

    def on_candle(self, candle: dict):
        """Fill pending paper orders.

        MARKET orders: fill at candle open (next-candle fill, existing behaviour).
        LIMIT orders:  fill only if price touched the limit level during the candle
                       (low <= limit for BUY, high >= limit for SELL); fill at the
                       limit price, not the open.  Unfilled orders stay pending and
                       are retried on subsequent candles until cleared by clear_pending().
        """
        if self._mode != "paper" or not self._pending_paper:
            return
        symbol = candle.get("_symbol")
        to_fill = [
            (oid, o) for oid, o in self._pending_paper.items()
            if o.instrument == symbol
        ]
        for order_id, order in to_fill:
            if config.order_type == "LIMIT":
                if order.direction == Direction.BUY:
                    if candle["low"] > order.price_hint:
                        continue  # price never reached limit — keep pending
                    fill_price = order.price_hint
                else:
                    if candle["high"] < order.price_hint:
                        continue
                    fill_price = order.price_hint
            else:
                fill_price = candle["open"]
            del self._pending_paper[order_id]
            record = {
                "order_id": order_id,
                "instrument": order.instrument,
                "order_type": config.order_type.upper(),
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
                            "target_price": order.target_price,
                            "partial": getattr(order, "partial", False),
                            "addon": getattr(order, "addon", False)})

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
        status_message = kite_update.get("status_message") or kite_update.get("status_message_raw") or ""

        # Layer 1 — cross-exchange / external SELL reconciliation.
        # An equity held on NSE can be sold on BSE (or vice-versa), and manual /
        # external sells aren't in our order maps. Such a fill arrives keyed by the
        # other exchange (e.g. BSE:GAIL) and won't match the position we hold
        # (NSE:GAIL), so the close silently no-ops and P&L is lost. If this is a
        # SELL with no matching order and the fill's instrument isn't a tracked
        # position, remap it to the held position with the same trading symbol so
        # the close reconciles and the stored order pairs in trade history.
        if (original is None and direction == "SELL"
                and self._position_lookup is not None):
            held = self._position_lookup()
            if instrument not in held:
                same_symbol = [p for p in held if p.split(":", 1)[-1] == symbol]
                if len(same_symbol) == 1:
                    logger.warning(
                        "External/cross-exchange SELL reconciled by symbol | "
                        "fill=%s -> position=%s @ %.2f",
                        instrument, same_symbol[0], fill_price,
                    )
                    instrument = same_symbol[0]

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
            # Scale-out: only an in-app partial SELL carries the flag. GTT/external
            # SELLs recover the ENTRY order (partial=False) → always full close.
            "partial": getattr(original, "partial", False) if original else False,
            # Scale-in: BUY fills for add-on lots must not re-anchor strategy state.
            "addon": getattr(original, "addon", False) if original else False,
        }
        self._store.upsert_order(record)
        if status == "REJECTED":
            logger.warning(
                "Live fill | %s %s x%d @ %.2f | status=%s | strategy=%s | reason=%s",
                direction, instrument, quantity, fill_price, status,
                record["strategy"], status_message or "(no message from Kite)",
            )
        else:
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
            if status in ("REJECTED", "CANCELLED") and direction == "BUY":
                self._instrument_orders.pop(instrument, None)  # R6-4: prevent stale GTT context
        # Place GTT only after BUY fill is confirmed (L5 fix: not at order submission time)
        if (status == "COMPLETE" and direction == "BUY" and config.gtt_enabled
                and original is not None and not getattr(original, "addon", False)):
            # Add-on lots never get their own GTT — exits sell the blended position.
            self._place_gtt_sl(original, symbol, last_price=fill_price)

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _place_paper(self, order: Order) -> str:
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        self._pending_paper[order_id] = order
        record = {
            "order_id": order_id,
            "instrument": order.instrument,
            "order_type": config.order_type.upper(),
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
        telegram.notify_order_queued(
            order.instrument, order.direction.value, order.quantity,
            strategy=order.strategy, mode="paper",
            stop_loss=order.stop_loss or None,
            target_price=order.target_price or None,
            price_hint=order.price_hint or None,
        )
        return order_id

    def _place_live(self, order: Order) -> str:
        symbol = order.instrument.split(":")[-1]
        if order.direction == Direction.SELL:
            self._cancel_gtt(order.instrument)
        order_type = config.order_type  # "MARKET" or "LIMIT"
        limit_price = order.price_hint if order_type == "LIMIT" else None
        try:
            kite_kwargs = dict(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=_EXCHANGE,
                tradingsymbol=symbol,
                transaction_type=order.direction.value,
                quantity=order.quantity,
                product=config.product,
                order_type=order_type,
            )
            if order_type == "LIMIT":
                kite_kwargs["price"] = limit_price
            else:
                # Zerodha API requires market_protection for MARKET orders.
                # -1 = automatic protection per Zerodha's own guidelines.
                kite_kwargs["market_protection"] = -1
            order_id = self._kite.place_order(**kite_kwargs)
            record = {
                "order_id": str(order_id),
                "instrument": order.instrument,
                "order_type": order_type,
                "product": config.product,
                "direction": order.direction.value,
                "quantity": order.quantity,
                "price": limit_price,
                "trigger_price": order.stop_loss,
                "status": "PENDING",
                "mode": "live",
            }
            self._store.upsert_order(record)
            self._live_orders[str(order_id)] = order
            if order.direction == Direction.BUY:
                self._instrument_orders[order.instrument] = order
            logger.info(
                "Live order placed | %s x%d @ %s | type=%s | id=%s | strategy=%s",
                order.instrument, order.quantity,
                f"{limit_price:.2f}" if limit_price else "MARKET",
                order_type, order_id, order.strategy,
            )
            telegram.notify_order_queued(
                order.instrument, order.direction.value, order.quantity,
                strategy=order.strategy, mode="live",
                stop_loss=order.stop_loss or None,
                target_price=order.target_price or None,
                price_hint=order.price_hint or None,
                order_type=order_type,
            )
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
                "addon": getattr(order, "addon", False),
                "status_message": str(e),
            })
            raise

    def _place_gtt_sl(self, order: Order, symbol: str, last_price: float | None = None):
        fill_price = last_price or order.price_hint

        # Rebase SL and target to the actual fill price.
        # The Order carries levels computed at signal time from price_hint.
        # If fill differs (e.g. MARKET order slippage), derive the implied
        # percentages and reapply them from the real fill so GTT levels are correct.
        if order.price_hint > 0 and fill_price != order.price_hint:
            sl_pct     = (order.price_hint - order.stop_loss)   / order.price_hint
            target_pct = (order.target_price - order.price_hint) / order.price_hint
            sl_price     = round(fill_price * (1 - sl_pct),     2)
            target_price = round(fill_price * (1 + target_pct), 2)
            logger.info(
                "GTT levels rebased to fill | %s | signal=%.2f fill=%.2f"
                " | SL %.2f→%.2f target %.2f→%.2f",
                symbol, order.price_hint, fill_price,
                order.stop_loss, sl_price, order.target_price, target_price,
            )
        else:
            sl_price     = order.stop_loss
            target_price = order.target_price

        try:
            result = self._kite.place_gtt(
                trigger_type=self._kite.GTT_TYPE_OCO,
                tradingsymbol=symbol,
                exchange=_EXCHANGE,
                trigger_values=[sl_price, target_price],
                last_price=fill_price,
                orders=[
                    {
                        "transaction_type": "SELL",
                        "quantity": order.quantity,
                        "product": "CNC",
                        "order_type": "MARKET",
                        "price": sl_price,
                    },
                    {
                        "transaction_type": "SELL",
                        "quantity": order.quantity,
                        "product": "CNC",
                        "order_type": "LIMIT",
                        "price": target_price,
                    },
                ],
            )
            trigger_id = result["trigger_id"]
            self._gtt_ids[order.instrument] = trigger_id
            logger.info(
                "GTT OCO placed | %s | SL=%.2f target=%.2f | gtt_id=%s",
                symbol, sl_price, target_price, trigger_id,
            )
            telegram.notify_gtt_placed(order.instrument, order.quantity, sl_price, target_price)
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
