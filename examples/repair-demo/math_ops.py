"""
Mathematical operations module for discount calculation.
"""


def calculate_discount(price: float, discount_percent: float) -> float:
    """Calculate the final price after applying a percentage discount."""
    if price < 0:
        raise ValueError("Price cannot be negative")
    if not (0 <= discount_percent <= 100):
        raise ValueError("Discount percent must be between 0 and 100")

    # Correct formula: subtract discount amount from price
    return round(price - (price * discount_percent / 100.0), 2)