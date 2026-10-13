from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from .materialized_views import refresh_incremental, read_view
from .mongo import REPORTING_INDEXES, connect, setup_reporting_indexes
from .reports import explain_before_after, run_aggregation, run_query
from .jobs import run_job

load_dotenv()


def run_final_phase(db) -> dict:
    """
    Execute all Big Data Phase 2 demonstrations:
    1. 5 Queries execution and 3 Indexes with before/after explain comparison
    2. 5 Aggregations execution
    3. 2 Materialized Views incremental update
    4. Scheduled jobs execution
    """
    collection_name = os.getenv("VALIDATED_COLLECTION", "orders_validated")
    collection = db[collection_name]

    # 1. Indexes and explain comparison for 3 queries matching the 3 indexes
    created_indexes = setup_reporting_indexes(db, collection_name)
    explain_query_names = ["recent_orders", "orders_by_city_status", "customer_orders"]
    explains = [
        explain_before_after(collection, q_name, REPORTING_INDEXES)
        for q_name in explain_query_names
    ]

    # Sample query outputs
    query_samples = {
        name: run_query(collection, name, limit=5)
        for name in ["recent_orders", "orders_by_city_status", "customer_orders", "high_value_orders", "paid_orders"]
    }

    # 2. Aggregations (5 reports)
    aggregation_names = ["sales_by_city", "top_products", "top_customers", "sales_by_period", "orders_by_status"]
    aggregations = {
        name: run_aggregation(collection, name)
        for name in aggregation_names
    }

    # 3. Incremental Materialized Views Refresh
    mv_refresh_result = refresh_incremental(db)
    daily_sales_sample = read_view(db, "daily_sales_summary", limit=5)
    top_products_sample = read_view(db, "top_products_summary", limit=5)

    # 4. Scheduled Jobs Execution
    job_results = {
        "refresh_materialized_views": run_job(db, "refresh_materialized_views"),
        "write_daily_status_report": run_job(db, "write_daily_status_report"),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "database": db.name,
        "collection": collection_name,
        "indexes": created_indexes,
        "explains": explains,
        "queries": query_samples,
        "aggregations": aggregations,
        "materialized_views": {
            "refresh_summary": mv_refresh_result,
            "daily_sales_sample": daily_sales_sample,
            "top_products_sample": top_products_sample,
        },
        "jobs": job_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Run Big Data Phase 2 Final Demonstration")
    parser.add_argument("--output", default="final_phase_report.json", help="Path to output JSON report")
    args = parser.parse_args()

    client, db = connect(
        os.getenv("MONGO_URI", "mongodb://localhost:27017"),
        os.getenv("MONGO_DATABASE", "orders_db")
    )
    try:
        report = run_final_phase(db)
        out_path = Path(args.output).resolve()
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, default=str, indent=2)
        print(f"Final phase demonstration report written successfully to {out_path}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
