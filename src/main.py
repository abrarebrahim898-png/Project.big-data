from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv

from .batch_loader import python_batch_load
from .mongo import connect, setup_collections, setup_schema_validation
from .pipeline import process_run
from .router import choose_engine, create_router

load_dotenv()


def ingest_file(db, input_file: str, batch_size: int = 5000, threshold_mb: float = 200.0) -> dict:
    """
    Unified Ingestion & ELT Pipeline entrypoint.
    Complies with Midterm Sections 4, 6.2, 6.3, 6.4, 6.5, 6.10, 6.11, 6.12:
    - Automatic engine routing based on file size
    - Raw load without drop or pre-filtering
    - Cleaning, classification, audit trail, idempotent upsert
    - Generates reports/results.json
    """
    file_path = Path(input_file).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    raw_col_name = os.getenv("RAW_COLLECTION", "orders_raw")
    val_col_name = os.getenv("VALIDATED_COLLECTION", "orders_validated")
    quar_col_name = os.getenv("QUARANTINE_COLLECTION", "orders_quarantine")

    raw, validated, quarantine = setup_collections(db, raw_col_name, val_col_name, quar_col_name)
    try:
        setup_schema_validation(db, val_col_name)
    except Exception:
        pass

    run_id = f"run-{uuid4().hex[:8]}"
    engine_decision = choose_engine(file_path, threshold_mb)
    chosen_engine = engine_decision["engine"]

    start_time = time.perf_counter()

    if chosen_engine == "python_batch":
        load_result = python_batch_load(file_path, raw, run_id, batch_size)
    else:
        try:
            from .spark_loader import spark_batch_load
            load_result = spark_batch_load(file_path, db, run_id)
        except Exception as exc:
            print(f"Warning: PySpark execution failed ({exc}). Falling back to streaming Python batch loader.")
            load_result = python_batch_load(file_path, raw, run_id, batch_size)
            chosen_engine = "python_batch_fallback"

    process_result = process_run(raw, validated, quarantine, run_id)
    total_elapsed = round(max(time.perf_counter() - start_time, 1e-9), 4)
    rows_read = load_result.get("rows_read", 0)
    overall_throughput = round(rows_read / max(total_elapsed, 1e-9), 2)

    # Compile official metrics required by Section 6.12
    metrics = {
        "run_id": run_id,
        "id_run": run_id,
        "file_name": file_path.name,
        "file_size_mb": engine_decision["file_size_mb"],
        "engine_used": chosen_engine,
        "rows_read": rows_read,
        "raw_loaded": load_result.get("raw_loaded", 0),
        "valid_count": process_result["valid_count"],
        "corrected_count": process_result["corrected_count"],
        "quarantine_count": process_result["quarantine_count"],
        "count_valid": process_result["valid_count"],
        "count_corrected": process_result["corrected_count"],
        "count_quarantine": process_result["quarantine_count"],
        "elapsed_seconds": total_elapsed,
        "throughput": overall_throughput,
        "batch_size": batch_size,
        "error_case_counts": process_result["error_case_counts"],
        "counts_case_error": process_result["error_case_counts"],
        "inserted_count": process_result["inserted_count"],
        "updated_count": process_result["updated_count"],
        "unchanged_count": process_result["unchanged_count"],
        "count_inserted": process_result["inserted_count"],
        "count_updated": process_result["updated_count"],
        "count_unchanged": process_result["unchanged_count"],
        "consistency_equation": {
            "equation": "run_raw_count = run_valid_count + run_corrected_count + run_quarantine_count",
            "raw_count": process_result["raw_count"],
            "sum_processed": process_result["valid_count"] + process_result["corrected_count"] + process_result["quarantine_count"],
            "passed": process_result["consistency_equation_passed"],
        },
    }

    # Save metrics to reports/results.json
    try:
        reports_dir = Path(__file__).resolve().parent.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        results_file = reports_dir / "results.json"
        with open(results_file, "w", encoding="utf-8") as rf:
            json.dump(metrics, rf, ensure_ascii=False, indent=2, default=str)
        print(f"Metrics saved successfully to {results_file}")
    except Exception as e:
        print(f"Note: Could not save reports/results.json: {e}")

    return {
        "status": "success",
        "run_id": run_id,
        "engine": engine_decision,
        "metrics": metrics,
        "load_result": load_result,
        "process_result": process_result,
    }


def create_app():
    from fastapi import FastAPI
    from .jobs import start_scheduler

    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    database = os.getenv("MONGO_DATABASE", "orders_db")
    client, db = connect(uri, database)

    setup_collections(
        db,
        os.getenv("RAW_COLLECTION", "orders_raw"),
        os.getenv("VALIDATED_COLLECTION", "orders_validated"),
        os.getenv("QUARANTINE_COLLECTION", "orders_quarantine")
    )
    try:
        setup_schema_validation(db, os.getenv("VALIDATED_COLLECTION", "orders_validated"))
    except Exception:
        pass

    app = FastAPI(
        title="Orders Data Engineering API",
        version="2.0.0",
        description="Hybrid Data Pipeline & Big Data Phase 2 Unified API"
    )

    def _ingest_callback(payload: dict):
        input_file = payload.get("input_file")
        if not input_file:
            raise ValueError("Payload must contain 'input_file'")
        batch_size = int(payload.get("batch_size", 5000))
        return ingest_file(db, input_file, batch_size=batch_size)

    app.include_router(create_router(db, _ingest_callback))
    app.state.mongo_client = client
    app.state.db = db

    # Start scheduled jobs in the background
    scheduler = start_scheduler(db)
    app.state.scheduler = scheduler

    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orders Data Engineering Pipeline")
    parser.add_argument("--input", required=True, help="Path to input CSV file")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for loading")
    parser.add_argument("--threshold", type=float, default=200.0, help="Threshold size in MB for router")
    args = parser.parse_args()

    client, db = connect(
        os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        os.getenv("MONGO_DATABASE", "orders_db")
    )
    try:
        res = ingest_file(db, args.input, batch_size=args.batch_size, threshold_mb=args.threshold)
        print("\n=== Ingestion Completed ===")
        print(json.dumps(res["metrics"], indent=2, ensure_ascii=False))
    finally:
        client.close()
