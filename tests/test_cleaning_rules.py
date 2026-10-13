from __future__ import annotations

import pytest
from src.quality_rules import (
    clean_numeric_price,
    clean_order,
    normalize_arabic_digits,
    normalize_currency,
    normalize_date,
    normalize_phone,
    normalize_status,
    clean_email,
)


def test_arabic_and_persian_digits_normalization():
    assert normalize_arabic_digits("٥٠٠٠") == "5000"
    assert normalize_arabic_digits("١٢٣") == "123"
    assert normalize_arabic_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789"
    assert normalize_arabic_digits("٥٢٠٠٠٫٥") == "52000.5"


def test_currency_normalization():
    assert normalize_currency("ريال") == "YER"
    assert normalize_currency("ريال يمني") == "YER"
    assert normalize_currency("ر.ي") == "YER"
    assert normalize_currency("YER") == "YER"
    assert normalize_currency("yer") == "YER"


def test_clean_numeric_price_thousands_and_words():
    # Thousands comma
    assert clean_numeric_price("125,000.00") == 125000.0
    # Arabic digits with comma and currency
    assert clean_numeric_price("٨,٥٠٠ YER") == 8500.0
    # Number words
    assert clean_numeric_price("ألفان") == 2000.0
    assert clean_numeric_price("خمسة آلاف") == 5000.0
    assert clean_numeric_price("عشرة آلاف") == 10000.0


def test_yemeni_phone_normalization():
    # Spaced with +967
    assert normalize_phone("+967 77 123 4567") == "+967771234567"
    # Leading 07
    assert normalize_phone("0731234567") == "+967731234567"
    # Leading 00967
    assert normalize_phone("00967781234567") == "+967781234567"
    # Plain 9 digits with 7
    assert normalize_phone("771234567") == "+967771234567"
    # Persian digits phone
    assert normalize_phone("۰۷۳۱۲۳۴۵۶۷") == "+967731234567"


def test_email_repeated_symbols_correction():
    cleaned, changed = clean_email("user@@mail..com")
    assert cleaned == "user@mail.com"
    assert changed is True

    # Already valid
    cleaned, changed = clean_email("ali@example.com")
    assert cleaned == "ali@example.com"
    assert changed is False

    # Irreparable
    cleaned, changed = clean_email("@@")
    assert cleaned is None
    assert changed is False


def test_date_standardization_and_boundaries():
    # Standard ISO
    assert normalize_date("2025-01-31") == "2025-01-31"
    # ISO datetime
    assert normalize_date("2024-03-15T10:30:00Z") == "2024-03-15"
    # Slash format
    assert normalize_date("2025/01/31") == "2025-01-31"
    # Specification example DD/MM/YYYY
    assert normalize_date("31/01/2025") == "2025-01-31"
    assert normalize_date("15/03/2024") == "2024-03-15"

    # Impossible date (year 1890 < 2000)
    assert normalize_date("1890-05-12") is None
    # Impossible date (year 2099 > 2030)
    assert normalize_date("2099-12-31") is None
    # Impossible calendar date (Feb 31)
    assert normalize_date("2025-02-31") is None


def test_status_normalization():
    assert normalize_status("مؤكد") == "CONFIRMED"
    assert normalize_status("قيد الانتظار") == "PENDING"
    assert normalize_status("قيد الشحن") == "SHIPPED"
    assert normalize_status("تم التسليم") == "DELIVERED"
    assert normalize_status("ملغي") == "CANCELLED"
    assert normalize_status("مرتجع") == "RETURNED"


def test_order_audit_trail_generation():
    raw_record = {
        "order_id": "ORD-999",
        "customer_id": "CUST-999",
        "customer_email": "user@@mail..com",
        "order_date": "31/01/2025",
        "status": "مؤكد",
        "total_amount": "4000",
        "delivery_cost": "1000",
        "currency": "ريال يمني",
        "items_json": '[{"sku":"SKU-1","name":"قلم","qty":2,"unit_price":2000}]'
    }

    record, status, corrections, errors = clean_order(raw_record)
    assert status == "corrected"
    assert len(errors) == 0
    assert len(corrections) > 0

    rule_codes = {c["rule_code"] for c in corrections}
    assert "EMAIL_REPEATED_SYMBOLS" in rule_codes
    assert "DATE_STANDARDIZATION" in rule_codes
    assert "STATUS_STANDARDIZATION" in rule_codes
    assert "TOTAL_RECALCULATION" in rule_codes
    assert record["total_amount"] == 5000.0
