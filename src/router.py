from __future__ import annotations

from pathlib import Path
from typing import Any
from fastapi import APIRouter, HTTPException, Query

from .jobs import JOB_DEFINITIONS, run_job, list_job_logs
from .materialized_views import VIEW_NAMES, read_view, refresh_incremental
from .reports import (
    AGGREGATION_DEFINITIONS,
    QUERY_DEFINITIONS,
    explain_before_after,
    list_aggregation_names,
    list_query_names,
    run_aggregation,
    run_query,
)


def choose_engine(file_path: str | Path, threshold_mb: float = 200.0) -> dict[str, Any]:
    """
    Select between Python Batch and PySpark based on file size.
    Complies with Midterm Section 6.2:
    - Prints file size, chosen engine, and rationale.
    - Configurable threshold (default 200 MB).
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Input file not found at: {path}")

    size_bytes = path.stat().st_size
    size_mb = round(size_bytes / (1024 * 1024), 4)

    if size_mb <= threshold_mb:
        engine = "python_batch"
        reason = f"File size ({size_mb} MB) is <= threshold ({threshold_mb} MB) -> Python Streaming Batch Loader chosen."
    else:
        engine = "pyspark"
        reason = f"File size ({size_mb} MB) exceeds threshold ({threshold_mb} MB) -> PySpark Distributed Loader chosen."

    print(f"\n[File Router Decision]")
    print(f"File: {path.name} ({size_mb} MB)")
    print(f"Engine: {engine}")
    print(f"Reason: {reason}\n")

    return {
        "file_name": path.name,
        "file_path": str(path),
        "file_size_mb": size_mb,
        "threshold_mb": threshold_mb,
        "engine": engine,
        "reason": reason,
    }


def create_router(db, ingest_callback=None) -> APIRouter:
    router = APIRouter()

    @router.get("/health", summary="Health Check")
    def health():
        db.command("ping")
        return {
            "status": "ok",
            "database": db.name,
            "orders_validated_count": db["orders_validated"].count_documents({}),
            "orders_quarantine_count": db["orders_quarantine"].count_documents({}),
        }

    @router.post("/ingest", summary="Run ELT Pipeline Ingestion")
    def ingest(payload: dict):
        if ingest_callback is None:
            raise HTTPException(503, "Ingest callback is not configured")
        return ingest_callback(payload)

    @router.post("/indexes", summary="Create Phase 2 Reporting Indexes")
    def create_indexes():
        from .mongo import setup_reporting_indexes
        created = setup_reporting_indexes(db)
        return {"created": created, "indexes": [idx["name"] for idx in db["orders_validated"].list_indexes()]}

    @router.get("/queries", summary="List Available Reporting Queries")
    def queries():
        return {"queries": list_query_names()}

    @router.get("/queries/{name}", summary="Execute Reporting Query")
    def query(name: str, limit: int = Query(50, ge=1, le=500)):
        if name not in QUERY_DEFINITIONS:
            raise HTTPException(404, f"Unknown query '{name}'. Available: {list(QUERY_DEFINITIONS.keys())}")
        return {"name": name, "rows": run_query(db["orders_validated"], name, limit)}

    @router.get("/queries/{name}/explain", summary="Explain Execution Plan Before and After Indexing")
    def query_explain(name: str):
        if name not in QUERY_DEFINITIONS:
            raise HTTPException(404, f"Unknown query '{name}'. Available: {list(QUERY_DEFINITIONS.keys())}")
        from .mongo import REPORTING_INDEXES
        return explain_before_after(db["orders_validated"], name, REPORTING_INDEXES)

    @router.get("/aggregations", summary="List Aggregation Reports")
    def aggregations():
        return {"reports": list_aggregation_names()}

    @router.get("/aggregations/{name}", summary="Execute Aggregation Report")
    def aggregation(name: str):
        if name not in AGGREGATION_DEFINITIONS:
            raise HTTPException(404, f"Unknown aggregation '{name}'. Available: {list(AGGREGATION_DEFINITIONS.keys())}")
        return {"name": name, "rows": run_aggregation(db["orders_validated"], name)}

    @router.post("/refresh-mv", summary="Incrementally Refresh Materialized Views")
    def refresh_mv():
        return refresh_incremental(db)

    @router.get("/views", summary="List Materialized Views")
    def list_views():
        return {"views": list(VIEW_NAMES)}

    @router.get("/views/{name}", summary="Get Materialized View Data")
    def view(name: str, limit: int = Query(100, ge=1, le=1000)):
        if name not in VIEW_NAMES:
            raise HTTPException(404, f"Unknown view '{name}'. Available: {list(VIEW_NAMES)}")
        return {"name": name, "rows": read_view(db, name, limit)}

    @router.get("/jobs", summary="List Scheduled Jobs")
    def jobs():
        return {"jobs": [{"name": k, **v} for k, v in JOB_DEFINITIONS.items()]}

    @router.post("/jobs/{name}/run", summary="Trigger Scheduled Job Manually")
    def run_scheduled_job(name: str):
        if name not in JOB_DEFINITIONS:
            raise HTTPException(404, f"Unknown job '{name}'. Available: {list(JOB_DEFINITIONS.keys())}")
        return run_job(db, name)

    @router.get("/jobs/logs", summary="Get Scheduled Job Execution Logs")
    def job_logs(limit: int = Query(50, ge=1, le=200)):
        return {"logs": list_job_logs(db, limit)}

    return router
