"""
engine.py — ارکستراسیون: ترکیب قواعد `rules.py` برای محاسبه‌ی یک سفارش کامل.

سلسله‌مراتب اولویت قواعد (مطابق DECISIONS.md):

    ۱) معافیت سطح سفارش  : پلاس  یا  مبلغ خالص ≥ ۵۰۰٬۰۰۰  →  همه‌چیز صفر
    ۲) مرسوله‌ی حجیم       : هزینه‌ی ثابت ۱۵۰٬۰۰۰، مستقل از مقصد/شب/پرداخت
    ۳) مرسوله‌ی معمولی     : (پایه + وزن) × ضریب شب  +  کارمزد پرداخت در محل
    ۴) سقف سطح سفارش      : مجموع کل، حداکثر ۲۰۰٬۰۰۰
"""

from __future__ import annotations

from . import rules


def group_items_by_seller(items: list[dict]) -> dict[str, list[dict]]:
    """
    قاعده‌ی ۲ — هر سفارش بر اساس `seller_id` به مرسوله‌ها تقسیم می‌شود.

    ترتیب کلیدها ترتیب اولین ظهور هر فروشنده در `items` است (dict در پایتون ۳.۷+
    ترتیب درج را حفظ می‌کند)، تا خروجی قطعی و قابل diff گرفتن باشد.
    """
    shipments: dict[str, list[dict]] = {}
    for item in items:
        shipments.setdefault(item["seller_id"], []).append(item)
    return shipments


def calculate_shipment_fee(order: dict, items: list[dict]) -> float:
    """
    هزینه‌ی ارسال یک مرسوله (آیتم‌های یک فروشنده).

    توجه: معافیت‌های سطح سفارش (پلاس / ≥۵۰۰هزار) اینجا اعمال **نمی‌شوند**؛
    آن‌ها در `calculate_order` و پیش از رسیدن به این تابع تصمیم‌گیری می‌شوند.
    """
    # بند ۳ و ۱۳ — مرسوله‌ی حجیم: عدد ثابت و نهایی، بدون هیچ محاسبه‌ی دیگر.
    if rules.shipment_is_bulky(items):
        return float(rules.BULKY_FLAT_FEE)

    total_weight = sum(rules.item_total_weight_grams(item) for item in items)

    # قاعده‌ی ۱ (پایه‌ی مقصد، per-shipment — بند ۷) + قاعده‌ی ۳ (وزن)
    fee = rules.weight_fee(total_weight) + rules.base_fee_for_city_tier(
        order["city_tier"]
    )

    # قاعده‌ی ۷ — افزایش شب فقط روی «پایه + وزن» اعمال می‌شود (بند ۶، گزینه‌ی الف)
    if rules.is_night_order(order["created_at"]):
        fee *= rules.NIGHT_SURCHARGE_MULTIPLIER

    # قاعده‌ی ۸ — کارمزد ثابت پرداخت در محل، **بعد از** ضرب شب و بدون مشمول‌شدن آن
    fee += rules.payment_method_fee(order["payment_method"])

    return fee


def order_is_free_shipping(order: dict) -> bool:
    """
    بند ۱ و ۲ — دو شرط معافیت سطح سفارش، هر دو بی‌قیدوشرط و با اولویت مطلق.
    """
    if order["membership"] == rules.PLUS_MEMBERSHIP:
        return True
    net_amount = rules.items_net_amount(order["items"])
    return net_amount >= rules.FREE_SHIPPING_AMOUNT_THRESHOLD


def calculate_order(order: dict) -> dict:
    """
    یک سفارش را به رکورد خروجی نهایی تبدیل می‌کند.

    خروجی: {"order_id": str, "shipments": [{"seller_id", "shipping_fee"}], "total_shipping_fee": int}
    """
    grouped = group_items_by_seller(order["items"])

    # --- ۱) معافیت سطح سفارش: اولویت مطلق، پیش از هر محاسبه‌ی دیگری ---
    if order_is_free_shipping(order):
        return {
            "order_id": order["order_id"],
            "shipments": [
                {"seller_id": seller_id, "shipping_fee": 0} for seller_id in grouped
            ],
            "total_shipping_fee": 0,
        }

    # --- ۲/۳) محاسبه‌ی هر مرسوله ---
    shipments: list[dict] = []
    raw_total = 0.0
    for seller_id, items in grouped.items():
        fee = calculate_shipment_fee(order, items)
        raw_total += fee
        shipments.append({"seller_id": seller_id, "shipping_fee": round(fee)})

    # --- ۴) سقف سطح سفارش (بند ۵) ---
    total = round(raw_total)
    if total > rules.ORDER_SHIPPING_FEE_CAP:
        total = rules.ORDER_SHIPPING_FEE_CAP

    return {
        "order_id": order["order_id"],
        "shipments": shipments,
        "total_shipping_fee": total,
    }


def calculate_all(orders: list[dict]) -> list[dict]:
    """کل دیتاست را پردازش می‌کند و ترتیب ورودی را حفظ می‌کند."""
    return [calculate_order(order) for order in orders]
