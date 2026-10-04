from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .jobs import JOB_DEFINITIONS, run_job
from .materialized_views import VIEW_NAMES, read_view, refresh_incremental
from .reports import AGGREGATION_DEFINITIONS, QUERY_DEFINITIONS, explain_before_after, list_aggregation_names, list_query_names, run_aggregation, run_query


def choose_engine(file_path, threshold_mb=200):
    """Select the original batch or Spark route based on source size."""
    from pathlib import Path
    size_mb = Path(file_path).stat().st_size / (1024 * 1024)
    return {"file_size_mb": round(size_mb, 4), "engine": "python_batch" if size_mb <= threshold_mb else "pyspark", "reason": f"File size {'<=' if size_mb <= threshold_mb else '>'} {threshold_mb} MB"}


def create_router(db, ingest_callback=None):
    router = APIRouter()

    @router.get("/health")
    def health():
        db.command("ping")
        return {"status": "ok", "database": db.name}

    @router.post("/ingest")
    def ingest(payload: dict):
        if ingest_callback is None:
            raise HTTPException(503, "ingest is not configured")
        return ingest_callback(payload)

    @router.post("/indexes")
    def create_indexes():
        from .mongo import setup_reporting_indexes
        return {"created": setup_reporting_indexes(db)}

    @router.get("/queries")
    def queries():
        return {"queries": list_query_names()}

    @router.get("/queries/{name}")
    def query(name: str, limit: int = Query(50, ge=1, le=500)):
        if name not in QUERY_DEFINITIONS:
            raise HTTPException(404, "unknown query")
        return {"name": name, "rows": run_query(db["orders_validated"], name, limit)}

    @router.get("/queries/{name}/explain")
    def query_explain(name: str):
        if name not in QUERY_DEFINITIONS:
            raise HTTPException(404, "unknown query")
        from .mongo import REPORTING_INDEXES
        return explain_before_after(db["orders_validated"], name, REPORTING_INDEXES)

    @router.get("/aggregations")
    def aggregations():
        return {"reports": list_aggregation_names()}

    @router.get("/aggregations/{name}")
    def aggregation(name: str):
        if name not in AGGREGATION_DEFINITIONS:
            raise HTTPException(404, "unknown aggregation report")
        return {"name": name, "rows": run_aggregation(db["orders_validated"], name)}

    @router.post("/refresh-mv")
    def refresh_mv():
        return refresh_incremental(db)

    @router.get("/views/{name}")
    def view(name: str):
        if name not in VIEW_NAMES:
            raise HTTPException(404, "unknown materialized view")
        return {"name": name, "rows": read_view(db, name)}

    @router.get("/jobs")
    def jobs():
        return {"jobs": [{"name": k, **v} for k, v in JOB_DEFINITIONS.items()]}

    @router.post("/jobs/{name}/run")
    def run(name: str):
        if name not in JOB_DEFINITIONS:
            raise HTTPException(404, "unknown job")
        return run_job(db, name)

    return router
