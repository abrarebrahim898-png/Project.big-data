from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .quality_rules import clean_order, get_order_id


def process_delta_file(delta_file_path: str | Path, validated_collection, quarantine_collection, watermark_collection) -> dict[str, Any]:
    """
    Path B: Incremental Delta Processing & High-Reliability Idempotent Loader.
    Complies with Midterm Path B requirement:
    - Reads delta records (inserts/updates).
    - Watermark & version handling (latest updated_at or version wins).
    - Idempotent upsert tracking inserted_count, updated_count, unchanged_count.
    - Replaying the same delta file does not produce duplicates.
    """
    path = Path(delta_file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Delta file not found: {path}")

    run_id = f"delta-{uuid4().hex[:8]}"
    inserted = 0
    updated = 0
    unchanged = 0
    quarantined = 0
    latest_timestamp = None
    now_utc = datetime.now(timezone.utc)

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            record, status, corrections, errors = clean_order(dict(row))
            order_id = get_order_id(record)

            if status in ("valid", "corrected") and order_id:
                record["order_id"] = order_id
                doc = {
                    **record,
                    "order_id": order_id,
                    "quality_status": status,
                    "corrections": corrections,
                    "id_run": run_id,
                    "source_delta_file": path.name,
                    "processed_at": now_utc,
                }

                existing = validated_collection.find_one({"order_id": order_id})
                if existing is None:
                    validated_collection.replace_one({"order_id": order_id}, doc, upsert=True)
                    inserted += 1
                else:
                    # Version / updated_at conflict handling: latest version wins
                    new_ver = float(record.get("version") or 1)
                    old_ver = float(existing.get("version") or 1)

                    ignored = {"_id", "id_run", "run_id", "source_delta_file", "processed_at"}
                    cur_biz = {k: v for k, v in doc.items() if k not in ignored}
                    ext_biz = {k: v for k, v in existing.items() if k not in ignored}

                    if cur_biz == ext_biz:
                        unchanged += 1
                    elif new_ver >= old_ver:
                        validated_collection.replace_one({"order_id": order_id}, doc, upsert=True)
                        updated += 1
                    else:
                        # Existing is newer than delta; preserve existing
                        unchanged += 1

                # Track watermark
                order_date = record.get("order_date")
                if order_date and (latest_timestamp is None or str(order_date) > str(latest_timestamp)):
                    latest_timestamp = str(order_date)
            else:
                qdoc = {
                    "id_run": run_id,
                    "source_delta_file": path.name,
                    "row_number": row_num,
                    "raw_record": dict(row),
                    "quality_status": "quarantined",
                    "error_codes": errors,
                    "error_details": "; ".join(errors),
                    "processed_at": now_utc,
                }
                quarantine_collection.insert_one(qdoc)
                quarantined += 1

    if latest_timestamp:
        watermark_collection.update_one(
            {"_id": "delta_high_watermark"},
            {"$set": {"watermark": latest_timestamp, "updated_at": now_utc}},
            upsert=True
        )

    return {
        "run_id": run_id,
        "delta_file": path.name,
        "inserted_count": inserted,
        "updated_count": updated,
        "unchanged_count": unchanged,
        "quarantined_count": quarantined,
        "watermark": latest_timestamp,
    }
