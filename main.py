from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from .batch_loader import python_batch_load
from .mongo import connect, setup_collections, setup_schema_validation
from .pipeline import process_run
from .router import choose_engine, create_router

load_dotenv()


def ingest_file(db, input_file: str, batch_size: int = 5000):
    raw, validated, quarantine = setup_collections(db, os.getenv("RAW_COLLECTION", "orders_raw"), os.getenv("VALIDATED_COLLECTION", "orders_validated"), os.getenv("QUARANTINE_COLLECTION", "orders_quarantine"))
    run_id = f"run-{uuid4()}"
    engine = choose_engine(input_file)
    if engine["engine"] != "python_batch":
        raise RuntimeError("PySpark route selected; install pyspark and use spark_loader for files over 200 MB")
    loaded = python_batch_load(input_file, raw, run_id, batch_size)
    processed = process_run(raw, validated, quarantine, run_id)
    return {"id_run": run_id, "engine": engine, "loaded": loaded, "processed": processed}


def create_app():
    from fastapi import FastAPI
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    database = os.getenv("MONGO_DATABASE", "orders_db")
    client, db = connect(uri, database)
    setup_collections(db, os.getenv("RAW_COLLECTION", "orders_raw"), os.getenv("VALIDATED_COLLECTION", "orders_validated"), os.getenv("QUARANTINE_COLLECTION", "orders_quarantine"))
    try:
        setup_schema_validation(db, os.getenv("VALIDATED_COLLECTION", "orders_validated"))
    except Exception:
        pass
    app = FastAPI(title="Orders Data Engineering API", version="2.0.0", description="Big Data Phase 2 API")
    app.include_router(create_router(db, lambda payload: ingest_file(db, payload["input_file"], int(payload.get("batch_size", 5000)))))
    app.state.mongo_client = client
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orders data engineering pipeline")
    parser.add_argument("--input", required=True, help="CSV input path")
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    client, db = connect(os.getenv("MONGO_URI", "mongodb://localhost:27017"), os.getenv("MONGO_DATABASE", "orders_db"))
    print(ingest_file(db, str(Path(args.input).resolve()), args.batch_size))
    client.close()
