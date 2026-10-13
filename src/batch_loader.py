from __future__ import annotations

import csv
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from pymongo.errors import BulkWriteError


def python_batch_load(file_path: str | Path, raw_collection, run_id: str, batch_size: int = 5000) -> dict[str, Any]:
    """
    Stream a CSV file and load raw records in configurable batches into MongoDB.
    Complies strictly with Section 6.3 of Midterm Specifications:
    - Streaming via csv.DictReader (no list(reader) or full memory load)
    - Configurable batch_size
    - Logs batch number, count, time, and throughput
    - Handles batch errors without concealing failure reasons
    - Preserves pristine raw record
    """
    total_rows = 0
    total_loaded = 0
    batches = 0
    batch_metrics = []
    batch = []
    start_total_time = time.perf_counter()

    file_str = str(Path(file_path).resolve())

    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            now_utc = datetime.now(timezone.utc)
            # Filter out non-string/None keys produced by csv.DictReader on unquoted commas in dirty rows
            clean_raw = {str(k): v for k, v in row.items() if k is not None}
            if None in row and row[None]:
                clean_raw["_unmatched_extra_columns"] = row[None]

            raw_doc = {
                "id_run": run_id,
                "run_id": run_id,
                "file_source": file_str,
                "source_file": file_str,
                "number_row_source": row_number,
                "source_row_number": row_number,
                "at_ingested": now_utc,
                "ingested_at": now_utc,
                "engine_used": "python_batch",
                "record_raw": clean_raw,
                "raw_record": clean_raw,
            }
            batch.append(raw_doc)
            total_rows += 1

            if len(batch) >= batch_size:
                batches += 1
                loaded_in_batch, elapsed = _insert_batch(raw_collection, batch, batches)
                total_loaded += loaded_in_batch
                throughput = round(len(batch) / max(elapsed, 1e-9), 2)
                batch_metrics.append({
                    "batch_number": batches,
                    "records": len(batch),
                    "seconds": round(elapsed, 4),
                    "throughput_rows_sec": throughput,
                })
                print(f"Batch {batches}: {len(batch):,} records | {elapsed:.2f}s | {throughput:,.0f} rows/s")
                batch.clear()

        if batch:
            batches += 1
            loaded_in_batch, elapsed = _insert_batch(raw_collection, batch, batches)
            total_loaded += loaded_in_batch
            throughput = round(len(batch) / max(elapsed, 1e-9), 2)
            batch_metrics.append({
                "batch_number": batches,
                "records": len(batch),
                "seconds": round(elapsed, 4),
                "throughput_rows_sec": throughput,
            })
            print(f"Batch {batches}: {len(batch):,} records | {elapsed:.2f}s | {throughput:,.0f} rows/s")
            batch.clear()

    total_elapsed = max(time.perf_counter() - start_total_time, 1e-9)
    overall_throughput = round(total_loaded / total_elapsed, 2)

    return {
        "rows_read": total_rows,
        "raw_loaded": total_loaded,
        "read_rows": total_rows,
        "loaded_raw": total_loaded,
        "batches": batches,
        "batch_metrics": batch_metrics,
        "elapsed_seconds": round(total_elapsed, 4),
        "throughput": overall_throughput,
    }


def _insert_batch(raw_collection, batch: list[dict[str, Any]], batch_num: int) -> tuple[int, float]:
    t0 = time.perf_counter()
    try:
        result = raw_collection.insert_many(batch, ordered=False)
        elapsed = time.perf_counter() - t0
        return len(result.inserted_ids), elapsed
    except BulkWriteError as bwe:
        elapsed = time.perf_counter() - t0
        inserted = bwe.details.get("nInserted", 0)
        write_errors = bwe.details.get("writeErrors", [])
        print(f"Warning: Batch {batch_num} encountered {len(write_errors)} write errors: {write_errors[:2]}")
        return inserted, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"Error inserting batch {batch_num}: {exc}")
        raise
