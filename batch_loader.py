import csv
import time
from datetime import datetime, timezone


def python_batch_load(file_path, raw_collection, id_run, batch_size=5000):
    total_rows = total_loaded = batches = 0
    batch = []
    batch_metrics = []

    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_number, row in enumerate(reader, start=2):
            batch.append({
                "id_run": id_run,
                "file_source": str(file_path),
                "number_row_source": row_number,
                "at_ingested": datetime.now(timezone.utc),
                "engine_used": "python_batch",
                "record_raw": dict(row),
            })
            total_rows += 1
            if len(batch) >= batch_size:
                t0 = time.perf_counter()
                result = raw_collection.insert_many(batch, ordered=False)
                elapsed = max(time.perf_counter() - t0, 1e-9)
                inserted = len(result.inserted_ids)
                total_loaded += inserted
                batches += 1
                batch_metrics.append({
                    "batch_number": batches,
                    "records": len(batch),
                    "seconds": round(elapsed, 4),
                    "throughput_rows_sec": round(len(batch) / elapsed, 2),
                })
                print(f"Batch {batches}: {len(batch):,} records | {elapsed:.2f}s | {len(batch)/elapsed:,.0f} rows/s")
                batch.clear()
        if batch:
            t0 = time.perf_counter()
            result = raw_collection.insert_many(batch, ordered=False)
            elapsed = max(time.perf_counter() - t0, 1e-9)
            inserted = len(result.inserted_ids)
            total_loaded += inserted
            batches += 1
            batch_metrics.append({
                "batch_number": batches,
                "records": len(batch),
                "seconds": round(elapsed, 4),
                "throughput_rows_sec": round(len(batch) / elapsed, 2),
            })
            print(f"Batch {batches}: {len(batch):,} records | {elapsed:.2f}s | {len(batch)/elapsed:,.0f} rows/s")

    return {"read_rows": total_rows, "loaded_raw": total_loaded, "batches": batches, "batch_metrics": batch_metrics}
