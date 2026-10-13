from __future__ import annotations

import os
import pytest
from pathlib import Path
from src.mongo import connect
from src.main import ingest_file


@pytest.fixture(scope="module")
def mongo_test_db():
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    client, db = connect(uri, "test_orders_db")
    # Clean previous test state
    db["orders_raw"].drop()
    db["orders_validated"].drop()
    db["orders_quarantine"].drop()
    yield db
    # Teardown
    client.drop_database("test_orders_db")
    client.close()


def test_idempotent_ingestion(mongo_test_db):
    sample_file = Path(__file__).resolve().parent.parent / "data" / "orders_sample.csv"
    assert sample_file.exists(), f"Sample file not found at {sample_file}"

    # First run (Initial Ingest)
    res1 = ingest_file(mongo_test_db, str(sample_file), batch_size=10)
    m1 = res1["metrics"]
    assert m1["inserted_count"] > 0
    assert m1["unchanged_count"] == 0
    assert m1["consistency_equation"]["passed"] is True

    initial_validated_count = mongo_test_db["orders_validated"].count_documents({})
    assert initial_validated_count == m1["valid_count"] + m1["corrected_count"]

    # Second run (Idempotency Replay with same input)
    res2 = ingest_file(mongo_test_db, str(sample_file), batch_size=10)
    m2 = res2["metrics"]
    assert m2["inserted_count"] == 0
    assert m2["unchanged_count"] == m1["valid_count"] + m1["corrected_count"]
    assert m2["consistency_equation"]["passed"] is True

    # Count of business records in orders_validated MUST remain identical
    second_validated_count = mongo_test_db["orders_validated"].count_documents({})
    assert second_validated_count == initial_validated_count, "Idempotency failed: business records count increased!"
