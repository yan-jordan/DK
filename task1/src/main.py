"""
main.py — نقطه‌ی ورود برنامه.

اجرا:
    python -m src.main
    python -m src.main --input path/to/orders.json --output path/to/results.json
"""

from __future__ import annotations

import argparse
import sys

from . import io_utils
from .engine import calculate_all


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="موتور محاسبه‌ی هزینه‌ی ارسال «بازار»"
    )
    parser.add_argument(
        "--input",
        default=str(io_utils.DEFAULT_INPUT_PATH),
        help="مسیر فایل ورودی orders.json",
    )
    parser.add_argument(
        "--output",
        default=str(io_utils.DEFAULT_OUTPUT_PATH),
        help="مسیر فایل خروجی results.json",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="چاپ نکردن خلاصه‌ی نتیجه در ترمینال",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    try:
        orders = io_utils.load_orders(args.input)
    except (OSError, ValueError) as exc:
        print(f"خطا در خواندن ورودی: {exc}", file=sys.stderr)
        return 1

    results = calculate_all(orders)
    io_utils.save_results(results, args.output)

    if not args.quiet:
        total = sum(r["total_shipping_fee"] for r in results)
        free_count = sum(1 for r in results if r["total_shipping_fee"] == 0)
        print(f"{len(results)} سفارش پردازش شد.")
        print(f"  ارسال رایگان : {free_count} سفارش")
        print(f"  مجموع هزینه‌ی ارسال : {total:,} تومان")
        print(f"  خروجی نوشته شد در : {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
