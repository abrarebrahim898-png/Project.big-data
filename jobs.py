"""Scheduled jobs required by the final phase."""
from __future__ import annotations

from datetime import datetime, timezone

from .materialized_views import refresh_incremental
from .reports import run_aggregation

JOB_DEFINITIONS = {
    "refresh_materialized_views": {"schedule": "hourly", "description": "تحديث daily_sales_summary و top_products_summary تزايديًا"},
    "write_daily_status_report": {"schedule": "daily at 23:55 UTC", "description": "تشغيل تقرير توزيع الطلبات حسب الحالة وحفظ لقطة تشغيل"},
}


def run_job(db, name: str):
    if name == "refresh_materialized_views":
        result = refresh_incremental(db)
    elif name == "write_daily_status_report":
        result = {"report": "orders_by_status", "rows": run_aggregation(db["orders_validated"], "orders_by_status")}
        db["job_runs"].insert_one({"job": name, "ran_at": datetime.now(timezone.utc), "result": result})
    else:
        raise KeyError(name)
    return {"job": name, "completed_at": datetime.now(timezone.utc), "result": result}


def start_scheduler(db):
    """Start APScheduler only when the API is run as a service."""
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(lambda: run_job(db, "refresh_materialized_views"), "interval", hours=1, id="refresh_materialized_views", replace_existing=True)
    scheduler.add_job(lambda: run_job(db, "write_daily_status_report"), "cron", hour=23, minute=55, id="write_daily_status_report", replace_existing=True)
    scheduler.start()
    return scheduler
