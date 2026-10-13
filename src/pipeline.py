from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from .quality_rules import clean_order, get_order_id


def _utcnow():
    return datetime.now(timezone.utc)


def process_run(raw_collection, validated_collection, quarantine_collection, id_run: str) -> dict[str, Any]:
    """
    Process raw orders for a specific run_id.
    Implements idempotent ELT validation, classification, audit trail, and upsert.
    Strictly satisfies:
    - Consistency equation (6.11): raw_count = valid_count + corrected_count + quarantine_count
    - Idempotency & Upsert (6.10): business duplicates are prevented, repeated runs increase unchanged_count
    """
    valid = 0
    corrected = 0
    quarantine = 0
    inserted = 0
    updated = 0
    unchanged = 0
    counts = {}

    cursor = raw_collection.find({"id_run": id_run}).sort("number_row_source", 1)
    raw_list = list(cursor)
    raw_count = len(raw_list)

    # First pass: check for in-batch duplicate order_ids
    seen_order_ids: dict[str, int] = {}
    duplicate_order_ids = set()
    for raw in raw_list:
        oid = get_order_id(raw.get("record_raw", {}))
        if oid:
            if oid in seen_order_ids:
                duplicate_order_ids.add(oid)
            seen_order_ids[oid] = seen_order_ids.get(oid, 0) + 1

    for raw in raw_list:
        raw_record = raw.get("record_raw") or raw.get("raw_record") or {}
        record, status, corrections, error_codes = clean_order(raw_record)
        order_id = get_order_id(record)

        base_metadata = {
            "id_run": id_run,
            "run_id": id_run,
            "file_source": raw.get("file_source") or raw.get("source_file"),
            "source_file": raw.get("file_source") or raw.get("source_file"),
            "number_row_source": raw.get("number_row_source") or raw.get("source_row_number"),
            "source_row_number": raw.get("number_row_source") or raw.get("source_row_number"),
            "record_raw": raw_record,
            "raw_record": raw_record,
        }

        # If order_id was duplicated within the dirty file with conflicting rows, quarantine it
        if order_id and order_id in duplicate_order_ids and seen_order_ids[order_id] > 1:
            # Check if this duplicate needs review
            if "DUPLICATE_ORDER_ID" not in error_codes:
                error_codes.append("DUPLICATE_ORDER_ID")
                status = "quarantined"

        if status in ("valid", "corrected") and order_id:
            record["order_id"] = order_id

            # Ensure typed items list exists for MongoDB aggregations
            if "items" not in record or not isinstance(record["items"], list):
                if isinstance(record.get("items_json"), str):
                    try:
                        record["items"] = json.loads(record["items_json"])
                    except Exception:
                        record["items"] = []

            # Ensure numeric fields are explicitly typed
            if "total_amount" in record and record["total_amount"] is not None:
                try:
                    record["total_amount"] = float(record["total_amount"])
                except (ValueError, TypeError):
                    pass

            doc = {
                **record,
                **base_metadata,
                "order_id": order_id,
                "quality_status": status,
                "corrections": corrections,
                "processed_at": _utcnow(),
            }

            existing = validated_collection.find_one({"order_id": order_id})
            if existing is None:
                validated_collection.replace_one({"order_id": order_id}, doc, upsert=True)
                inserted += 1
            else:
                # Compare business fields to verify idempotency
                ignored = {
                    "_id", "id_run", "run_id", "file_source", "source_file",
                    "number_row_source", "source_row_number", "processed_at", "at_ingested", "ingested_at"
                }
                current_biz = {k: v for k, v in doc.items() if k not in ignored}
                existing_biz = {k: v for k, v in existing.items() if k not in ignored}

                if current_biz == existing_biz:
                    unchanged += 1
                else:
                    validated_collection.replace_one({"order_id": order_id}, doc, upsert=True)
                    updated += 1

            if status == "valid":
                valid += 1
            else:
                corrected += 1
            continue

        # If not valid/corrected, record is quarantined
        if not error_codes:
            error_codes = ["MISSING_ORDER_ID"]

        # If multiple errors present, flag multiple conflicting errors
        if len(error_codes) >= 2 and "ERRORS_CONFLICTING_MULTIPLE" not in error_codes:
            error_codes.append("ERRORS_CONFLICTING_MULTIPLE")

        qdoc = {
            **base_metadata,
            "quality_status": "quarantined",
            "codes_error": error_codes,
            "error_codes": error_codes,
            "details_error": "; ".join(error_codes),
            "error_details": "; ".join(error_codes),
            "processed_at": _utcnow(),
        }

        # Quarantine is keyed by run + row number
        quarantine_collection.replace_one(
            {
                "id_run": id_run,
                "number_row_source": base_metadata["number_row_source"]
            },
            qdoc,
            upsert=True,
        )
        quarantine += 1
        for code in error_codes:
            counts[code] = counts.get(code, 0) + 1

    # Consistency check verification (Section 6.11):
    # run_raw_count = run_valid_count + run_corrected_count + run_quarantine_count
    consistency_passed = (raw_count == (valid + corrected + quarantine))

    return {
        "raw_count": raw_count,
        "valid_count": valid,
        "corrected_count": corrected,
        "quarantine_count": quarantine,
        "count_valid": valid,
        "count_corrected": corrected,
        "count_quarantine": quarantine,
        "inserted_count": inserted,
        "updated_count": updated,
        "unchanged_count": unchanged,
        "count_inserted": inserted,
        "count_updated": updated,
        "count_unchanged": unchanged,
        "error_case_counts": counts,
        "counts_case_error": counts,
        "consistency_equation_passed": consistency_passed,
    }
