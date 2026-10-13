from __future__ import annotations

from pymongo import MongoClient, ASCENDING, DESCENDING
from typing import Any

REPORTING_INDEXES = [
    {
        "keys": [("order_date", DESCENDING)],
        "name": "idx_order_date",
        "description": "Index on order_date to speed up chronological sorting and range filters (recent_orders).",
    },
    {
        "keys": [("city", ASCENDING), ("status", ASCENDING)],
        "name": "idx_city_status",
        "description": "Compound index on (city, status) to serve queries filtering by geographic location and fulfillment status without table scan.",
    },
    {
        "keys": [("customer_id", ASCENDING)],
        "name": "idx_customer_id",
        "description": "Single-field index on customer_id to optimize customer history lookups and prevent full collection scans.",
    },
]


def connect(uri: str, database: str) -> tuple[MongoClient, Any]:
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client, client[database]


def setup_collections(db, raw_name: str = "orders_raw", validated_name: str = "orders_validated", quarantine_name: str = "orders_quarantine"):
    raw = db[raw_name]
    validated = db[validated_name]
    quarantine = db[quarantine_name]

    # Ensure unique business key index exists on order_id in validated collection
    existing_indexes = {idx["name"]: idx for idx in validated.list_indexes()}
    if "ux_order_id" not in existing_indexes:
        validated.create_index(
            [("order_id", ASCENDING)],
            unique=True,
            name="ux_order_id"
        )

    return raw, validated, quarantine


def setup_reporting_indexes(db, collection_name: str = "orders_validated") -> list[str]:
    """Create the 3 reporting indexes required by Phase 2, including at least one compound index."""
    collection = db[collection_name]
    created = []
    for spec in REPORTING_INDEXES:
        name = collection.create_index(spec["keys"], name=spec["name"])
        created.append(name)
    return created


def setup_schema_validation(db, collection_name: str = "orders_validated"):
    """Set up MongoDB JSON Schema Validation on the validated collection according to specs."""
    try:
        db.command({
            "collMod": collection_name,
            "validator": {
                "$jsonSchema": {
                    "bsonType": "object",
                    "required": ["order_id", "quality_status"],
                    "properties": {
                        "order_id": {"bsonType": "string", "description": "Canonical business key required"},
                        "quality_status": {"enum": ["valid", "corrected"], "description": "Only valid or corrected allowed"},
                    },
                }
            },
            "validationLevel": "moderate",
            "validationAction": "error",
        })
    except Exception as e:
        # If collection doesn't exist yet, create it with validator
        try:
            db.create_collection(
                collection_name,
                validator={
                    "$jsonSchema": {
                        "bsonType": "object",
                        "required": ["order_id", "quality_status"],
                        "properties": {
                            "order_id": {"bsonType": "string"},
                            "quality_status": {"enum": ["valid", "corrected"]},
                        },
                    }
                },
                validationLevel="moderate",
                validationAction="error"
            )
        except Exception:
            pass
