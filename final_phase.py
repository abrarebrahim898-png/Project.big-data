"""Run the final-phase demonstrations and save a reproducible JSON report."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from dotenv import load_dotenv

from .materialized_views import refresh_incremental
from .mongo import REPORTING_INDEXES, connect, setup_reporting_indexes
from .reports import explain_before_after, run_aggregation

load_dotenv()


def run_final_phase(db):
    collection = db[os.getenv("VALIDATED_COLLECTION", "orders_validated")]
    indexes = setup_reporting_indexes(db)
    explain_names = ["recent_orders", "high_value_orders", "customer_orders"]
    explains = [explain_before_after(collection, name, REPORTING_INDEXES) for name in explain_names]
    aggregations = {name: run_aggregation(collection, name) for name in ("sales_by_city", "top_products", "top_customers", "sales_by_period", "orders_by_status")}
    views = refresh_incremental(db)
    result = {"generated_at": datetime.now(timezone.utc), "indexes": indexes, "explains": explains, "aggregations": aggregations, "materialized_views": views}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="final_phase_report.json")
    args = parser.parse_args()
    client, db = connect(os.getenv("MONGO_URI", "mongodb://localhost:27017"), os.getenv("MONGO_DATABASE", "orders_db"))
    try:
        result = run_final_phase(db)
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, default=str, indent=2)
        print(f"Final phase report written to {args.output}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
