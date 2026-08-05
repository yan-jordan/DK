"""
test_decisions.py — یک تست به ازای هر بندِ DECISIONS.md.

این فایل قلب بخش «تست‌ها»ی تحویل است. هر تست:
  ۱) در نامش شماره‌ی بند DECISIONS.md را دارد،
  ۲) در docstring می‌گوید چه ابهامی بود و چه تصمیمی گرفته شد،
  ۳) رفتار انتخاب‌شده را روی سفارش واقعیِ orders.json تثبیت می‌کند،
  ۴) و هرجا ممکن بوده، عددِ «گزینه‌ی رد‌شده» را هم به‌صورت صریح assert می‌کند
     تا اگر روزی کسی تصمیم را برگرداند، تست دقیقاً بگوید کدام تصمیم عوض شده.

هر ۱۵ بند DECISIONS.md اینجا تست دارد. بند ۴ (تجمیع کامل هزینه‌ها) یک تصمیمِ
«عدم استثنا»ست و علاوه بر تست مستقیم خودش (`test_decision_04_*` روی ORD-1019)،
به‌طور ضمنی توسط تست‌های بندهای ۱، ۳، ۶ و ۷ هم پوشش داده می‌شود.
"""

import pytest

from src import rules
from src.engine import calculate_order, calculate_shipment_fee
from tests.conftest import make_item, make_order


def fee_of(result: dict, seller_id: str) -> int:
    return next(
        s["shipping_fee"] for s in result["shipments"] if s["seller_id"] == seller_id
    )


# ==========================================================================
# بند ۱ — عضویت پلاس: اولویت مطلق، حتی بر قاعده‌ی صریحِ ۶ (کالای حجیم)
# ==========================================================================
def test_decision_01_plus_overrides_bulky_carve_out(real_results):
    """
    ابهام: قاعده‌ی ۶ صراحتاً می‌گوید کالای حجیم «مشمول ارسال رایگان نمی‌شود»،
    اما قاعده‌ی ۴ می‌گوید اعضای پلاس ارسال رایگان دارند. کدام مقدم است؟

    تصمیم: پلاس مقدم است. ORD-1008 (پلاس + کالای حجیم) کاملاً رایگان می‌شود.
    گزینه‌ی رد‌شده: خوانش تحت‌اللفظی قاعده‌ی ۶ → این مرسوله ۱۵۰٬۰۰۰ می‌گرفت.
    """
    result = real_results["ORD-1008"]
    assert result["total_shipping_fee"] == 0
    assert fee_of(result, "SL-5") == 0
    # عددِ گزینه‌ی رد‌شده، برای اینکه اثر تصمیم در تست مستند بماند:
    assert rules.BULKY_FLAT_FEE == 150_000


def test_decision_01_plus_overrides_night_and_cod(real_results):
    """
    ORD-1024: پلاس + حجیم + شبانه + پرداخت در محل، یعنی هر چهار قاعده هم‌زمان.
    تصمیم: همه‌ی مرسوله‌ها صفر می‌شوند، بدون استثنا.
    """
    result = real_results["ORD-1024"]
    assert result["total_shipping_fee"] == 0
    assert all(s["shipping_fee"] == 0 for s in result["shipments"])


def test_decision_01_plus_zeroes_every_shipment_not_just_total(real_results):
    """تصمیم مکمل بند ۱: تک‌تک مرسوله‌ها صفر می‌شوند، نه فقط جمع کل."""
    result = real_results["ORD-1026"]
    assert len(result["shipments"]) == 3
    assert all(s["shipping_fee"] == 0 for s in result["shipments"])


# ==========================================================================
# بند ۲ — آستانه‌ی ۵۰۰٬۰۰۰: بی‌قیدوشرط، و بر مبنای مبلغ خالص
# ==========================================================================
def test_decision_02_threshold_overrides_bulky(real_results):
    """
    ORD-1009: مبلغ خالص ۷۰۰٬۰۰۰ (بالای آستانه) + یک آیتم حجیم.
    تصمیم: رایگانیِ آستانه مقدم است → ۰.
    گزینه‌ی رد‌شده: مرسوله‌ی حجیم ۱۵۰٬۰۰۰ می‌گرفت.
    """
    assert real_results["ORD-1009"]["total_shipping_fee"] == 0


def test_decision_02_threshold_uses_net_amount_not_gross(real_results):
    """
    ORD-1006: ناخالص ۵۲۰٬۰۰۰، تخفیف ۴۰٬۰۰۰، خالص ۴۸۰٬۰۰۰.
    تصمیم: مبنا خالص است → زیر آستانه → رایگان **نیست**.
    گزینه‌ی رد‌شده (مبنای ناخالص): این سفارش رایگان می‌شد (۰ به‌جای ۲۵٬۰۰۰).
    """
    assert real_results["ORD-1006"]["total_shipping_fee"] == 25_000


def test_decision_02_threshold_is_inclusive():
    """مرز: دقیقاً ۵۰۰٬۰۰۰ تومان هم مشمول رایگانی است (≥ نه >)."""
    order = make_order(items=[make_item(unit_price=500_000, quantity=1, discount=0)])
    assert calculate_order(order)["total_shipping_fee"] == 0

    order = make_order(items=[make_item(unit_price=499_999, quantity=1, discount=0)])
    assert calculate_order(order)["total_shipping_fee"] > 0


# ==========================================================================
# بند ۳ — کالای حجیم: ۱۵۰٬۰۰۰ ثابت و مستقل از مقصد/شب/پرداخت
# ==========================================================================
def test_decision_03_bulky_fee_ignores_city_tier(real_results):
    """
    ORD-1010: کالای حجیم به مقصد کرمان (پایه‌ی ۳۵٬۰۰۰).
    تصمیم: خروجی دقیقاً ۱۵۰٬۰۰۰ است.
    گزینه‌ی رد‌شده (جمع‌شدن پایه‌ی مقصد): ۳۵٬۰۰۰ + ۱۵۰٬۰۰۰ = ۱۸۵٬۰۰۰.
    """
    assert real_results["ORD-1010"]["total_shipping_fee"] == 150_000


def test_decision_03_bulky_fee_ignores_night_and_cod():
    """
    سفارش مصنوعی: حجیم + شبانه + پرداخت در محل + مقصد «سایر شهرها».
    تصمیم: باز هم دقیقاً ۱۵۰٬۰۰۰.
    گزینه‌ی رد‌شده (تجمیع کامل): (۵۰٬۰۰۰+۱۵۰٬۰۰۰)×۱٫۱+۱۰٬۰۰۰ = ۲۳۰٬۰۰۰.
    """
    order = make_order(
        created_at="2026-03-14T23:40:00+03:30",
        city_tier="other",
        payment_method="cash_on_delivery",
        items=[make_item(is_bulky=True, weight_grams=40_000, unit_price=100_000)],
    )
    assert calculate_order(order)["total_shipping_fee"] == 150_000


# ==========================================================================
# بند ۴ — سفارش‌های معمولی: تجمیع کامل و بدون اغماض
# ==========================================================================
def test_decision_04_normal_order_stacks_all_costs(real_results):
    """
    ORD-1019: ایرانشهر (`other`) + پرداخت در محل + هر دو مرسوله سنگین.
    تصمیم: پایه + وزن + کارمزد، همگی کامل و بدون کسر روی هم جمع می‌شوند.
      SL-1: وزن ۹۵۰۰ → ۸۵٬۰۰۰ + پایه ۵۰٬۰۰۰ + کارمزد ۱۰٬۰۰۰ = ۱۴۵٬۰۰۰
      SL-2: وزن ۹۰۰۰ → ۸۰٬۰۰۰ + پایه ۵۰٬۰۰۰ + کارمزد ۱۰٬۰۰۰ = ۱۴۰٬۰۰۰
    """
    result = real_results["ORD-1019"]
    assert fee_of(result, "SL-1") == 145_000
    assert fee_of(result, "SL-2") == 140_000
    assert result["total_shipping_fee"] == 200_000  # سقف بند ۵


# ==========================================================================
# بند ۵ — سقف ۲۰۰٬۰۰۰ روی کل سفارش، نه هر مرسوله
# ==========================================================================
def test_decision_05_cap_is_per_order_not_per_shipment(real_results):
    """
    ORD-1017: پنج مرسوله × ۷۵٬۰۰۰ = ۳۷۵٬۰۰۰ خام.
    تصمیم: سقف روی مجموع → ۲۰۰٬۰۰۰.
    گزینه‌ی رد‌شده (سقف per-shipment): هیچ مرسوله‌ای به سقف نمی‌خورد و
    مجموع همان ۳۷۵٬۰۰۰ باقی می‌ماند.
    """
    result = real_results["ORD-1017"]
    raw_sum = sum(s["shipping_fee"] for s in result["shipments"])
    assert raw_sum == 375_000
    assert result["total_shipping_fee"] == 200_000


def test_decision_05_known_limitation_shipments_are_not_rescaled(real_results):
    """
    محدودیت شناخته‌شده و عمدیِ بند ۵: وقتی سقف فعال می‌شود، مقادیر تک‌تک
    `shipments` بازتوزیع نمی‌شوند، پس جمعشان از `total_shipping_fee` بیشتر است.
    این تست عمداً وجود دارد تا این رفتار «تصادفی» به‌نظر نرسد و اگر روزی
    تصمیم عوض شد، آگاهانه عوض شود.
    """
    result = real_results["ORD-1017"]
    assert sum(s["shipping_fee"] for s in result["shipments"]) > result[
        "total_shipping_fee"
    ]


# ==========================================================================
# بند ۶ — ترتیب افزایش شب و کارمزد پرداخت در محل (گزینه‌ی الف)
# ==========================================================================
def test_decision_06_night_multiplier_excludes_cod_fee():
    """
    ابهام: (پایه+وزن)×۱٫۱ + ۱۰٬۰۰۰   یا   (پایه+وزن+۱۰٬۰۰۰)×۱٫۱ ؟
    تصمیم: گزینه‌ی الف — کارمزد پرداخت در محل مشمول ضریب شب نمی‌شود.

    دیتاست اصلی هیچ سفارشی با «شب + پرداخت در محلِ غیرمعاف» ندارد، پس این
    تصمیم فقط با یک سفارش مصنوعی قابل تثبیت است — و دقیقاً به همین دلیل
    داشتنِ این تست ضروری است.
      گزینه‌ی الف : ۱۳۰٬۰۰۰ × ۱٫۱ + ۱۰٬۰۰۰ = ۱۵۳٬۰۰۰  ← انتخاب‌شده
      گزینه‌ی ب  : (۱۳۰٬۰۰۰ + ۱۰٬۰۰۰) × ۱٫۱ = ۱۵۴٬۰۰۰
    """
    order = make_order(
        created_at="2026-03-14T23:40:00+03:30",
        city_tier="other",
        payment_method="cash_on_delivery",
        items=[make_item(weight_grams=9_000, unit_price=10_000)],
    )
    fee = calculate_shipment_fee(order, order["items"])
    assert round(fee) == 153_000
    assert round(fee) != 154_000


# ==========================================================================
# بند ۷ — هزینه‌ی پایه به ازای هر مرسوله، نه هر سفارش
# ==========================================================================
def test_decision_07_base_fee_applied_per_shipment(real_results):
    """
    ORD-1017: پنج فروشنده به مقصد «خاش» (`other`، پایه ۵۰٬۰۰۰).
    تصمیم: پایه ۵ بار اعمال می‌شود (۵ × ۵۰٬۰۰۰ = ۲۵۰٬۰۰۰).
    گزینه‌ی رد‌شده (یک‌بار برای کل سفارش): مجموع پیش از سقف ۲۰۰٬۰۰۰ کمتر می‌شد.
    """
    result = real_results["ORD-1017"]
    assert len(result["shipments"]) == 5
    # هر مرسوله: پایه ۵۰٬۰۰۰ + وزن ۳۵۰۰ گرم → ۲۵٬۰۰۰ = ۷۵٬۰۰۰
    assert all(s["shipping_fee"] == 75_000 for s in result["shipments"])


# ==========================================================================
# بند ۸ — تکیه بر `city_tier` و نه `destination_city`
# ==========================================================================
def test_decision_08_city_tier_wins_over_city_name(real_results):
    """
    ORD-1021: `destination_city` = «تهران» ولی `city_tier` = «other».
    تصمیم: مبنا `city_tier` است → پایه ۵۰٬۰۰۰.
    گزینه‌ی رد‌شده (مبنای نام شهر): ۲۵٬۰۰۰ می‌شد.
    """
    assert real_results["ORD-1021"]["total_shipping_fee"] == 50_000
    assert real_results["ORD-1021"]["total_shipping_fee"] != 25_000


# ==========================================================================
# بند ۹ — گرد کردن
# ==========================================================================
def test_decision_09_rounding_removes_float_artifact(real_results):
    """
    ORD-1011: ۲۵٬۰۰۰ × ۱٫۱ در پایتون برابر ۲۷۵۰۰.۰۰۰۰۰۰۰۰۰۰۰۴ است.
    تصمیم: خروجی همیشه عدد صحیحِ گردشده است.
    """
    result = real_results["ORD-1011"]
    assert result["total_shipping_fee"] == 27_500
    assert isinstance(result["total_shipping_fee"], int)
    assert all(isinstance(s["shipping_fee"], int) for s in result["shipments"])
    assert 25_000 * rules.NIGHT_SURCHARGE_MULTIPLIER != 27_500  # آرتیفکت واقعاً وجود دارد


def test_decision_09_all_output_values_are_integers(real_results):
    """رگرسیون سراسری: هیچ مقدار اعشاری‌ای نباید به خروجی نشت کند."""
    for result in real_results.values():
        assert isinstance(result["total_shipping_fee"], int)
        for shipment in result["shipments"]:
            assert isinstance(shipment["shipping_fee"], int)


# ==========================================================================
# بند ۱۰ — نرمال‌سازی منطقه‌ی زمانی به وقت تهران
# ==========================================================================
def test_decision_10_utc_offset_is_normalised_to_tehran(real_results):
    """
    ORD-1013 تنها سفارشی است که آفستش `+00:00` است، نه `+03:30`.
    تصمیم: زمان پیش از خواندن ساعت به وقت تهران تبدیل می‌شود.
      ۲۳:۰۰ UTC → ۰۲:۳۰ بامداد به وقت تهران → همچنان داخل بازه‌ی شب.
    """
    assert rules.to_business_timezone("2026-03-14T23:00:00+00:00").hour == 2
    assert rules.is_night_order("2026-03-14T23:00:00+00:00") is True
    assert real_results["ORD-1013"]["total_shipping_fee"] == 27_500


def test_decision_10_normalisation_actually_changes_classification():
    """
    مورد بحرانی که دیتاست فعلی ندارد ولی تصمیم را واقعاً می‌سنجد:
    ۲۰:۰۰ به وقت UTC = ۲۳:۳۰ به وقت تهران.
      با نرمال‌سازی (تصمیم ما) : شب  ✅
      بدون نرمال‌سازی (خواندن خام ساعت ۲۰) : روز ❌
    """
    assert rules.to_business_timezone("2026-03-14T20:00:00+00:00").hour == 23
    assert rules.is_night_order("2026-03-14T20:00:00+00:00") is True


def test_decision_10_naive_timestamp_assumed_tehran():
    """اگر رشته اصلاً آفست نداشت، فرض می‌شود از قبل به وقت تهران است."""
    assert rules.is_night_order("2026-03-14T23:40:00") is True
    assert rules.is_night_order("2026-03-14T14:20:00") is False


# ==========================================================================
# بند ۱۱ — `weight_grams` وزن یک واحد است و در `quantity` ضرب می‌شود
# ==========================================================================
def test_decision_11_weight_is_multiplied_by_quantity(real_results):
    """
    ORD-1005: ۳ عدد کالای ۷۰۰ گرمی → وزن مرسوله ۲۱۰۰ گرم، نه ۷۰۰ گرم.
      تصمیم ما : ۱۵٬۰۰۰ (وزن) + ۳۵٬۰۰۰ (پایه) = ۵۰٬۰۰۰
      گزینه‌ی رد‌شده (بدون ضرب در تعداد): ۰ + ۳۵٬۰۰۰ = ۳۵٬۰۰۰
    """
    assert real_results["ORD-1005"]["total_shipping_fee"] == 50_000
    assert real_results["ORD-1005"]["total_shipping_fee"] != 35_000


def test_decision_11_second_affected_order(real_results):
    """
    ORD-1028: ۲ عدد کالای ۹۰۰ گرمی → ۱۸۰۰ گرم.
      تصمیم ما : ۱۰٬۰۰۰ + ۳۵٬۰۰۰ = ۴۵٬۰۰۰   |   گزینه‌ی رد‌شده: ۳۵٬۰۰۰
    """
    assert real_results["ORD-1028"]["total_shipping_fee"] == 45_000


def test_decision_11_consistency_with_unit_price():
    """
    استدلال پشت تصمیم: در همان ردیف آیتم، `unit_price` قیمت **یک واحد** است و
    در `quantity` ضرب می‌شود. اگر `weight_grams` را وزن کل ردیف بگیریم، دو
    فیلدِ هم‌ردیف را با دو قاعده‌ی متفاوت خوانده‌ایم. این تست آن تقارن را تثبیت می‌کند.
    """
    item = make_item(weight_grams=700, quantity=3, unit_price=100_000, discount=0)
    assert rules.item_total_weight_grams(item) == 2_100
    assert rules.items_net_amount([item]) == 300_000


# ==========================================================================
# بند ۱۲ — رفتار در برابر مقادیر ناشناخته‌ی enum
# ==========================================================================
def test_decision_12_unknown_enums_fall_back_conservatively():
    """
    ابهام: اگر روزی `city_tier` یا `payment_method` مقدار جدیدی بگیرد چه؟
    تصمیم: گران‌ترین/محافظه‌کارانه‌ترین حالت، تا پلتفرم متضرر نشود و خطا
    به‌جای crash، به‌صورت هزینه‌ی بیشتر ظاهر شود.
    """
    assert rules.base_fee_for_city_tier("metropolitan") == rules.DEFAULT_BASE_FEE
    assert rules.payment_method_fee("crypto") == rules.CASH_ON_DELIVERY_FEE


# ==========================================================================
# بند ۱۳ — مرسوله‌ی مخلوط (حجیم + غیرحجیم از یک فروشنده)
# ==========================================================================
def test_decision_13_mixed_shipment_is_treated_as_bulky(real_results):
    """
    ORD-1010 / فروشنده SL-5 هم‌زمان یک یخچال حجیم (۴۰ کیلو) و یک کالای
    غیرحجیمِ ۲٬۶ کیلویی دارد. چون هر دو از یک فروشنده‌اند، در یک مرسوله و با
    یک ناوگان ارسال می‌شوند.

    تصمیم: کل مرسوله حجیم تلقی می‌شود → ۱۵۰٬۰۰۰ ثابت؛ وزن کالای غیرحجیم
    در همان عدد جذب می‌شود.
    گزینه‌ی رد‌شده (تفکیک به دو مرسوله‌ی مجزا برای یک فروشنده):
        حجیم ۱۵۰٬۰۰۰ + غیرحجیم (۳۵٬۰۰۰ پایه + ۲۰٬۰۰۰ وزن) = ۲۰۵٬۰۰۰ → با سقف ۲۰۰٬۰۰۰
    """
    result = real_results["ORD-1010"]
    assert len(result["shipments"]) == 1  # یک مرسوله، نه دو تا
    assert result["total_shipping_fee"] == 150_000
    assert result["total_shipping_fee"] != 200_000


def test_decision_13_bulky_absorbs_nonbulky_weight():
    """
    تثبیت پیامد تصمیم ۱۳ به‌صورت مستقیم: افزودن یک کالای غیرحجیمِ سنگین به
    مرسوله‌ی حجیم، هزینه را تغییر نمی‌دهد.
    """
    only_bulky = [make_item(is_bulky=True, weight_grams=40_000)]
    mixed = [
        make_item(is_bulky=True, weight_grams=40_000),
        make_item(item_id="IT-X", is_bulky=False, weight_grams=9_000),
    ]
    order = make_order()
    assert calculate_shipment_fee(order, only_bulky) == calculate_shipment_fee(
        order, mixed
    )


# ==========================================================================
# بند ۱۴ — مرزهای بازه‌ی شب: ۲۳:۰۰ شامل، ۰۶:۰۰ غیرشامل
# ==========================================================================
def test_decision_14_six_am_is_daytime(real_results):
    """
    ابهام: عبارت «بین ۲۳:۰۰ تا ۰۶:۰۰» دو سرِ بازه را روشن نکرده.
    تصمیم: [۲۳:۰۰، ۰۶:۰۰) — یعنی ۲۳:۰۰ شب، ۰۶:۰۰ روز.
    ORD-1012 دقیقاً ساعت ۰۶:۰۰ ثبت شده و عمداً همین مرز را می‌سنجد.
      تصمیم ما : ۲۵٬۰۰۰ (بدون افزایش)
      گزینه‌ی رد‌شده (۰۶:۰۰ هم شب) : ۲۷٬۵۰۰
    """
    assert real_results["ORD-1012"]["total_shipping_fee"] == 25_000
    assert real_results["ORD-1012"]["total_shipping_fee"] != 27_500


# ==========================================================================
# بند ۱۵ — `discount` تخفیف کل ردیف است، نه تخفیف هر واحد
# ==========================================================================
def test_decision_15_discount_is_line_level_not_per_unit():
    """
    ابهام: در ردیفی با `quantity: 2` و `discount: 60000`، آیا تخفیف ۶۰٬۰۰۰ برای
    کل ردیف است یا ۶۰٬۰۰۰ برای هر واحد (جمعاً ۱۲۰٬۰۰۰)؟

    تصمیم: تخفیف در سطح ردیف است و در `quantity` ضرب نمی‌شود.
      تصمیم ما : ۶۰۰٬۰۰۰ − ۶۰٬۰۰۰ = ۵۴۰٬۰۰۰ ≥ ۵۰۰٬۰۰۰ → ارسال رایگان
      گزینه‌ی رد‌شده : ۶۰۰٬۰۰۰ − ۱۲۰٬۰۰۰ = ۴۸۰٬۰۰۰ → رایگان نمی‌شد

    دیتاست فعلی موردی ندارد که این دو تفسیر نتیجه را عوض کند (ORD-1028 و
    ORD-1023 با هر دو خوانش یک نتیجه می‌دهند)، پس تست مصنوعی است.
    """
    items = [make_item(unit_price=300_000, quantity=2, discount=60_000)]
    assert rules.items_net_amount(items) == 540_000
    assert calculate_order(make_order(items=items))["total_shipping_fee"] == 0


# ==========================================================================
# تست‌های سلامت ساختار خروجی
# ==========================================================================
@pytest.mark.parametrize("order_id", ["ORD-1001", "ORD-1017", "ORD-1024"])
def test_output_schema(real_results, order_id):
    """خروجی باید دقیقاً همان ساختاری باشد که PDF تمرین تعریف کرده."""
    result = real_results[order_id]
    assert set(result) == {"order_id", "shipments", "total_shipping_fee"}
    for shipment in result["shipments"]:
        assert set(shipment) == {"seller_id", "shipping_fee"}


def test_one_shipment_per_seller(real_orders, real_results):
    """قاعده‌ی ۲: تعداد مرسوله‌ها = تعداد فروشنده‌های یکتای آن سفارش."""
    for order in real_orders:
        expected = len({item["seller_id"] for item in order["items"]})
        assert len(real_results[order["order_id"]]["shipments"]) == expected


def test_no_order_exceeds_cap(real_results):
    """هیچ سفارشی نباید از سقف ۲۰۰٬۰۰۰ عبور کند."""
    for result in real_results.values():
        assert 0 <= result["total_shipping_fee"] <= rules.ORDER_SHIPPING_FEE_CAP
