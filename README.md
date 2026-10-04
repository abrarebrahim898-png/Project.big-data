# Orders Data Engineering — Big Data Phase 2

هذا المشروع يستكمل مشروع المرحلة النصفية داخل نفس المستودع. تمت إضافة متطلبات المرحلة النهائية دون حذف مكونات التنظيف والتحميل السابقة.

## التشغيل

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# شغّل MongoDB محليًا ثم:
python -m src.main --input src/data/orders_sample.csv
uvicorn src.main:create_app --factory --reload
```

تحتاج ملفات CSV الكبيرة إلى PySpark اختياريًا، بينما يستخدم الملف الصغير مسار Python الدفعي.

## متطلبات المرحلة النهائية المنفذة

### 1) الاستعلامات والفهارس

يوجد خمسة استعلامات مستقلة في `src/reports.py`: `recent_orders`, `high_value_orders`, `orders_by_city`, `customer_orders`, و`paid_orders`.

ينشئ `POST /indexes` ثلاثة فهارس في `orders_validated`:

- `idx_order_date`: يدعم الفرز والاستعلامات الزمنية.
- `idx_city_status`: فهرس مركب يدعم تقارير المدينة والحالة.
- `idx_customer_id`: يدعم سجل العميل.

ينفذ `GET /queries/{name}/explain` مقارنة فعلية باستخدام `explain("executionStats")` قبل وبعد إنشاء الفهارس، ويعيد `totalDocsExamined`, `totalKeysExamined`, و`executionTimeMillis` مع خطة التنفيذ.

### 2) خمسة تقارير Aggregation

التقارير هي:

- `sales_by_city`
- `top_products`
- `top_customers`
- `sales_by_period`
- `orders_by_status`

كل تقرير له pipeline مستقل وتشغيل مستقل ونتيجة فعلية من `orders_validated`.

### 3) Materialized Views بتحديث تزايدي

- `daily_sales_summary`
- `top_products_summary`

تستخدم `src/materialized_views.py` مجموعة `mv_watermarks` لحفظ آخر `processed_at`. عند التحديث لا يعاد بناء كل البيانات؛ تتم قراءة الوثائق الجديدة فقط ثم تطبيق `$inc` على صفوف العرض. يمكن تشغيل التحديث عبر `POST /refresh-mv` أو المهمة المجدولة.

### 4) المهام المجدولة

يوجد مهمتان:

- `refresh_materialized_views`: كل ساعة.
- `write_daily_status_report`: يوميًا الساعة 23:55 UTC.

يمكن عرضهما من `GET /jobs` وتشغيل أي منهما يدويًا من `POST /jobs/{name}/run`. ويمكن استدعاء `start_scheduler(db)` من بيئة الخدمة لتفعيل APScheduler.

لتنفيذ عرض المرحلة النهائية وتسجيل النتائج في ملف JSON:

```bash
python -m src.final_phase --output final_phase_report.json
```

### 5) API موحدة

- `GET /health`
- `POST /ingest` — body: `{"input_file": "...", "batch_size": 5000}`
- `POST /indexes`
- `GET /queries`
- `GET /queries/{name}`
- `GET /queries/{name}/explain`
- `GET /aggregations`
- `GET /aggregations/{name}`
- `POST /refresh-mv`
- `GET /views/{name}`
- `GET /jobs`
- `POST /jobs/{name}/run`

تتوفر وثائق Swagger تلقائيًا على `/docs` وملف OpenAPI JSON على `/openapi.json`.

## التشغيل والتحقق

```bash
python -m compileall -q src
curl http://localhost:8000/health
curl -X POST http://localhost:8000/indexes
curl http://localhost:8000/aggregations/top_products
curl -X POST http://localhost:8000/refresh-mv
```

## ملاحظات البيانات

يحتفظ المشروع بـ`record_raw` للتتبع، ويطبق قواعد الجودة السابقة، ويعزل السجلات غير الصالحة. أضيف حقل `items` typed array إلى السجلات الصالحة مع إبقاء `items_json` الخام، حتى تعمل تجميعات المنتجات في MongoDB بصورة مباشرة.
