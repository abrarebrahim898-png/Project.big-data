"""Incremental materialized views for dashboard/report workloads."""
from __future__ import annotations

import json
from datetime import datetime, timezone


VIEW_NAMES = ("daily_sales_summary", "top_products_summary")


def _items(document):
    value = document.get("items") or document.get("items_json") or []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    return value if isinstance(value, list) else []


def refresh_incremental(db, since=None):
    """Apply only documents newer than the stored watermark; never rebuilds all rows."""
    source = db["orders_validated"]
    views = db["materialized_views"]
    watermarks = db["mv_watermarks"]
    if since is None:
        state = watermarks.find_one({"_id": "orders_validated"})
        since = state.get("last_processed_at") if state else None
    query = {"processed_at": {"$gt": since}} if since else {}
    docs = list(source.find(query).sort("processed_at", 1))
    daily_updates, product_updates = {}, {}
    newest = since
    for doc in docs:
        processed_at = doc.get("processed_at")
        if processed_at and (newest is None or processed_at > newest):
            newest = processed_at
        day = str(doc.get("order_date", "unknown"))[:10]
        day_data = daily_updates.setdefault(day, {"orders": 0, "sales": 0.0})
        day_data["orders"] += 1
        day_data["sales"] += float(doc.get("total_amount") or 0)
        for item in _items(doc):
            key = (item.get("sku", "unknown"), item.get("name", "unknown"))
            product = product_updates.setdefault(key, {"quantity": 0, "revenue": 0.0})
            qty = float(item.get("qty") or 0)
            product["quantity"] += qty
            product["revenue"] += qty * float(item.get("unit_price") or 0)
    for day, values in daily_updates.items():
        views.update_one({"_id": day}, {"$inc": values, "$set": {"view": "daily_sales_summary", "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    for (sku, name), values in product_updates.items():
        views.update_one({"_id": f"product:{sku}"}, {"$inc": values, "$set": {"view": "top_products_summary", "sku": sku, "name": name, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    if newest is not None:
        watermarks.update_one({"_id": "orders_validated"}, {"$set": {"last_processed_at": newest, "updated_at": datetime.now(timezone.utc)}}, upsert=True)
    return {"processed_documents": len(docs), "daily_rows_updated": len(daily_updates), "product_rows_updated": len(product_updates), "watermark": newest}


def read_view(db, name: str, limit: int = 100):
    if name == "daily_sales_summary":
        return list(db["materialized_views"].find({"view": name}, {"_id": 0}).sort("_id", 1).limit(limit))
    if name == "top_products_summary":
        return list(db["materialized_views"].find({"view": name}, {"_id": 0}).sort("revenue", -1).limit(limit))
    raise KeyError(name)
