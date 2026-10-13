from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

VIEW_NAMES = ("daily_sales_summary", "top_products_summary")


def _extract_items(document: dict[str, Any]) -> list[dict[str, Any]]:
    items = document.get("items")
    if isinstance(items, list):
        return items
    raw_val = document.get("items_json")
    if isinstance(raw_val, str):
        try:
            parsed = json.loads(raw_val)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []


def refresh_incremental(db, since: datetime | None = None) -> dict[str, Any]:
    """
    Incrementally refresh daily_sales_summary and top_products_summary.
    Complies strictly with Phase 2 Materialized Views requirement:
    - Only reads documents newer than the stored watermark (last_processed_at).
    - Applies updates incrementally using $inc without rebuilding the entire dataset.
    - Idempotent: re-running when no new data has arrived modifies 0 documents.
    """
    source = db["orders_validated"]
    watermarks = db["mv_watermarks"]
    daily_coll = db["daily_sales_summary"]
    products_coll = db["top_products_summary"]
    legacy_views = db["materialized_views"]

    if since is None:
        state = watermarks.find_one({"_id": "orders_validated"})
        since = state.get("last_processed_at") if state else None

    query = {"processed_at": {"$gt": since}} if since else {}
    docs = list(source.find(query).sort("processed_at", 1))

    if not docs:
        return {
            "processed_documents": 0,
            "daily_rows_updated": 0,
            "product_rows_updated": 0,
            "watermark": since,
            "status": "up_to_date"
        }

    daily_updates: dict[str, dict[str, float]] = {}
    product_updates: dict[str, dict[str, Any]] = {}
    newest = since
    now_utc = datetime.now(timezone.utc)

    for doc in docs:
        proc_time = doc.get("processed_at")
        if proc_time and (newest is None or proc_time > newest):
            newest = proc_time

        # 1. Daily Sales Summary aggregation
        day_str = str(doc.get("order_date", "UNKNOWN"))[:10]
        if not day_str or day_str == "None":
            day_str = "UNKNOWN"
        day_entry = daily_updates.setdefault(day_str, {"orders_count": 0, "total_sales": 0.0})
        day_entry["orders_count"] += 1
        day_entry["total_sales"] += float(doc.get("total_amount") or 0.0)

        # 2. Top Products Summary aggregation
        for item in _extract_items(doc):
            sku = str(item.get("sku") or item.get("item_id") or "UNKNOWN").strip()
            name = str(item.get("name") or item.get("item_name") or sku).strip()
            qty = float(item.get("qty") or item.get("quantity") or 0.0)
            unit_p = float(item.get("unit_price") or item.get("price") or 0.0)
            revenue = qty * unit_p

            if sku not in product_updates:
                product_updates[sku] = {
                    "sku": sku,
                    "name": name,
                    "total_quantity": 0.0,
                    "total_revenue": 0.0,
                }
            product_updates[sku]["total_quantity"] += qty
            product_updates[sku]["total_revenue"] += revenue

    # Apply incremental updates to dedicated daily_sales_summary collection
    for day, vals in daily_updates.items():
        daily_coll.update_one(
            {"_id": day},
            {
                "$inc": {"orders_count": vals["orders_count"], "total_sales": vals["total_sales"]},
                "$set": {"date": day, "updated_at": now_utc},
            },
            upsert=True
        )
        legacy_views.update_one(
            {"_id": day},
            {
                "$inc": {"orders": vals["orders_count"], "sales": vals["total_sales"]},
                "$set": {"view": "daily_sales_summary", "updated_at": now_utc},
            },
            upsert=True
        )

    # Apply incremental updates to dedicated top_products_summary collection
    for sku, pdata in product_updates.items():
        products_coll.update_one(
            {"_id": sku},
            {
                "$inc": {"total_quantity": pdata["total_quantity"], "total_revenue": pdata["total_revenue"]},
                "$set": {"sku": sku, "name": pdata["name"], "updated_at": now_utc},
            },
            upsert=True
        )
        legacy_views.update_one(
            {"_id": f"product:{sku}"},
            {
                "$inc": {"quantity": pdata["total_quantity"], "revenue": pdata["total_revenue"]},
                "$set": {"view": "top_products_summary", "sku": sku, "name": pdata["name"], "updated_at": now_utc},
            },
            upsert=True
        )

    # Update high-watermark
    if newest is not None:
        watermarks.update_one(
            {"_id": "orders_validated"},
            {"$set": {"last_processed_at": newest, "updated_at": now_utc}},
            upsert=True
        )

    return {
        "processed_documents": len(docs),
        "daily_rows_updated": len(daily_updates),
        "product_rows_updated": len(product_updates),
        "watermark": newest,
        "status": "success"
    }


def read_view(db, name: str, limit: int = 100) -> list[dict[str, Any]]:
    if name == "daily_sales_summary":
        results = list(db["daily_sales_summary"].find({}, {"_id": 0}).sort("date", -1).limit(limit))
        if not results:
            results = list(db["materialized_views"].find({"view": name}, {"_id": 0}).sort("_id", -1).limit(limit))
        return results
    elif name == "top_products_summary":
        results = list(db["top_products_summary"].find({}, {"_id": 0}).sort("total_revenue", -1).limit(limit))
        if not results:
            results = list(db["materialized_views"].find({"view": name}, {"_id": 0}).sort("revenue", -1).limit(limit))
        return results
    raise KeyError(f"Unknown materialized view '{name}'. Available views: {VIEW_NAMES}")
