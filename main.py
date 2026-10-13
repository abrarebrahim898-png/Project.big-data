from __future__ import annotations

import sys
from pathlib import Path

# Ensure root is in python path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.main import create_app, ingest_file
from src.batch_loader import python_batch_load
from src.mongo import connect, setup_collections, setup_schema_validation
from src.pipeline import process_run
from src.router import choose_engine, create_router

app = create_app()

if __name__ == "__main__":
    import argparse
    import json
    import os
    from dotenv import load_dotenv

    load_dotenv()
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
