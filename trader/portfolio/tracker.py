"""
Portfolio Tracker — fetches and caches current positions and P&L from Kite.

Provides a live snapshot of:
  - Intraday positions (MIS)
  - Holdings (CNC, long-term)
  - Unrealised and realised P&L per instrument and in total

In paper mode, positions are tracked from order fills rather than
fetched from Kite (since no real orders are placed).
"""

from dataclasses import dataclass, field
from datetime import datetime

from kiteconnect import KiteConnect

from trader.core.config import config
from trader.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Position:
    instrument: str
    quantity: int          # positive = long, negative = short
    average_price: float
    last_price: float
    unrealised_pnl: float
    realised_pnl: float
    product: str           # MIS, CNC, NRML


@dataclass
class PortfolioSnapshot:
    positions: list[Position] = field(default_factory=list)
    total_unrealised_pnl: float = 0.0
    total_realised_pnl: float = 0.0
    fetched_at: datetime = field(default_factory=datetime.now)

    def net_pnl(self) -> float:
        return self.total_unrealised_pnl + self.total_realised_pnl

    def position_for(self, instrument: str) -> Position | None:
        symbol = instrument.split(":")[-1]
        return next((p for p in self.positions if p.instrument == symbol), None)


class PortfolioTracker:
    def __init__(self, kite: KiteConnect, mode: str):
        self._kite = kite
        self._mode = mode
        self._snapshot: PortfolioSnapshot = PortfolioSnapshot()

        # Paper mode position tracking (keyed by instrument)
        self._paper_positions: dict[str, Position] = {}

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def refresh(self) -> PortfolioSnapshot:
        """
        Fetch current positions from Kite (live) or return paper state.
        Call this once per candle or on demand.
        """
        if self._mode == "paper":
            return self._paper_snapshot()
        return self._fetch_live()

    def on_order_filled(self, instrument: str, direction: str,
                        quantity: int, fill_price: float, signal_type: str):
        """
        Update paper positions when an order is confirmed filled.
        Only used in paper mode.
        """
        if self._mode != "paper":
            return

        symbol = instrument.split(":")[-1]
        pos = self._paper_positions.get(symbol)

        if signal_type == "ENTRY":
            qty = quantity if direction == "BUY" else -quantity
            if pos is None:
                self._paper_positions[symbol] = Position(
                    instrument=symbol,
                    quantity=qty,
                    average_price=fill_price,
                    last_price=fill_price,
                    unrealised_pnl=0.0,
                    realised_pnl=0.0,
                    product="MIS",
                )
            else:
                # Average into existing position
                total_qty = pos.quantity + qty
                if total_qty != 0:
                    pos.average_price = (
                        (pos.average_price * pos.quantity + fill_price * qty) / total_qty
                    )
                pos.quantity = total_qty

        elif signal_type == "EXIT" and pos is not None:
            if direction == "SELL":
                pnl = (fill_price - pos.average_price) * quantity
            else:
                pnl = (pos.average_price - fill_price) * quantity
            pos.realised_pnl += pnl
            pos.quantity = 0
            logger.info("Paper position closed | %s | pnl=%.2f", symbol, pnl)

    def update_last_prices(self, ltp_map: dict[str, float]):
        """
        Update last traded prices for paper positions.
        ltp_map: { "RELIANCE": 2510.0, ... }
        """
        if self._mode != "paper":
            return
        for symbol, price in ltp_map.items():
            pos = self._paper_positions.get(symbol)
            if pos and pos.quantity != 0:
                pos.last_price = price
                pos.unrealised_pnl = (price - pos.average_price) * pos.quantity

    def snapshot(self) -> PortfolioSnapshot:
        """Return the last cached snapshot without fetching."""
        return self._snapshot

    def log_summary(self):
        """Log a one-line P&L summary."""
        s = self._snapshot
        from trader.core.config import config
        logger.info(
            "Portfolio | positions=%d | unrealised=%.2f | realised=%.2f | net=%.2f (%.2f%%)",
            len([p for p in s.positions if p.quantity != 0]),
            s.total_unrealised_pnl,
            s.total_realised_pnl,
            s.net_pnl(),
            s.net_pnl() / config.total_capital * 100,
        )

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _fetch_live(self) -> PortfolioSnapshot:
        try:
            raw = self._kite.positions()
            positions = []

            for p in raw.get("net", []):
                if p["quantity"] == 0:
                    continue
                positions.append(Position(
                    instrument=p["tradingsymbol"],
                    quantity=p["quantity"],
                    average_price=p["average_price"],
                    last_price=p["last_price"],
                    unrealised_pnl=p["unrealised"],
                    realised_pnl=p["realised"],
                    product=p["product"],
                ))

            total_unrealised = sum(p.unrealised_pnl for p in positions)
            total_realised = sum(p.realised_pnl for p in positions)

            self._snapshot = PortfolioSnapshot(
                positions=positions,
                total_unrealised_pnl=total_unrealised,
                total_realised_pnl=total_realised,
            )
            return self._snapshot

        except Exception as e:
            logger.error("Failed to fetch live positions: %s", e)
            return self._snapshot  # return last known state

    def _paper_snapshot(self) -> PortfolioSnapshot:
        positions = list(self._paper_positions.values())
        total_unrealised = sum(p.unrealised_pnl for p in positions)
        total_realised = sum(p.realised_pnl for p in positions)
        self._snapshot = PortfolioSnapshot(
            positions=positions,
            total_unrealised_pnl=total_unrealised,
            total_realised_pnl=total_realised,
        )
        return self._snapshot
