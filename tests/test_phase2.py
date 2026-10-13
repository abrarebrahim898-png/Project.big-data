from __future__ import annotations

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.main import create_app, ingest_file
from src.mongo import connect


@pytest.fixture(scope="module")
def client_app():
    # Setup database with sample data first
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client, db = connect(uri, "orders_db")
    sample_file = Path(__file__).resolve().parent.parent / "data" / "orders_sample.csv"
    ingest_file(db, str(sample_file), batch_size=10)

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
    client.close()


def test_api_health(client_app):
    response = client_app.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_api_indexes(client_app):
    response = client_app.post("/indexes")
    assert response.status_code == 200
    data = response.json()
    assert "created" in data
    assert any("idx_order_date" in idx for idx in data["indexes"])
    assert any("idx_city_status" in idx for idx in data["indexes"])
    assert any("idx_customer_id" in idx for idx in data["indexes"])


def test_api_queries(client_app):
    response = client_app.get("/queries")
    assert response.status_code == 200
    queries = response.json()["queries"]
    assert len(queries) >= 5

    # Run individual queries
    for q in ["recent_orders", "orders_by_city_status", "customer_orders"]:
        q_res = client_app.get(f"/queries/{q}?limit=10")
        assert q_res.status_code == 200
        assert "rows" in q_res.json()


def test_api_explain(client_app):
    # Test explain before and after index on compound index query
    response = client_app.get("/queries/orders_by_city_status/explain")
    assert response.status_code == 200
    data = response.json()
    assert "before" in data
    assert "after" in data
    assert "reason_for_index" in data
    assert "effect_summary" in data


def test_api_aggregations(client_app):
    response = client_app.get("/aggregations")
    assert response.status_code == 200
    reports = response.json()["reports"]
    assert len(reports) >= 5

    for rep in ["sales_by_city", "top_products", "top_customers", "sales_by_period", "orders_by_status"]:
        rep_res = client_app.get(f"/aggregations/{rep}")
        assert rep_res.status_code == 200
        assert "rows" in rep_res.json()
        assert len(rep_res.json()["rows"]) > 0


def test_api_materialized_views(client_app):
    # Refresh views
    refresh_res = client_app.post("/refresh-mv")
    assert refresh_res.status_code == 200
    assert "status" in refresh_res.json()

    # Read daily_sales_summary
    daily_res = client_app.get("/views/daily_sales_summary")
    assert daily_res.status_code == 200
    assert len(daily_res.json()["rows"]) > 0

    # Read top_products_summary
    top_p_res = client_app.get("/views/top_products_summary")
    assert top_p_res.status_code == 200
    assert len(top_p_res.json()["rows"]) > 0


def test_api_jobs_and_execution_logging(client_app):
    # List jobs
    jobs_res = client_app.get("/jobs")
    assert jobs_res.status_code == 200
    assert len(jobs_res.json()["jobs"]) >= 2

    # Run refresh_materialized_views job
    run1 = client_app.post("/jobs/refresh_materialized_views/run")
    assert run1.status_code == 200
    assert run1.json()["status"] == "SUCCESS"
    assert "started_at" in run1.json()
    assert "ended_at" in run1.json()

    # Run write_daily_status_report job
    run2 = client_app.post("/jobs/write_daily_status_report/run")
    assert run2.status_code == 200
    assert run2.json()["status"] == "SUCCESS"

    # Verify audit logs in /jobs/logs
    logs_res = client_app.get("/jobs/logs")
    assert logs_res.status_code == 200
    logs = logs_res.json()["logs"]
    assert len(logs) >= 2
    assert all("status" in log and "started_at" in log and "ended_at" in log for log in logs)
