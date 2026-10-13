from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

QUERY_DEFINITIONS = {
    "recent_orders": {
        "description": "آخر الطلبات مرتبة تنازليًا حسب تاريخ الطلب (يخدمه فهرس idx_order_date)",
        "filter": {},
        "sort": {"order_date": -1},
        "projection": {"_id": 0, "order_id": 1, "order_date": 1, "status": 1, "total_amount": 1},
        "target_index": "idx_order_date",
        "index_reason": "تسريع الفرز والبحث الزمني دون الحاجة لفرز كامل البيانات في الذاكرة (In-memory Sort)",
    },
    "orders_by_city_status": {
        "description": "طلبات مدينة صنعاء بحالة مؤكدة (يخدمه الفهرس المركب idx_city_status)",
        "filter": {"city": "صنعاء", "status": "CONFIRMED"},
        "sort": {"order_date": -1},
        "projection": {"_id": 0, "order_id": 1, "city": 1, "status": 1, "total_amount": 1},
        "target_index": "idx_city_status",
        "index_reason": "فهرس مركب (Compound Index) يخدم تصفية متعددة الحقول جغرافية وحالة الطلب بكفاءة عالية",
    },
    "customer_orders": {
        "description": "سجل طلبات عميل محدد (يخدمه فهرس idx_customer_id)",
        "filter": {"customer_id": "عميل-1"},
        "sort": {"order_date": -1},
        "projection": {"_id": 0, "order_id": 1, "customer_id": 1, "status": 1, "total_amount": 1},
        "target_index": "idx_customer_id",
        "index_reason": "تسريع استرجاع تاريخ طلبات العميل وتجنب المسح الشامل لمجموعة الطلبات",
    },
    "high_value_orders": {
        "description": "الطلبات ذات القيمة العالية مرتبة بالقيمة",
        "filter": {"total_amount": {"$gte": 50000.0}},
        "sort": {"total_amount": -1},
        "projection": {"_id": 0, "order_id": 1, "customer_name": 1, "total_amount": 1},
        "target_index": None,
        "index_reason": "استعلام لتحديد الصفقات الكبرى والمبيعات المرتفعة",
    },
    "paid_orders": {
        "description": "الطلبات المدفوعة بنجاح مرتبة بالمبلغ",
        "filter": {"payment_status": "PAID"},
        "sort": {"total_amount": -1},
        "projection": {"_id": 0, "order_id": 1, "payment_status": 1, "total_amount": 1},
        "target_index": None,
        "index_reason": "استعلام لتدقيق المعاملات المالية المدفوعة",
    },
}

AGGREGATION_DEFINITIONS = {
    "sales_by_city": {
        "description": "إجمالي وعدد المبيعات حسب المدينة",
        "pipeline": [
            {"$group": {"_id": "$city", "orders": {"$sum": 1}, "sales": {"$sum": "$total_amount"}}},
            {"$sort": {"sales": -1}},
            {"$project": {"_id": 0, "city": "$_id", "orders": 1, "sales": {"$round": ["$sales", 2]}}},
        ],
    },
    "top_products": {
        "description": "أفضل المنتجات حسب الكمية المباعة والإيرادات",
        "pipeline": [
            {"$unwind": "$items"},
            {
                "$group": {
                    "_id": {"sku": "$items.sku", "name": "$items.name"},
                    "quantity": {"$sum": "$items.qty"},
                    "revenue": {
                        "$sum": {
                            "$cond": [
                                {"$gt": ["$items.total", 0]},
                                "$items.total",
                                {"$multiply": ["$items.qty", {"$ifNull": ["$items.unit_price", 0]}]}
                            ]
                        }
                    }
                }
            },
            {"$sort": {"revenue": -1}},
            {"$limit": 20},
            {"$project": {"_id": 0, "sku": "$_id.sku", "name": "$_id.name", "quantity": 1, "revenue": {"$round": ["$revenue", 2]}}},
        ],
    },
    "top_customers": {
        "description": "أفضل العملاء حسب عدد الطلبات وإجمالي الإنفاق",
        "pipeline": [
            {"$group": {"_id": {"id": "$customer_id", "name": "$customer_name"}, "orders": {"$sum": 1}, "spent": {"$sum": "$total_amount"}}},
            {"$sort": {"spent": -1}},
            {"$limit": 20},
            {"$project": {"_id": 0, "customer_id": "$_id.id", "customer_name": "$_id.name", "orders": 1, "spent": {"$round": ["$spent", 2]}}},
        ],
    },
    "sales_by_period": {
        "description": "المبيعات الشهرية وتوزيع الإيرادات",
        "pipeline": [
            {"$group": {"_id": {"$substr": ["$order_date", 0, 7]}, "orders": {"$sum": 1}, "sales": {"$sum": "$total_amount"}}},
            {"$sort": {"_id": 1}},
            {"$project": {"_id": 0, "period": "$_id", "orders": 1, "sales": {"$round": ["$sales", 2]}}},
        ],
    },
    "orders_by_status": {
        "description": "توزيع الطلبات وقيمتها حسب حالة الطلب",
        "pipeline": [
            {"$group": {"_id": "$status", "orders": {"$sum": 1}, "sales": {"$sum": "$total_amount"}}},
            {"$sort": {"orders": -1}},
            {"$project": {"_id": 0, "status": "$_id", "orders": 1, "sales": {"$round": ["$sales", 2]}}},
        ],
    },
}


def list_query_names() -> list[dict[str, str]]:
    return [{"name": k, "description": v["description"]} for k, v in QUERY_DEFINITIONS.items()]


def list_aggregation_names() -> list[dict[str, str]]:
    return [{"name": k, "description": v["description"]} for k, v in AGGREGATION_DEFINITIONS.items()]


def run_query(collection, name: str, limit: int = 50) -> list[dict[str, Any]]:
    if name not in QUERY_DEFINITIONS:
        raise KeyError(name)
    defn = QUERY_DEFINITIONS[name]
    cursor = collection.find(defn["filter"], defn["projection"]).sort(list(defn["sort"].items())).limit(limit)
    return list(cursor)


def run_aggregation(collection, name: str) -> list[dict[str, Any]]:
    if name not in AGGREGATION_DEFINITIONS:
        raise KeyError(name)
    return list(collection.aggregate(AGGREGATION_DEFINITIONS[name]["pipeline"]))


def _extract_plan_stats(explain_doc: dict[str, Any]) -> dict[str, Any]:
    stats = explain_doc.get("executionStats", {})
    winning = explain_doc.get("queryPlanner", {}).get("winningPlan", {})
    return {
        "stage": winning.get("stage") or (winning.get("inputStage", {}).get("stage")),
        "nReturned": stats.get("nReturned", 0),
        "totalKeysExamined": stats.get("totalKeysExamined", 0),
        "totalDocsExamined": stats.get("totalDocsExamined", 0),
        "executionTimeMillis": stats.get("executionTimeMillis", 0),
    }


def explain_before_after(collection, name: str, indexes: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Run executionStats before (COLLSCAN without index) and after (IXSCAN with index).
    Includes explanation of index selection and measured performance effect.
    """
    if name not in QUERY_DEFINITIONS:
        raise KeyError(name)

    defn = QUERY_DEFINITIONS[name]
    filt = defn["filter"]
    proj = defn["projection"]
    sort = list(defn["sort"].items())

    # 1. Before index execution: Force natural scan (COLLSCAN)
    cursor_before = collection.find(filt, proj).sort(sort).limit(100).hint({"$natural": 1})
    explain_before = cursor_before.explain()
    stats_before = _extract_plan_stats(explain_before)

    # 2. Ensure indexes are present
    created_indexes = []
    for spec in indexes:
        idx_name = collection.create_index(spec["keys"], name=spec["name"])
        created_indexes.append(idx_name)

    # 3. After index execution: Use index
    target_idx = defn.get("target_index")
    cursor_after = collection.find(filt, proj).sort(sort).limit(100)
    if target_idx:
        try:
            cursor_after = cursor_after.hint(target_idx)
        except Exception:
            pass
    explain_after = cursor_after.explain()
    stats_after = _extract_plan_stats(explain_after)

    docs_examined_saved = stats_before["totalDocsExamined"] - stats_after["totalDocsExamined"]
    effect_summary = (
        f"Transformed plan from {stats_before['stage']} to {stats_after['stage']}. "
        f"Docs examined changed from {stats_before['totalDocsExamined']} to {stats_after['totalDocsExamined']} "
        f"(saved {docs_examined_saved} full document reads)."
    )

    return {
        "query": name,
        "target_index": target_idx,
        "reason_for_index": defn.get("index_reason", "تسريع أداء الاستعلام وتقليل فحص المستندات"),
        "effect_summary": effect_summary,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "before": stats_before,
        "after": stats_after,
        "indexes_active": created_indexes,
    }
