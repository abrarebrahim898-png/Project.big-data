from datetime import datetime, timezone
import json
from pymongo import ReplaceOne
from .quality_rules import clean_order, get_order_id


def _utcnow():
    return datetime.now(timezone.utc)


def process_run(raw_collection, validated_collection, quarantine_collection, id_run):
    valid = corrected = quarantine = 0
    counts = {}
    inserted = updated = unchanged = 0

    cursor = raw_collection.find({"id_run": id_run}).sort("number_row_source", 1)

    for raw in cursor:
        record, status, corrections, error_codes = clean_order(raw["record_raw"])
        order_id = get_order_id(record)
        base = {
            "id_run": id_run,
            "file_source": raw["file_source"],
            "number_row_source": raw["number_row_source"],
            "record_raw": raw["record_raw"],
        }

        if status in ("valid", "corrected") and order_id:
            # Canonical business key is always stored in order_id.
            # This avoids conflicts with legacy id_order indexes/documents.
            record["order_id"] = order_id

            # Keep the original CSV field and add a typed array for MongoDB aggregations.
            if isinstance(record.get("items_json"), str):
                try:
                    record["items"] = json.loads(record["items_json"])
                except (TypeError, ValueError, json.JSONDecodeError):
                    record["items"] = []

            doc = {
                **record,
                **base,
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
                # Compare business state, ignoring run-specific timestamps/source metadata.
                ignored = {"_id", "id_run", "file_source", "number_row_source", "processed_at"}
                compare_fields = {k: v for k, v in doc.items() if k not in ignored}
                existing_compare = {k: v for k, v in existing.items() if k not in ignored}
                if existing_compare == compare_fields:
                    unchanged += 1
                else:
                    validated_collection.replace_one({"order_id": order_id}, doc, upsert=True)
                    updated += 1
            if status == "valid":
                valid += 1
            else:
                corrected += 1
            continue

        if not error_codes:
            error_codes = ["MISSING_ORDER_ID"]
        qdoc = {
            **base,
            "quality_status": "quarantined",
            "codes_error": error_codes,
            "details_error": "; ".join(error_codes),
            "processed_at": _utcnow(),
        }
        # Raw attempts may repeat, so quarantine is keyed by run + source row.
        quarantine_collection.replace_one(
            {"id_run": id_run, "number_row_source": raw["number_row_source"]},
            qdoc,
            upsert=True,
        )
        quarantine += 1
        for code in error_codes:
            counts[code] = counts.get(code, 0) + 1

    return {
        "count_valid": valid,
        "count_corrected": corrected,
        "count_quarantine": quarantine,
        "counts_case_error": counts,
        "count_inserted": inserted,
        "count_updated": updated,
        "count_unchanged": unchanged,
    }
