import json
import re
from datetime import datetime

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
ARABIC_DECIMAL = str.maketrans("٫٬", ".,")

STATUS_MAP = {
    "مؤكد": "CONFIRMED", "confirmed": "CONFIRMED", "CONFIRMED": "CONFIRMED",
    "قيد الانتظار": "PENDING", "pending": "PENDING", "PENDING": "PENDING",
    "قيد الشحن": "SHIPPED", "shipped": "SHIPPED", "SHIPPED": "SHIPPED",
    "ملغي": "CANCELLED", "cancelled": "CANCELLED", "CANCELLED": "CANCELLED",
    "مرتجع": "RETURNED", "returned": "RETURNED", "RETURNED": "RETURNED",
}
PAYMENT_STATUS_MAP = {
    "تم الدفع": "PAID", "paid": "PAID", "PAID": "PAID",
    "بانتظار الدفع": "PENDING", "pending": "PENDING", "PENDING": "PENDING",
    "ملغي": "CANCELLED", "cancelled": "CANCELLED", "CANCELLED": "CANCELLED",
}

NUMBER_WORDS = {
    "ألف": 1000, "الف": 1000,
    "ألفان": 2000, "الفان": 2000,
    "ألفين": 2000, "الفين": 2000,
    "خمسة آلاف": 5000, "خمسه آلاف": 5000,
    "خمسة الاف": 5000, "خمسه الاف": 5000,
}


def normalize_arabic_digits(value):
    if value is None:
        return None
    return str(value).translate(ARABIC_DIGITS).translate(ARABIC_DECIMAL)


def normalize_spaces(value):
    if value is None:
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize_currency(value):
    if value is None:
        return None
    v = normalize_spaces(value)
    if v.lower() in {"yer", "ريال", "ريال يمني", "ر.ي", "ريالاً", "ريال يمني"}:
        return "YER"
    return v.upper()


def clean_numeric_price(value):
    if value is None or normalize_spaces(value) == "":
        return None
    v = normalize_spaces(normalize_arabic_digits(value))
    if v in NUMBER_WORDS:
        return float(NUMBER_WORDS[v])
    v = re.sub(r"(ريال يمني|ريال|YER)", "", v, flags=re.I)
    v = v.replace(",", "").strip()
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_phone(value):
    if value is None:
        return None
    v = normalize_spaces(normalize_arabic_digits(value))
    v = re.sub(r"[\s\-()]", "", v)
    if v.startswith("00967"):
        return "+967" + v[5:]
    if v.startswith("967"):
        return "+" + v
    if v.startswith("07"):
        return "+967" + v[1:]
    if v.startswith("7") and len(v) == 9:
        return "+967" + v
    return v


def clean_email(value):
    if value is None:
        return None, False
    original = normalize_spaces(value)
    corrected = original.replace("@@", "@").replace("..", ".").lower()
    ok = bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", corrected))
    return (corrected, corrected != original) if ok else (None, False)


def normalize_date(value):
    if value is None or normalize_spaces(value) == "":
        return None
    raw = normalize_spaces(normalize_arabic_digits(value))
    # Accept ISO datetime/date and common slash formats without guessing ambiguous values.
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$", raw)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{4})/(\d{2})/(\d{2})", raw)
    if m:
        y, mo, d = map(int, m.groups())
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def normalize_status(value):
    if value is None:
        return None
    v = normalize_spaces(value)
    return STATUS_MAP.get(v, v.upper())


def normalize_payment_status(value):
    if value is None:
        return None
    v = normalize_spaces(value)
    return PAYMENT_STATUS_MAP.get(v, v.upper())


def parse_items(value):
    if value is None or normalize_spaces(value) == "":
        return None, "ITEMS_EMPTY"
    try:
        items = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "CORRUPTED_ITEMS_JSON"
    if not isinstance(items, list) or len(items) == 0:
        return None, "ITEMS_EMPTY"
    for item in items:
        if not isinstance(item, dict):
            return None, "CORRUPTED_ITEMS_JSON"
    return items, None


def calculate_items_total(items):
    total = 0.0
    for item in items:
        qty = item.get("qty")
        unit = item.get("unit_price")
        if not isinstance(qty, (int, float)) or not isinstance(unit, (int, float)):
            return None
        if qty < 0:
            return None
        total += qty * unit
    return total


def find_column(record, names):
    for name in names:
        if name in record:
            return name
    return None


def clean_order(raw):
    record = dict(raw)
    corrections = []
    errors = []

    def correct(field, new_value, rule_code):
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

    # 1. Arabic digits.
    for field, value in list(record.items()):
        if isinstance(value, str):
            correct(field, normalize_arabic_digits(value), "ARABIC_DIGITS")

    # 2. Spaces.
    for field, value in list(record.items()):
        if isinstance(value, str):
            correct(field, normalize_spaces(value), "TRIM_NORMALIZE_SPACES")

    # 3. Email.
    email = find_column(record, ["customer_email", "email", "customerEmail"])
    if email:
        nv, changed = clean_email(record[email])
        if nv is not None:
            if changed:
                correct(email, nv, "EMAIL_REPEATED_SYMBOLS")
            else:
                record[email] = nv
        elif record[email]:
            errors.append("EMAIL_INVALID")

    # 4. Phone.
    phone = find_column(record, ["phone", "customer_phone", "customerPhone"])
    if phone:
        nv = normalize_phone(record[phone])
        if nv is not None and nv != record[phone]:
            correct(phone, nv, "PHONE_NORMALIZATION")

    # 5. Date.
    datef = find_column(record, ["order_date", "date", "orderDate"])
    if datef:
        original_date = record[datef]
        if normalize_spaces(original_date) != "":
            nv = normalize_date(original_date)
            if nv:
                correct(datef, nv, "DATE_STANDARDIZATION")
            else:
                errors.append("DATE_IMPOSSIBLE_INVALID")

    # 6. Currency.
    currency = find_column(record, ["currency", "Currency"])
    if currency:
        nv = normalize_currency(record[currency])
        if nv is not None:
            correct(currency, nv, "CURRENCY_NORMALIZATION")

    # 7. Price fields.
    for price_name in ["delivery_cost", "payment_amount", "total_amount", "price", "unit_price"]:
        if price_name in record:
            nv = clean_numeric_price(record[price_name])
            if nv is not None:
                correct(price_name, nv, "PRICE_NUMERIC_NORMALIZATION")
            elif normalize_spaces(record[price_name]) != "":
                errors.append("PRICE_UNKNOWN")

    # 8. Status.
    status = find_column(record, ["status", "order_status"])
    if status:
        nv = normalize_status(record[status])
        if nv is not None:
            correct(status, nv, "STATUS_STANDARDIZATION")

    payment_status = find_column(record, ["payment_status"])
    if payment_status:
        nv = normalize_payment_status(record[payment_status])
        if nv is not None:
            correct(payment_status, nv, "PAYMENT_STATUS_STANDARDIZATION")

    # 9. items_json validation + total calculation.
    items_field = find_column(record, ["items_json", "items"])
    if items_field:
        items, item_error = parse_items(record[items_field])
        if item_error:
            errors.append(item_error)
        else:
            calculated = calculate_items_total(items)
            if calculated is None:
                errors.append("VALUE_NEGATIVE_AMBIGUOUS")
            else:
                total_field = find_column(record, ["total_amount", "total_price"])
                delivery_field = find_column(record, ["delivery_cost", "delivery_fee"])
                if total_field:
                    delivery = clean_numeric_price(record.get(delivery_field)) if delivery_field else 0.0
                    expected = calculated + (delivery or 0.0)
                    current = clean_numeric_price(record.get(total_field))
                    if current is not None and abs(current - expected) > 0.01:
                        correct(total_field, expected, "TOTAL_RECALCULATION")

    # 10. Required business keys.
    order_id = find_column(record, ["order_id", "id_order", "orderId"])
    if not order_id or not normalize_spaces(record.get(order_id)):
        errors.append("MISSING_ORDER_ID")

    customer_id = find_column(record, ["customer_id", "id_customer", "customerId"])
    if customer_id and not normalize_spaces(record.get(customer_id)):
        errors.append("MISSING_CUSTOMER_ID")

    # Deduplicate error codes while preserving order.
    errors = list(dict.fromkeys(errors))

    if errors:
        status = "quarantined"
    elif corrections:
        status = "corrected"
    else:
        status = "valid"

    return record, status, corrections, errors


def get_order_id(record):
    for name in ["order_id", "id_order", "orderId"]:
        if name in record and record[name] is not None and str(record[name]).strip():
            return str(record[name]).strip()
    return None
