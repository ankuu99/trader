"""
Portfolio Tracker — tracks open positions and P&L.

Live mode : fetches positions from Kite on demand.
Paper mode: tracks fills locally.
"""

from dataclasses import dataclass

from kiteconnect import KiteConnect

from trader.core.config import config
from trader.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Position:
    instrument: str
    quantity: int
    average_price: float
    unrealised_pnl: float = 0.0
    realised_pnl: float = 0.0


class PortfolioTracker:
    def __init__(self, kite: KiteConnect, mode: str):
        self._kite = kite
        self._mode = mode
        self._positions: dict[str, Position] = {}

    def on_order_filled(self, instrument: str, direction: str, quantity: int, fill_price: float):
        """Update paper positions when a fill is confirmed."""
        if self._mode != "paper":
            return
        symbol = instrument.split(":")[-1]
        self._positions[symbol] = Position(
            instrument=symbol,
            quantity=quantity,
            average_price=fill_price,
        )
        logger.info("Paper position | %s x%d @ %.2f", symbol, quantity, fill_price)

    def refresh(self):
        """Fetch live positions from Kite (no-op in paper mode)."""
        if self._mode == "paper":
            return
        try:
            raw = self._kite.positions().get("net", [])
            self._positions = {}
            for p in raw:
                if p["quantity"] == 0:
                    continue
                symbol = p["tradingsymbol"]
                self._positions[symbol] = Position(
                    instrument=symbol,
                    quantity=p["quantity"],
                    average_price=p["average_price"],
                    unrealised_pnl=p["unrealised"],
                    realised_pnl=p["realised"],
                )
        except Exception as e:
            logger.error("Failed to fetch positions: %s", e)

    def log_summary(self):
        positions = [p for p in self._positions.values() if p.quantity != 0]
        total_unrealised = sum(p.unrealised_pnl for p in positions)
        total_realised = sum(p.realised_pnl for p in positions)
        logger.info(
            "Portfolio | open=%d | unrealised=%.2f | realised=%.2f | net=%.2f (%.1f%%)",
            len(positions),
            total_unrealised,
            total_realised,
            total_unrealised + total_realised,
            (total_unrealised + total_realised) / config.total_capital * 100,
        )
