"""
Zerodha transaction cost calculator for equity trades.

Covers equity intraday (MIS) and equity delivery (CNC) on NSE.
F&O is not currently traded and is excluded.

Charges per order
-----------------
Intraday (MIS):
  Brokerage        : min(0.03% × turnover, ₹20)   — both sides
  STT              : 0.025% of turnover             — sell side only
  Transaction (NSE): 0.00307% of turnover           — both sides
  SEBI             : ₹10 / crore (= 0.0001%)        — both sides
  GST              : 18% on (brokerage + SEBI + transaction)
  Stamp            : 0.003% of turnover             — buy side only

Delivery (CNC):
  Brokerage        : zero
  STT              : 0.1% of turnover               — both sides
  Transaction (NSE): 0.00307% of turnover           — both sides
  SEBI             : ₹10 / crore (= 0.0001%)        — both sides
  GST              : 18% on (brokerage + SEBI + transaction)
  Stamp            : 0.015% of turnover             — buy side only

Usage
-----
    from trader.costs import order_cost, round_trip_cost

    # Cost for a single BUY order of 100 shares at ₹500 (MIS)
    cost = order_cost(product="MIS", side="BUY", quantity=100, price=500.0)

    # Combined entry + exit cost (common use in backtest)
    total = round_trip_cost(product="MIS", quantity=100,
                            entry_price=500.0, exit_price=510.0)
"""


def order_cost(product: str, side: str, quantity: int, price: float) -> float:
    """
    Returns the total transaction cost for a single order in rupees.

    Args:
        product  : "MIS" (intraday) or "CNC" (delivery)
        side     : "BUY" or "SELL"
        quantity : number of shares
        price    : execution price per share
    """
    turnover = quantity * price

    # --- Brokerage ---
    if product == "CNC":
        brokerage = 0.0
    else:  # MIS
        brokerage = min(turnover * 0.0003, 20.0)

    # --- STT (Securities Transaction Tax) ---
    if product == "CNC":
        stt = turnover * 0.001          # 0.1% on both sides
    else:  # MIS
        stt = turnover * 0.00025 if side == "SELL" else 0.0   # 0.025% sell only

    # --- Exchange transaction charges (NSE) ---
    transaction = turnover * 0.0000307  # 0.00307%

    # --- SEBI charges: ₹10/crore ---
    sebi = turnover * 0.000001          # = ₹10 per ₹1,00,00,000

    # --- GST: 18% on (brokerage + SEBI + transaction) ---
    gst = (brokerage + sebi + transaction) * 0.18

    # --- Stamp charges (buy side only) ---
    if side == "BUY":
        stamp = turnover * (0.00015 if product == "CNC" else 0.00003)
    else:
        stamp = 0.0

    return brokerage + stt + transaction + sebi + gst + stamp


def round_trip_cost(
    product: str,
    quantity: int,
    entry_price: float,
    exit_price: float,
    entry_side: str = "BUY",
) -> float:
    """
    Total cost for a complete entry + exit round trip.

    Args:
        product     : "MIS" or "CNC"
        quantity    : shares traded
        entry_price : fill price at entry
        exit_price  : fill price at exit
        entry_side  : "BUY" (long) or "SELL" (short) — exit side is inferred
    """
    exit_side = "SELL" if entry_side == "BUY" else "BUY"
    return (
        order_cost(product, entry_side, quantity, entry_price)
        + order_cost(product, exit_side, quantity, exit_price)
    )
