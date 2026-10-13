"""
Tests for discount calculation logic.
"""

from math_ops import calculate_discount


def test_calculate_discount_standard():
    # 20% discount on 100.0 must be 80.0
    assert calculate_discount(100.0, 20.0) == 80.0


def test_calculate_discount_zero():
    # 0% discount on 50.0 must be 50.0
    assert calculate_discount(50.0, 0.0) == 50.0


def test_calculate_discount_full():
    # 100% discount on 75.0 must be 0.0
    assert calculate_discount(75.0, 100.0) == 0.0