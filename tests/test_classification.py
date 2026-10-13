from __future__ import annotations

import pytest
from src.quality_rules import clean_order


def test_missing_order_id():
    raw = {
        "order_id": "",
        "customer_id": "CUST-001",
        "order_date": "2025-01-15",
        "total_amount": "5000",
        "items_json": '[{"sku":"SKU-1","qty":1,"unit_price":5000}]'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "MISSING_ORDER_ID" in errors


def test_missing_customer_id():
    raw = {
        "order_id": "ORD-001",
        "customer_id": "   ",
        "order_date": "2025-01-15",
        "total_amount": "5000",
        "items_json": '[{"sku":"SKU-1","qty":1,"unit_price":5000}]'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "MISSING_CUSTOMER_ID" in errors


def test_impossible_date():
    raw = {
        "order_id": "ORD-001",
        "customer_id": "CUST-001",
        "order_date": "1890-05-12",
        "total_amount": "5000",
        "items_json": '[{"sku":"SKU-1","qty":1,"unit_price":5000}]'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "DATE_IMPOSSIBLE_INVALID" in errors


def test_corrupted_items_json():
    raw = {
        "order_id": "ORD-001",
        "customer_id": "CUST-001",
        "order_date": "2025-01-15",
        "total_amount": "5000",
        "items_json": '[{bad_json_not_quoted'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "CORRUPTED_ITEMS_JSON" in errors


def test_empty_items():
    raw = {
        "order_id": "ORD-001",
        "customer_id": "CUST-001",
        "order_date": "2025-01-15",
        "total_amount": "5000",
        "items_json": '[]'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "ITEMS_EMPTY" in errors


def test_unknown_price():
    raw = {
        "order_id": "ORD-001",
        "customer_id": "CUST-001",
        "order_date": "2025-01-15",
        "total_amount": "???",
        "items_json": '[]'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "PRICE_UNKNOWN" in errors


def test_ambiguous_negative_value():
    raw = {
        "order_id": "ORD-001",
        "customer_id": "CUST-001",
        "order_date": "2025-01-15",
        "total_amount": "-5000",
        "items_json": '[{"sku":"SKU-1","qty":-2,"unit_price":2500}]'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "VALUE_NEGATIVE_AMBIGUOUS" in errors


def test_multiple_conflicting_errors():
    raw = {
        "order_id": "",
        "customer_id": "",
        "order_date": "invalid-date",
        "total_amount": "???",
        "items_json": 'not_json'
    }
    record, status, corrections, errors = clean_order(raw)
    assert status == "quarantined"
    assert "ERRORS_CONFLICTING_MULTIPLE" in errors
    assert len(errors) >= 3
