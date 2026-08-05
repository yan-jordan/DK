"""
test_golden.py — تست رگرسیونِ «طلایی».

تست‌های `test_decisions.py` هر تصمیم را جداگانه می‌سنجند. این فایل کارِ مکملی
می‌کند: کل خروجی روی کل دیتاست را قفل می‌کند، تا اگر رفتار در جایی عوض شد که
هیچ تستِ تصمیمی پوششش نمی‌داد، باز هم دیده شود.

اگر تصمیمی را عمداً عوض کردی، این فایل هم باید عمداً به‌روزرسانی شود — و همین
«اجبار به به‌روزرسانی آگاهانه» دقیقاً هدف تست طلایی است.
"""

import json
from pathlib import Path

from src.engine import calculate_all

PROJECT_ROOT = Path(__file__).resolve().parent.parent

EXPECTED_TOTALS = {
    "ORD-1001": 25_000,
    "ORD-1002": 70_000,
    "ORD-1027": 35_000,
    "ORD-1003": 30_000,
    "ORD-1004": 35_000,
    "ORD-1025": 25_000,
    "ORD-1005": 50_000,  # بند ۱۱ — وزن × تعداد
    "ORD-1006": 25_000,
    "ORD-1028": 45_000,  # بند ۱۱ — وزن × تعداد
    "ORD-1007": 0,
    "ORD-1008": 0,
    "ORD-1009": 0,
    "ORD-1010": 150_000,
    "ORD-1020": 0,
    "ORD-1026": 0,
    "ORD-1011": 27_500,
    "ORD-1012": 25_000,
    "ORD-1013": 27_500,
    "ORD-1014": 0,
    "ORD-1015": 0,
    "ORD-1016": 135_000,
    "ORD-1017": 200_000,
    "ORD-1018": 200_000,
    "ORD-1019": 200_000,
    "ORD-1021": 50_000,
    "ORD-1023": 0,
    "ORD-1024": 0,
}


def test_golden_totals(real_orders):
    actual = {r["order_id"]: r["total_shipping_fee"] for r in calculate_all(real_orders)}
    assert actual == EXPECTED_TOTALS


def test_results_file_is_up_to_date(real_orders):
    """
    `results.json` موجود در ریپو باید با خروجیِ کدِ فعلی یکی باشد.
    این تست جلوی تحویل‌دادن یک خروجیِ کهنه را می‌گیرد.
    """
    results_path = PROJECT_ROOT / "results.json"
    assert results_path.exists(), "results.json وجود ندارد؛ ابتدا `python -m src.main` را اجرا کن."

    on_disk = json.loads(results_path.read_text(encoding="utf-8"))
    assert on_disk == calculate_all(real_orders)


def test_every_order_appears_exactly_once(real_orders):
    results = calculate_all(real_orders)
    ids = [r["order_id"] for r in results]
    assert len(ids) == len(set(ids)) == len(real_orders)
