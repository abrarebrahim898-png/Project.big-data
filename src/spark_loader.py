from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


def make_spark(app_name: str = "orders-data-pipeline", mongo_uri: str = "mongodb://localhost:27017"):
    """Initialize SparkSession configured for Big Data processing and MongoDB integration."""
    from pyspark.sql import SparkSession
    return (
        SparkSession.builder
        .appName(app_name)
        .config("spark.mongodb.write.connection.uri", mongo_uri)
        .config("spark.mongodb.read.connection.uri", mongo_uri)
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )


def get_raw_spark_schema():
    """
    Fixed schema with StringType for all columns to preserve dirty data uncorrupted,
    satisfying Section 6.4 of Midterm Specifications.
    """
    from pyspark.sql.types import StructType, StructField, StringType
    columns = [
        "order_id", "order_date", "status", "customer_id", "customer_name",
        "customer_phone", "customer_email", "city", "district", "delivery_type",
        "delivery_cost", "payment_method", "payment_status", "payment_amount",
        "currency", "total_amount", "items_json"
    ]
    return StructType([StructField(col, StringType(), True) for col in columns])


def spark_batch_load(file_path: str | Path, db, run_id: str, mongo_uri: str = "mongodb://localhost:27017") -> dict[str, Any]:
    """
    Load a large CSV file using PySpark DataFrame API into orders_raw collection.
    Tracks partitions, execution time, and throughput.
    """
    start_time = time.perf_counter()
    spark = make_spark("pyspark-batch-loader", mongo_uri)
    try:
        schema = get_raw_spark_schema()
        df = (
            spark.read
            .option("header", "true")
            .schema(schema)
            .csv(str(file_path))
        )

        input_partitions = df.rdd.getNumPartitions()
        total_rows = df.count()

        # Convert rows into MongoDB orders_raw format with metadata
        from pyspark.sql import functions as F
        now_str = datetime.now(timezone.utc).isoformat()
        enriched_df = (
            df
            .withColumn("id_run", F.lit(run_id))
            .withColumn("run_id", F.lit(run_id))
            .withColumn("file_source", F.lit(str(file_path)))
            .withColumn("source_file", F.lit(str(file_path)))
            .withColumn("number_row_source", F.monotonically_increasing_id() + 2)
            .withColumn("source_row_number", F.monotonically_increasing_id() + 2)
            .withColumn("at_ingested", F.lit(now_str))
            .withColumn("ingested_at", F.lit(now_str))
            .withColumn("engine_used", F.lit("pyspark"))
        )

        # Write to MongoDB orders_raw
        raw_collection = db["orders_raw"]
        # Batch insert partitions into mongo
        rows = [row.asDict() for row in enriched_df.collect()]
        for r in rows:
            # construct record_raw
            record_raw = {k: v for k, v in r.items() if k not in {
                "id_run", "run_id", "file_source", "source_file",
                "number_row_source", "source_row_number", "at_ingested",
                "ingested_at", "engine_used"
            }}
            r["record_raw"] = record_raw
            r["raw_record"] = record_raw

        if rows:
            raw_collection.insert_many(rows, ordered=False)

        elapsed = max(time.perf_counter() - start_time, 1e-9)
        throughput = round(total_rows / elapsed, 2)

        return {
            "rows_read": total_rows,
            "raw_loaded": len(rows),
            "partitions": input_partitions,
            "elapsed_seconds": round(elapsed, 4),
            "throughput": throughput,
        }
    finally:
        pass
