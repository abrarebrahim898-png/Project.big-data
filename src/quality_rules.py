from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
ARABIC_DECIMAL = str.maketrans("٫٬", ".,")

STATUS_MAP = {
    "مؤكد": "CONFIRMED", "confirmed": "CONFIRMED", "CONFIRMED": "CONFIRMED",
    "قيد الانتظار": "PENDING", "pending": "PENDING", "PENDING": "PENDING",
    "قيد الشحن": "SHIPPED", "shipped": "SHIPPED", "SHIPPED": "SHIPPED",
    "تم التسليم": "DELIVERED", "delivered": "DELIVERED", "DELIVERED": "DELIVERED",
    "ملغي": "CANCELLED", "cancelled": "CANCELLED", "CANCELLED": "CANCELLED", "canceled": "CANCELLED",
    "مرتجع": "RETURNED", "returned": "RETURNED", "RETURNED": "RETURNED",
}

PAYMENT_STATUS_MAP = {
    "تم الدفع": "PAID", "paid": "PAID", "PAID": "PAID",
    "بانتظار الدفع": "PENDING", "pending": "PENDING", "PENDING": "PENDING",
    "ملغي": "CANCELLED", "cancelled": "CANCELLED", "CANCELLED": "CANCELLED", "canceled": "CANCELLED",
    "فشل الدفع": "FAILED", "failed": "FAILED", "FAILED": "FAILED",
}

NUMBER_WORDS = {
    "ألف": 1000.0, "الف": 1000.0,
    "ألفان": 2000.0, "الفان": 2000.0,
    "ألفين": 2000.0, "الفين": 2000.0,
    "ثلاثة آلاف": 3000.0, "ثلاثة الاف": 3000.0, "ثلاثه آلاف": 3000.0, "ثلاثه الاف": 3000.0,
    "أربعة آلاف": 4000.0, "اربعة الاف": 4000.0, "اربعه آلاف": 4000.0, "اربعه الاف": 4000.0,
    "خمسة آلاف": 5000.0, "خمسه آلاف": 5000.0, "خمسة الاف": 5000.0, "خمسه الاف": 5000.0,
    "ستة آلاف": 6000.0, "سته آلاف": 6000.0, "ستة الاف": 6000.0, "سته الاف": 6000.0,
    "سبعة آلاف": 7000.0, "سبعه آلاف": 7000.0, "سبعة الاف": 7000.0, "سبعه الاف": 7000.0,
    "ثمانية آلاف": 8000.0, "ثمانيه آلاف": 8000.0, "ثمانية الاف": 8000.0, "ثمانيه الاف": 8000.0,
    "تسعة آلاف": 9000.0, "تسعه آلاف": 9000.0, "تسعة الاف": 9000.0, "تسعه الاف": 9000.0,
    "عشرة آلاف": 10000.0, "عشرة الاف": 10000.0, "عشره آلاف": 10000.0, "عشره الاف": 10000.0,
}


def normalize_arabic_digits(value: Any) -> str | None:
    if value is None:
        return None
    return str(value).translate(ARABIC_DIGITS).translate(PERSIAN_DIGITS).translate(ARABIC_DECIMAL)


def normalize_spaces(value: Any) -> str | None:
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_currency(value: Any) -> str | None:
    if value is None:
        return None
    v = normalize_spaces(value)
    if not v:
        return None
    if v.lower() in {"yer", "ريال", "ريال يمني", "ر.ي", "ريالاً", "ريالا", "riyal"}:
        return "YER"
    return v.upper()


def clean_numeric_price(value: Any) -> float | None:
    if value is None:
        return None
    raw = normalize_spaces(value)
    if not raw or raw in {"???", "null", "none", "nan", "n/a", "unknown"}:
        return None
    v = normalize_spaces(normalize_arabic_digits(raw))
    if v in NUMBER_WORDS:
        return float(NUMBER_WORDS[v])
    # Strip currency words and symbols
    v = re.sub(r"(ريال يمني|ريال|YER|ر\.ي)", "", v, flags=re.I)
    v = v.replace(",", "").strip()
    try:
        val = float(v)
        return val
    except (TypeError, ValueError):
        return None


def normalize_phone(value: Any) -> str | None:
    if value is None:
        return None
    raw = normalize_spaces(value)
    if not raw:
        return None
    v = normalize_spaces(normalize_arabic_digits(raw))
    v = re.sub(r"[\s\-()]", "", v)
    if v.startswith("00967"):
        return "+967" + v[5:]
    if v.startswith("967") and not v.startswith("+"):
        return "+" + v
    if v.startswith("07"):
        return "+967" + v[1:]
    if v.startswith("7") and len(v) == 9:
        return "+967" + v
    return v


def clean_email(value: Any) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    original = normalize_spaces(value)
    if not original:
        return None, False
    # Correct obvious repeated symbols: @@ -> @, .. -> .
    corrected = re.sub(r"@+", "@", original)
    corrected = re.sub(r"\.+", ".", corrected).lower()
    ok = bool(re.fullmatch(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", corrected))
    return (corrected, corrected != original) if ok else (None, False)


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    raw = normalize_spaces(normalize_arabic_digits(value))
    if not raw:
        return None

    # Check for ISO format: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ].*)?$", raw)
    if m:
        y, mo, d = map(int, m.groups())
        if 2000 <= y <= 2030:
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                return None
        return None

    # Check for slash format: YYYY/MM/DD
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})(?:[T ].*)?$", raw)
    if m:
        y, mo, d = map(int, m.groups())
        if 2000 <= y <= 2030:
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                return None
        return None

    # Check for DD/MM/YYYY or DD-MM-YYYY format (e.g. 31/01/2025 as in specs)
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[T ].*)?$", raw)
    if m:
        d, mo, y = map(int, m.groups())
        if 2000 <= y <= 2030:
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                return None
        return None

    return None


def normalize_status(value: Any) -> str | None:
    if value is None:
        return None
    v = normalize_spaces(value)
    if not v:
        return None
    return STATUS_MAP.get(v, v.upper())


def normalize_payment_status(value: Any) -> str | None:
    if value is None:
        return None
    v = normalize_spaces(value)
    if not v:
        return None
    return PAYMENT_STATUS_MAP.get(v, v.upper())


def parse_items(value: Any) -> tuple[list[dict[str, Any]] | None, str | None]:
    if value is None or normalize_spaces(value) in {"", "[]", "null", "none"}:
        return None, "ITEMS_EMPTY"
    if isinstance(value, list):
        items = value
    else:
        try:
            items = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, "CORRUPTED_ITEMS_JSON"
    if not isinstance(items, list) or len(items) == 0:
        return None, "ITEMS_EMPTY"

    normalized_items = []
    for item in items:
        if not isinstance(item, dict):
            return None, "CORRUPTED_ITEMS_JSON"
        sku = str(item.get("sku") or item.get("item_id") or "UNKNOWN").strip()
        name = str(item.get("name") or item.get("item_name") or sku).strip()
        qty = item.get("qty") if "qty" in item else item.get("quantity", 1)
        price = item.get("unit_price") if "unit_price" in item else item.get("price", 0.0)

        try:
            qty_num = float(normalize_arabic_digits(qty))
            price_num = float(normalize_arabic_digits(price))
        except (TypeError, ValueError):
            return None, "CORRUPTED_ITEMS_JSON"

        if qty_num < 0 or price_num < 0:
            return None, "VALUE_NEGATIVE_AMBIGUOUS"

        normalized_items.append({
            "sku": sku,
            "name": name,
            "qty": int(qty_num) if qty_num.is_integer() else qty_num,
            "unit_price": price_num,
            "total": round(qty_num * price_num, 2),
        })
    return normalized_items, None


def calculate_items_total(items: list[dict[str, Any]]) -> float | None:
    total = 0.0
    for item in items:
        qty = item.get("qty")
        unit = item.get("unit_price")
        if not isinstance(qty, (int, float)) or not isinstance(unit, (int, float)):
            return None
        if qty < 0 or unit < 0:
            return None
        total += qty * unit
    return round(total, 2)


def find_column(record: dict[str, Any], names: list[str]) -> str | None:
    for name in names:
        if name in record:
            return name
    return None


def clean_order(raw: dict[str, Any]) -> tuple[dict[str, Any], str, list[dict[str, Any]], list[str]]:
    record = dict(raw)
    corrections = []
    errors = []

    def correct(field: str, new_value: Any, rule_code: str):
        old = record.get(field)
        if new_value is None or str(new_value) == str(old):
            return
        corrections.append({
            "field": field,
            "original_value": old,
            "corrected_value": new_value,
            "rule_code": rule_code,
        })
        record[field] = new_value

    # 1. Arabic / Persian digits normalization across string fields
    for field, value in list(record.items()):
        if isinstance(value, str) and field not in {"items_json", "items"}:
            norm_digits = normalize_arabic_digits(value)
            if norm_digits != value:
                correct(field, norm_digits, "ARABIC_DIGITS")

    # 2. Trim and normalize spaces
    for field, value in list(record.items()):
        if isinstance(value, str) and field not in {"items_json", "items"}:
            norm_space = normalize_spaces(record[field])
            if norm_space != record[field]:
                correct(field, norm_space, "TRIM_NORMALIZE_SPACES")

    # 3. Email Cleaning & Validation
    email_field = find_column(record, ["customer_email", "email", "customerEmail"])
    if email_field:
        email_val = record.get(email_field)
        if email_val and str(email_val).strip() != "":
            nv, changed = clean_email(email_val)
            if nv is not None:
                if changed:
                    correct(email_field, nv, "EMAIL_REPEATED_SYMBOLS")
                else:
                    record[email_field] = nv
            else:
                # Invalid email that cannot be repaired safely must be quarantined
                errors.append("EMAIL_INVALID")

    # 4. Phone Normalization
    phone_field = find_column(record, ["phone", "customer_phone", "customerPhone"])
    if phone_field:
        phone_val = record.get(phone_field)
        if phone_val and str(phone_val).strip() != "":
            nv = normalize_phone(phone_val)
            if nv is not None and nv != phone_val:
                correct(phone_field, nv, "PHONE_NORMALIZATION")

    # 5. Date Standardization & Boundary Check
    date_field = find_column(record, ["order_date", "date", "orderDate"])
    if date_field:
        orig_date = record.get(date_field)
        if orig_date is not None and normalize_spaces(orig_date) != "":
            nv = normalize_date(orig_date)
            if nv:
                if nv != orig_date:
                    correct(date_field, nv, "DATE_STANDARDIZATION")
            else:
                errors.append("DATE_IMPOSSIBLE_INVALID")
        else:
            errors.append("DATE_IMPOSSIBLE_INVALID")
    else:
        errors.append("DATE_IMPOSSIBLE_INVALID")

    # 6. Currency Normalization
    currency_field = find_column(record, ["currency", "Currency"])
    if currency_field:
        curr_val = record.get(currency_field)
        if curr_val is not None:
            nv = normalize_currency(curr_val)
            if nv is not None and nv != curr_val:
                correct(currency_field, nv, "CURRENCY_NORMALIZATION")

    # 7. Price Fields Normalization
    for price_name in ["delivery_cost", "payment_amount", "total_amount", "price", "unit_price"]:
        if price_name in record:
            raw_p = record.get(price_name)
            if raw_p is not None and normalize_spaces(raw_p) != "":
                nv = clean_numeric_price(raw_p)
                if nv is not None:
                    if nv < 0:
                        errors.append("VALUE_NEGATIVE_AMBIGUOUS")
                    elif str(nv) != str(raw_p):
                        correct(price_name, nv, "PRICE_NUMERIC_NORMALIZATION")
                else:
                    errors.append("PRICE_UNKNOWN")

    # 8. Status and Payment Status Normalization
    status_field = find_column(record, ["status", "order_status"])
    if status_field:
        status_val = record.get(status_field)
        if status_val is not None:
            nv = normalize_status(status_val)
            if nv is not None and nv != status_val:
                correct(status_field, nv, "STATUS_STANDARDIZATION")

    pay_status_field = find_column(record, ["payment_status"])
    if pay_status_field:
        pay_status_val = record.get(pay_status_field)
        if pay_status_val is not None:
            nv = normalize_payment_status(pay_status_val)
            if nv is not None and nv != pay_status_val:
                correct(pay_status_field, nv, "PAYMENT_STATUS_STANDARDIZATION")

    # 9. Items JSON Validation and Total Recalculation
    items_field = find_column(record, ["items_json", "items"])
    items = None
    if items_field:
        items, item_error = parse_items(record.get(items_field))
        if item_error:
            errors.append(item_error)
        else:
            record["items"] = items
            calc_total = calculate_items_total(items)
            if calc_total is None:
                errors.append("VALUE_NEGATIVE_AMBIGUOUS")
            else:
                total_field = find_column(record, ["total_amount", "total_price"])
                delivery_field = find_column(record, ["delivery_cost", "delivery_fee"])
                if total_field:
                    deliv_val = clean_numeric_price(record.get(delivery_field)) if delivery_field else 0.0
                    expected_total = round(calc_total + (deliv_val or 0.0), 2)
                    cur_total = clean_numeric_price(record.get(total_field))
                    if cur_total is not None and abs(cur_total - expected_total) > 0.01:
                        correct(total_field, expected_total, "TOTAL_RECALCULATION")
                    elif cur_total is None:
                        correct(total_field, expected_total, "TOTAL_RECALCULATION")
    else:
        errors.append("ITEMS_EMPTY")

    # 10. Required Business Keys (Order ID & Customer ID)
    order_id_field = find_column(record, ["order_id", "id_order", "orderId"])
    order_id_val = record.get(order_id_field) if order_id_field else None
    if not order_id_val or normalize_spaces(order_id_val) in {"", "null", "none", "nan", "n/a"}:
        errors.append("MISSING_ORDER_ID")

    customer_id_field = find_column(record, ["customer_id", "id_customer", "customerId"])
    customer_id_val = record.get(customer_id_field) if customer_id_field else None
    if not customer_id_val or normalize_spaces(customer_id_val) in {"", "null", "none", "nan", "n/a"}:
        errors.append("MISSING_CUSTOMER_ID")

    # 11. Multi-conflict Error Rule
    unique_errors = list(dict.fromkeys(errors))
    fatal_errors = [e for e in unique_errors if e in {
        "MISSING_ORDER_ID", "MISSING_CUSTOMER_ID", "DATE_IMPOSSIBLE_INVALID",
        "CORRUPTED_ITEMS_JSON", "ITEMS_EMPTY", "PRICE_UNKNOWN",
        "VALUE_NEGATIVE_AMBIGUOUS", "EMAIL_INVALID", "DUPLICATE_ORDER_ID"
    }]
    if len(fatal_errors) >= 2:
        unique_errors.append("ERRORS_CONFLICTING_MULTIPLE")
        unique_errors = list(dict.fromkeys(unique_errors))

    if unique_errors:
        status = "quarantined"
    elif corrections:
        status = "corrected"
    else:
        status = "valid"

    return record, status, corrections, unique_errors


def get_order_id(record: dict[str, Any]) -> str | None:
    for name in ["order_id", "id_order", "orderId"]:
        if name in record and record[name] is not None:
            val = str(record[name]).strip()
            if val and val.lower() not in {"null", "none", "nan", "n/a"}:
                return val
    return None
