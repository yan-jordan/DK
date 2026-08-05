"""io_utils.py — خواندن ورودی و نوشتن خروجی. تنها ماژولی که I/O انجام می‌دهد."""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT_PATH = PROJECT_ROOT / "orders.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "results.json"

REQUIRED_ORDER_FIELDS = (
    "order_id",
    "created_at",
    "city_tier",
    "membership",
    "payment_method",
    "items",
)
REQUIRED_ITEM_FIELDS = (
    "seller_id",
    "is_bulky",
    "weight_grams",
    "unit_price",
    "quantity",
    "discount",
)


def validate_orders(orders: list[dict]) -> None:
    """
    اعتبارسنجی حداقلیِ ساختار ورودی.

    هدف این نیست که همه‌ی خطاهای ممکن گرفته شود؛ هدف این است که اگر فیلدی
    گم شده باشد، برنامه با یک پیام روشن و قابل‌ردیابی متوقف شود، نه با یک
    KeyError خام در وسط محاسبات.
    """
    if not isinstance(orders, list):
        raise ValueError("فایل ورودی باید یک آرایه‌ی JSON از سفارش‌ها باشد.")

    for index, order in enumerate(orders):
        for field in REQUIRED_ORDER_FIELDS:
            if field not in order:
                raise ValueError(
                    f"سفارش شماره‌ی {index} فیلد اجباری «{field}» را ندارد."
                )
        if not order["items"]:
            raise ValueError(f"سفارش {order['order_id']} هیچ آیتمی ندارد.")
        for item in order["items"]:
            for field in REQUIRED_ITEM_FIELDS:
                if field not in item:
                    raise ValueError(
                        f"آیتمی در سفارش {order['order_id']} فیلد «{field}» را ندارد."
                    )


def load_orders(path: str | Path = DEFAULT_INPUT_PATH) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        orders = json.load(f)
    validate_orders(orders)
    return orders


def save_results(results: list[dict], path: str | Path = DEFAULT_OUTPUT_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        f.write("\n")
