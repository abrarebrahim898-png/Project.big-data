"""MongoDB queries, aggregation reports, and execution-plan comparisons."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


QUERY_DEFINITIONS = {
    "recent_orders": {
        "description": "آخر الطلبات حسب تاريخ الطلب",
        "filter": {},
        "sort": {"order_date": -1},
        "projection": {"_id": 0, "order_id": 1, "order_date": 1, "status": 1, "total_amount": 1},
    },
    "high_value_orders": {
        "description": "الطلبات ذات القيمة العالية",
        "filter": {"total_amount": {"$gte": 100000}},
        "sort": {"total_amount": -1},
        "projection": {"_id": 0, "order_id": 1, "customer_name": 1, "total_amount": 1},
    },
    "orders_by_city": {
        "description": "طلبات مدينة محددة",
        "filter": {"city": "صنعاء"},
        "sort": {"order_date": -1},
        "projection": {"_id": 0, "order_id": 1, "city": 1, "total_amount": 1},
    },
    "customer_orders": {
        "description": "طلبات عميل محدد",
        "filter": {"customer_id": "عميل-1"},
        "sort": {"order_date": -1},
        "projection": {"_id": 0, "order_id": 1, "customer_id": 1, "status": 1, "total_amount": 1},
    },
    "paid_orders": {
        "description": "الطلبات المدفوعة مرتبة بالقيمة",
        "filter": {"payment_status": "PAID"},
        "sort": {"total_amount": -1},
        "projection": {"_id": 0, "order_id": 1, "payment_status": 1, "total_amount": 1},
    },
}


AGGREGATION_DEFINITIONS = {
    "sales_by_city": {
        "description": "إجمالي وعدد المبيعات حسب المدينة",
        "pipeline": [
            {"$group": {"_id": "$city", "orders": {"$sum": 1}, "sales": {"$sum": "$total_amount"}}},
            {"$sort": {"sales": -1}},
            {"$project": {"_id": 0, "city": "$_id", "orders": 1, "sales": 1}},
        ],
    },
    "top_products": {
        "description": "أفضل المنتجات حسب الكمية والإيراد",
        "pipeline": [
            {"$unwind": "$items"},
            {"$group": {"_id": {"sku": "$items.sku", "name": "$items.name"}, "quantity": {"$sum": "$items.qty"}, "revenue": {"$sum": {"$multiply": ["$items.qty", "$items.unit_price"]}}}},
            {"$sort": {"revenue": -1}},
            {"$limit": 20},
            {"$project": {"_id": 0, "sku": "$_id.sku", "name": "$_id.name", "quantity": 1, "revenue": 1}},
        ],
    },
    "top_customers": {
        "description": "أفضل العملاء حسب عدد الطلبات وقيمة المبيعات",
        "pipeline": [
            {"$group": {"_id": {"id": "$customer_id", "name": "$customer_name"}, "orders": {"$sum": 1}, "spent": {"$sum": "$total_amount"}}},
            {"$sort": {"spent": -1}},
            {"$limit": 20},
            {"$project": {"_id": 0, "customer_id": "$_id.id", "customer_name": "$_id.name", "orders": 1, "spent": 1}},
        ],
    },
    "sales_by_period": {
        "description": "المبيعات الشهرية",
        "pipeline": [
            {"$group": {"_id": {"$substr": ["$order_date", 0, 7]}, "orders": {"$sum": 1}, "sales": {"$sum": "$total_amount"}}},
            {"$sort": {"_id": 1}},
            {"$project": {"_id": 0, "period": "$_id", "orders": 1, "sales": 1}},
        ],
    },
    "orders_by_status": {
        "description": "توزيع الطلبات حسب الحالة",
        "pipeline": [
            {"$group": {"_id": "$status", "orders": {"$sum": 1}, "sales": {"$sum": "$total_amount"}}},
            {"$sort": {"orders": -1}},
            {"$project": {"_id": 0, "status": "$_id", "orders": 1, "sales": 1}},
        ],
    },
}


def list_query_names() -> list[dict[str, str]]:
    return [{"name": k, "description": v["description"]} for k, v in QUERY_DEFINITIONS.items()]


def list_aggregation_names() -> list[dict[str, str]]:
    return [{"name": k, "description": v["description"]} for k, v in AGGREGATION_DEFINITIONS.items()]


def run_query(collection, name: str, limit: int = 50) -> list[dict[str, Any]]:
    definition = QUERY_DEFINITIONS[name]
    cursor = collection.find(definition["filter"], definition["projection"]).sort(list(definition["sort"].items())).limit(limit)
    return list(cursor)


def run_aggregation(collection, name: str) -> list[dict[str, Any]]:
    return list(collection.aggregate(AGGREGATION_DEFINITIONS[name]["pipeline"]))


def explain_query(collection, name: str, limit: int = 50) -> dict[str, Any]:
    definition = QUERY_DEFINITIONS[name]
    cursor = collection.find(definition["filter"], definition["projection"]).sort(list(definition["sort"].items())).limit(limit)
    return cursor.explain("executionStats")


def _stats(explain: dict[str, Any]) -> dict[str, Any]:
    execution = explain.get("executionStats", {})
    return {"nReturned": execution.get("nReturned", 0), "totalKeysExamined": execution.get("totalKeysExamined", 0), "totalDocsExamined": execution.get("totalDocsExamined", 0), "executionTimeMillis": execution.get("executionTimeMillis", 0), "winningPlan": explain.get("queryPlanner", {}).get("winningPlan", {})}


def explain_before_after(collection, name: str, indexes: list[dict[str, Any]]) -> dict[str, Any]:
    """Capture real executionStats before and after the indexes are created."""
    before = _stats(explain_query(collection, name))
    created = []
    for spec in indexes:
        created.append(collection.create_index(spec["keys"], name=spec["name"], **spec.get("options", {})))
    after = _stats(explain_query(collection, name))
    return {"query": name, "captured_at": datetime.now(timezone.utc), "before": before, "after": after, "indexes_created": created}
