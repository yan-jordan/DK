"""
test_rules.py — تست واحدِ قواعد اتمیک.

اینجا صرفاً بررسی می‌شود که هر قاعده به‌تنهایی درست پیاده شده است (مرزها،
گردکردن، مقادیر ناشناخته). تثبیتِ *تصمیم‌های* مستندشده در DECISIONS.md وظیفه‌ی
`test_decisions.py` است.
"""

import pytest

from src import rules


# --------------------------------------------------------------------------
# قاعده‌ی ۱ — هزینه‌ی پایه‌ی مقصد
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "city_tier, expected",
    [
        ("tehran", 25_000),
        ("provincial_capital", 35_000),
        ("other", 50_000),
        ("مقدار_ناشناخته", 50_000),  # fallback محافظه‌کارانه
        ("", 50_000),
    ],
)
def test_base_fee_for_city_tier(city_tier, expected):
    assert rules.base_fee_for_city_tier(city_tier) == expected


# --------------------------------------------------------------------------
# قاعده‌ی ۳ — هزینه‌ی وزن (تمرکز روی مرزها)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "grams, expected",
    [
        (0, 0),
        (999, 0),
        (1_000, 0),  # مرز: دقیقاً ۱ کیلو هنوز رایگان است
        (1_001, 5_000),  # کوچک‌ترین سرریز، یک پله‌ی کامل حساب می‌شود
        (1_500, 5_000),  # مرز: دقیقاً ۵۰۰ گرم اضافه = یک پله
        (1_501, 10_000),
        (2_000, 10_000),
        (2_600, 20_000),  # ۱۶۰۰ گرم اضافه → ceil(3.2) = 4 پله
        (9_000, 80_000),
    ],
)
def test_weight_fee_boundaries(grams, expected):
    assert rules.weight_fee(grams) == expected


def test_weight_fee_never_negative():
    """رگرسیون: وزن‌های زیر ۱ کیلو نباید هزینه‌ی منفی تولید کنند."""
    for grams in range(0, 1_001, 50):
        assert rules.weight_fee(grams) >= 0


# --------------------------------------------------------------------------
# قاعده‌ی ۷ — مرزهای بازه‌ی شب
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "created_at, expected_night",
    [
        ("2026-03-14T22:59:59+03:30", False),
        ("2026-03-14T23:00:00+03:30", True),  # مرز شامل
        ("2026-03-14T23:40:00+03:30", True),
        ("2026-03-15T00:00:00+03:30", True),
        ("2026-03-15T05:59:59+03:30", True),
        ("2026-03-15T06:00:00+03:30", False),  # مرز غیرشامل
        ("2026-03-14T14:20:00+03:30", False),
    ],
)
def test_night_window_boundaries(created_at, expected_night):
    assert rules.is_night_order(created_at) is expected_night


# --------------------------------------------------------------------------
# قاعده‌ی ۸ — کارمزد پرداخت
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "payment_method, expected",
    [
        ("online", 0),
        ("cash_on_delivery", 10_000),
        ("wallet_ناشناخته", 10_000),  # fallback محافظه‌کارانه
    ],
)
def test_payment_method_fee(payment_method, expected):
    assert rules.payment_method_fee(payment_method) == expected


# --------------------------------------------------------------------------
# قاعده‌ی ۶ — تشخیص حجیم‌بودن مرسوله
# --------------------------------------------------------------------------
def test_shipment_is_bulky_detects_any_bulky_item():
    from tests.conftest import make_item

    assert rules.shipment_is_bulky([make_item(is_bulky=False)]) is False
    assert rules.shipment_is_bulky([make_item(is_bulky=True)]) is True
    assert (
        rules.shipment_is_bulky([make_item(is_bulky=False), make_item(is_bulky=True)])
        is True
    )
