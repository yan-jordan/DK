"""ابزارهای مشترک تست‌ها."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def make_order(**overrides) -> dict:
    """
    یک سفارش «حداقلیِ سالم» می‌سازد که می‌شود تک‌تک فیلدهایش را override کرد.

    این factory باعث می‌شود هر تست فقط همان فیلدی را که واقعاً برایش مهم است
    ذکر کند — بنابراین از خودِ تست پیداست کدام متغیر در حال آزمایش است.
    """
    order = {
        "order_id": "ORD-TEST",
        "created_at": "2026-03-14T14:20:00+03:30",  # روز
        "destination_city": "تهران",
        "city_tier": "tehran",
        "membership": "regular",
        "payment_method": "online",
        "items": [make_item()],
    }
    order.update(overrides)
    return order


def make_item(**overrides) -> dict:
    item = {
        "item_id": "IT-TEST",
        "seller_id": "SL-1",
        "category": "books",
        "is_bulky": False,
        "weight_grams": 500,
        "unit_price": 100_000,
        "quantity": 1,
        "discount": 0,
    }
    item.update(overrides)
    return item


@pytest.fixture(scope="session")
def real_orders():
    """دیتاست واقعی تمرین."""
    from src import io_utils

    return io_utils.load_orders(PROJECT_ROOT / "orders.json")


@pytest.fixture(scope="session")
def real_results(real_orders):
    from src.engine import calculate_all

    return {r["order_id"]: r for r in calculate_all(real_orders)}
