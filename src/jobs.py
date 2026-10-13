from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from .materialized_views import refresh_incremental
from .reports import run_aggregation

JOB_DEFINITIONS = {
    "refresh_materialized_views": {
        "schedule": "hourly",
        "description": "تحديث العروض المادية daily_sales_summary و top_products_summary تزايديًا",
    },
    "write_daily_status_report": {
        "schedule": "daily at 23:55 UTC",
        "description": "تشغيل تقرير توزيع الطلبات حسب الحالة وحفظ ملخص دوري في قاعدة البيانات",
    },
}


def run_job(db, name: str) -> dict[str, Any]:
    """
    Run a scheduled job manually or automatically and log full audit metrics:
    started_at, ended_at, duration_seconds, status (SUCCESS/FAILED), result/error.
    Complies with Phase 2 requirement:
    'يجب تسجيل نتيجة التنفيذ ووقت البداية والنهاية وحالة النجاح أو الفشل.'
    """
    if name not in JOB_DEFINITIONS:
        raise KeyError(f"Unknown job '{name}'. Available: {list(JOB_DEFINITIONS.keys())}")

    started_at = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    status = "SUCCESS"
    result = None
    error_msg = None

    try:
        if name == "refresh_materialized_views":
            result = refresh_incremental(db)
        elif name == "write_daily_status_report":
            report_rows = run_aggregation(db["orders_validated"], "orders_by_status")
            result = {
                "report": "orders_by_status",
                "rows_count": len(report_rows),
                "summary": report_rows,
            }
    except Exception as exc:
        status = "FAILED"
        error_msg = str(exc)
        result = {"error": error_msg}

    ended_at = datetime.now(timezone.utc)
    duration_sec = round(time.perf_counter() - t0, 4)

    log_entry = {
        "job_name": name,
        "job": name,
        "started_at": started_at,
        "ended_at": ended_at,
        "ran_at": ended_at,
        "duration_seconds": duration_sec,
        "status": status,
        "result": result,
    }
    if error_msg:
        log_entry["error"] = error_msg

    # Persist in both job_logs and job_runs collections
    db["job_logs"].insert_one(dict(log_entry))
    db["job_runs"].insert_one(dict(log_entry))

    # Format return
    return {
        "job": name,
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_seconds": duration_sec,
        "status": status,
        "result": result,
    }


def list_job_logs(db, limit: int = 50) -> list[dict[str, Any]]:
    cursor = db["job_logs"].find({}, {"_id": 0}).sort("ended_at", -1).limit(limit)
    return list(cursor)


def start_scheduler(db):
    """Start APScheduler in the background when running the API server."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(
            lambda: run_job(db, "refresh_materialized_views"),
            "interval",
            hours=1,
            id="refresh_materialized_views",
            replace_existing=True
        )
        scheduler.add_job(
            lambda: run_job(db, "write_daily_status_report"),
            "cron",
            hour=23,
            minute=55,
            id="write_daily_status_report",
            replace_existing=True
        )
        scheduler.start()
        return scheduler
    except Exception as exc:
        print(f"Notice: APScheduler could not be started: {exc}")
        return None
