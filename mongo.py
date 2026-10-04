from pymongo import MongoClient, ASCENDING


REPORTING_INDEXES = [
    {"keys": [("order_date", ASCENDING)], "name": "idx_order_date"},
    {"keys": [("city", ASCENDING), ("status", ASCENDING)], "name": "idx_city_status"},
    {"keys": [("customer_id", ASCENDING)], "name": "idx_customer_id"},
]


def connect(uri, database):
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client, client[database]


def setup_collections(db, raw_name, validated_name, quarantine_name):
    raw = db[raw_name]
    validated = db[validated_name]
    quarantine = db[quarantine_name]
    # Remove stale indexes from previous project versions.
    # The current pipeline uses order_id as the canonical business key.
    for index in list(validated.list_indexes()):
        name = index["name"]
        if name != "_id_":
            validated.drop_index(name)

    validated.create_index(
        [("order_id", ASCENDING)],
        unique=True,
        name="ux_order_id"
    )
    quarantine.create_index([("id_run", ASCENDING), ("number_row_source", ASCENDING)], unique=True, name="ux_run_row")
    return raw, validated, quarantine


def setup_reporting_indexes(db, collection_name="orders_validated"):
    """Create the three final-phase reporting indexes, including one compound index."""
    collection = db[collection_name]
    return [collection.create_index(spec["keys"], name=spec["name"]) for spec in REPORTING_INDEXES]


def setup_schema_validation(db, collection_name):
    db.command({
        "collMod": collection_name,
        "validator": {
            "$jsonSchema": {
                "bsonType": "object",
                "required": ["order_id", "quality_status"],
                "properties": {
                    "order_id": {"bsonType": "string"},
                    "quality_status": {"enum": ["valid", "corrected"]},
                },
            }
        },
        "validationLevel": "moderate",
        "validationAction": "error",
    })
