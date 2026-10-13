# خط أنابيب هندسة ومعالجة البيانات الضخمة (ELT Hybrid Pipeline & Phase 2 API)
### جامعة الرازي — مقرر البيانات الضخمة (العملي)
**المشروع النصفي (18 درجة) + المرحلة النهائية Phase 2 (7 درجات) = الإجمالي 25 درجة**

---

## 📌 نظرة عامة على المشروع (Project Overview)

يهدف هذا المشروع إلى بناء خط بيانات هجين لمعالجة وتدقيق بيانات طلبات التجارة الإلكترونية ذات الجودة المختلطة وفق نمط **ELT** (Extract, Load, Transform)، مع دعم متطلبات المرحلة النهائية المتقدمة عبر قاعدة بيانات **MongoDB** وواجهة **FastAPI** موحدة:

1. **الموجّه التلقائي للمحرك (File Router):** فحص حجم الملف وتوجيهه تلقائيًا بين المسار الدفعي المتدفق بلغة Python (للملفات ≤ 200MB) ومسار المعالجة المتوازية عبر Apache Spark (للملفات > 200MB).
2. **التحميل الأولي الخام (Raw Load):** تحميل جميع السجلات كما وردت إلى مجموعة `orders_raw` دون أي حذف أو تنظيف مسبق لحفظ سجل التتبع التاريخي.
3. **قواعد الجودة والتنظيف الآلي (Quality Rules):** تطبيق أكثر من 8 قواعد تنظيف وتصحيح ذكية مع الاحتفاظ بسجل الأثر والتدقيق (`corrections audit trail`).
4. **التصنيف والعزل (Classification & Quarantine):** تصنيف كل سجل إلى `valid` أو `corrected` أو نقله إلى `orders_quarantine` مع أسباب ورموز العزل التفصيلية، مع ضمان اتساق المعادلة:
`run_raw_count = run_valid_count + run_corrected_count + run_quarantine_count`5. **إعادة التشغيل الموثوق (Idempotency & Upsert):** استخدام مفتاح العمل الثابت `order_id` وفهرس فريد `ux_order_id` داخل `orders_validated` والكتابة بأسلوب Upsert لضمان عدم إنشاء أي سجلات مكررة عند إعادة تشغيل نفس الملف.
6. **الاستعلامات والفهارس (Queries, Indexes & Explain):** 5 استعلامات عملية تخدمها 3 فهارس (منها فهرس مركب Compound Index) مع تحليل خطط التنفيذ قبل وبعد عبر `explain("executionStats")`.
7. **التقارير والتجميعات (Aggregations):** 5 تقارير تحليلية تنفيذية تخدم الأعمال (المبيعات بالمدينة، أفضل المنتجات، كبار العملاء، المبيعات بالفترة، وتوزيع الحالات).
8. **العروض المادية التزايدية (Materialized Views):** تحديث تزايدي ذكي لـ `daily_sales_summary` و `top_products_summary` عبر علامة مائية (`watermark`) وعمليات `$inc` دون إعادة بناء البيانات من البداية.
9. **المهام المجدولة (Scheduled Jobs):** مهمتان مجدولتان لتحديث العروض وإنشاء التقارير الدورية مع توثيق وقت البداية والنهاية والحالة (`SUCCESS`/`FAILED`) في مجموعة `job_logs`.
10. **واجهة API موحدة (Unified FastAPI):** واجهة RESTful كاملة تلبي متطلبات نظام التقييم، وتوفر توثيق Swagger تفاعلي عبر `/docs`.

---

## 🏗️ المعمارية وتدفق البيانات (Architecture & Data Flow)

```text
       ┌───────────────────────────────┐
       │   Input CSV (Dirty / Clean)   │
       └───────────────┬───────────────┘
                       │
             [ File Router (200MB) ]
             ┌─────────┴─────────┐
      Size <= 200MB        Size > 200MB
             │                   │
             ▼                   ▼
    [ Python Batch Loader ]  [ PySpark Loader ]
             │                   │
             └─────────┬─────────┘
                       │
                       ▼
          [ MongoDB: orders_raw ]
                       │
                       ▼
         [ Quality Rules & Validation ]
                       │
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
    [ Valid ]    [ Corrected ]  [ Quarantined ]
       │               │               │
       │ (Audit Trail) │               ▼
       └───────┬───────┘     [ orders_quarantine ]
               │
               ▼
      (Idempotent Upsert)
               │
               ▼
     [ orders_validated ]
     (Unique Index: order_id)
     (Schema Validation)
               │
   ┌───────────┼───────────┐
   ▼           ▼           ▼
[Queries] [Aggregations] [Incremental MVs]
               │                   │
               └─────────┬─────────┘
                         ▼
        [ Unified FastAPI: /docs ]
```

---

## 📁 هيكل مجلدات المشروع (Repository Structure)

```text
Project.big-data/
├── README.md                     # وثيقة التوثيق والتشغيل الشاملة
├── requirements.txt              # الحزم البرمجية والتبعيات
├── .env.example                  # نموذج متغيرات البيئة
├── .env                          # ملف الإعدادات المحلي
├── .gitignore                    # استثناء الملفات المؤقتة وpyc
├── final_phase_report.json       # تقرير تقييم المرحلة النهائية الشامل
├── config/
│   ├── __init__.py
│   └── settings.py               # إعدادات النظام الموحدة
├── data/
│   └── orders_sample.csv         # مجموعة بيانات اختبارية تغطي كافة الحالات
├── reports/
│   └── results.json              # المقاييس والعدادات الرسمية لخط البيانات
├── src/                          # الحزمة البرمجية الأساسية
│   ├── __init__.py
│   ├── main.py                   # نقطة الدخول الرئيسية وتطبيق FastAPI
│   ├── api.py                    # تهيئة تطبيق الـ API
│   ├── router.py                 # موجه المحرك ومسارات REST API
│   ├── batch_loader.py           # التحميل الدفعي المتدفق (Python Streaming)
│   ├── spark_loader.py           # معالجة الملفات الكبيرة (PySpark)
│   ├── pipeline.py               # خط ELT والتصنيف والتحقق وIdempotency
│   ├── quality_rules.py          # قواعد الجودة الثمانية وسجل التدقيق
│   ├── mongo.py                  # إعداد الاتصال والفهارس والـ Schema
│   ├── reports.py                # الاستعلامات والتجميعات وتحليل Explain
│   ├── materialized_views.py     # العروض المادية والتحديث التزايدي
│   ├── jobs.py                   # المهام المجدولة وتسجيل التنفيذ
│   ├── incremental_loader.py     # معالجة ملفات Delta وتحديثات الإصدار (المسار B)
│   └── create_small_sample.py    # استخراج عينة متدفقة قابلة لإعادة الإنتاج
├── tests/                        # حزمة الاختبارات المؤتمتة (Pytest)
│   ├── __init__.py
│   ├── test_cleaning_rules.py    # اختبارات قواعد التنظيف الـ 8 وسجل التدقيق
│   ├── test_classification.py    # اختبارات حالات العزل التسع
│   ├── test_idempotency.py       # اختبارات إعادة التشغيل الآمنة وعدم التكرار
│   └── test_phase2.py            # اختبارات مسارات الـ API والعروض والمهام
├── main.py                       # مشغل سطري متوافق
├── run_api.py                    # تشغيل خادم FastAPI عبر Uvicorn
├── final_phase.py                # تشغيل العرض العملي وتوليد التقرير
├── create_small_sample.py        # سكربت سحب العينة المستقل
└── sample.py                     # اسم بديل لسكربت العينة
```

---

## ⚙️ التثبيت والتهيئة (Installation & Setup)

### 1. المتطلبات الأساسية
- Python 3.9 أو أحدث (تم الاختبار على 3.12).
- خادم MongoDB يعمل محليًا على المنفذ `27017` (أو خادم سحابي).

### 2. تثبيت الحزم
```bash
# إنشاء وتفعيل البيئة الافتراضية
python -m venv .venv

# على Linux / macOS:
source .venv/bin/activate
# على Windows PowerShell:
.venv\Scripts\Activate.ps1

# تثبيت الحزم
pip install -r requirements.txt

# إنشاء ملف البيئة
cp .env.example .env
```

---

## 🚀 تشغيل متطلبات المشروع النصفي (Phase 1 Execution)

### 1. استخراج عينة صغيرة قابلة لإعادة الإنتاج (Section 6.1)
```bash
python create_small_sample.py --input data/orders_sample.csv --rows 100 --output data/small_sample.csv
```

### 2. تشغيل خط البيانات (ELT Pipeline) واختيار المحرك التلقائي (Section 6.2)
يقوم الموجه التلقائي بفحص حجم الملف واختيار `python_batch` أو `pyspark`:
```bash
python main.py --input data/orders_sample.csv --batch-size 5000
```
أو بالصيغة القياسية:
```bash
python -m src.main --input data/orders_sample.csv --batch-size 5000
```

### 3. إثبات عدم التكرار (Idempotency Check)
عند إعادة تشغيل نفس الأمر على نفس الملف:
```bash
python main.py --input data/orders_sample.csv
```
ستلاحظ في المخرجات:
- `inserted_count: 0`
- `updated_count: 0`
- `unchanged_count: N`
- عدد السجلات في `orders_validated` لا يزيد إطلاقاً ولا يتم توليد سجلات تجارية مكررة!

### 4. مخرجات القياسات الرسمية (Metrics: Section 6.12)
يتم حفظ كافة العدادات والقياسات تلقائيًا في `reports/results.json`:
- `run_id`, `file_name`, `file_size_mb`, `engine_used`
- `rows_read`, `raw_loaded`
- `valid_count`, `corrected_count`, `quarantine_count`
- `elapsed_seconds`, `throughput` (سجل/ثانية)
- `counts_case_error` (تفصيل أعداد كل خطأ)
- `inserted_count`, `updated_count`, `unchanged_count`
- التحقق الرياضي: `run_raw_count = run_valid_count + run_corrected_count + run_quarantine_count`

---

## 🌟 تشغيل متطلبات المرحلة النهائية (Phase 2 - Big Data API & Analytics)

### 1. تشغيل واجهة الـ API الموحدة
```bash
python run_api.py
```
أو عبر uvicorn مباشرة:
```bash
uvicorn src.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```
- صفحة التوثيق التفاعلية (Swagger UI): **`http://127.0.0.1:8000/docs`**
- فحص الحالة: **`http://127.0.0.1:8000/health`**

### 2. استدعاء نقاط النهاية (API Endpoints):

| المسار (Endpoint) | الطريقة (Method) | الوصف والدور |
|---|---|---|
| `/health` | `GET` | فحص صحة الاتصال بقاعدة البيانات وحالة المجموعات |
| `/ingest` | `POST` | تشغيل خط المعالجة (`{"input_file": "data/orders_sample.csv", "batch_size": 5000}`) |
| `/indexes` | `POST` | إنشاء الفهارس الثلاثة المقررة (منها الفهرس المركب) |
| `/queries` | `GET` | عرض قائمة الاستعلامات العملية الخمسة |
| `/queries/{name}` | `GET` | تنفيذ استعلام عملي (`recent_orders`, `orders_by_city_status`, إلخ) |
| `/queries/{name}/explain` | `GET` | مقارنة خطة التنفيذ `explain("executionStats")` قبل الفهرس (COLLSCAN) وبعده (IXSCAN) مع توضيح السبب والأثر |
| `/aggregations` | `GET` | عرض قائمة تقارير التجميع الخمسة |
| `/aggregations/{name}` | `GET` | تنفيذ تقرير تجميع محدد وعرض نتائجه |
| `/refresh-mv` | `POST` | تنفيذ التحديث التزايدي للعروض المادية اعتماداً على العلامة المائية |
| `/views/{name}` | `GET` | استعراض بيانات العرض المادي (`daily_sales_summary` أو `top_products_summary`) |
| `/jobs` | `GET` | استعراض قائمة المهام المجدولة ومواعيدها |
| `/jobs/{name}/run` | `POST` | تشغيل مهمة مجدولة يدوياً وتوثيق النتيجة وحالة النجاح والوقت |
| `/jobs/logs` | `GET` | استعراض سجلات التدقيق لتنفيذ المهام ومواعيد بدايتها ونهايتها |

### 3. تشغيل عرض المرحلة النهائية وتوليد التقرير الشامل:
```bash
python final_phase.py --output final_phase_report.json
```
أو:
```bash
python -m src.final_phase --output final_phase_report.json
```

---

## 📊 الفهارس وتحليل خطط التنفيذ (Indexes & Explain Plan)

تم إنشاء 3 فهارس مخصصة لخدمة الاستعلامات:
1. **`idx_order_date`** (`{"order_date": -1}`):
   - **السبب:** تسريع الترتيب الزمني التنازلي وتجنب عمليات الفرز في الذاكرة (`In-memory Sort`).
   - **الاستعلام:** `recent_orders`.
2. **`idx_city_status`** (`{"city": 1, "status": 1}` — **فهرس مركب Compound Index**):
   - **السبب:** تصفية ثنائية متقدمة حسب الموقع الجغرافي وحالة الطلب معاً دون الحاجة لمسح الوثائق غير المطابقة في المدن الأخرى.
   - **الاستعلام:** `orders_by_city_status`.
3. **`idx_customer_id`** (`{"customer_id": 1}`):
   - **السبب:** تسريع استرجاع سجل طلبات العميل ومنع المسح الكامل للمجموعة.
   - **الاستعلام:** `customer_orders`.

عند فحص `/queries/{name}/explain`:
- **قبل الفهرس (Before):** ينفذ `COLLSCAN` ويفحص كامل وثائق المجموعة (`totalKeysExamined = 0` و `totalDocsExamined = N`).
- **بعد الفهرس (After):** ينفذ `IXSCAN` مع تقليل جذري في عدد الوثائق المفحوصة ليقتصر على المفاتيح المطابقة فقط مع تسريع ملحوظ في زمن التنفيذ.

---

## 📈 تقارير التجميع الخمسة (Aggregation Reports)

1. **`sales_by_city`:** إجمالي المبيعات وعدد الطلبات لكل مدينة.
2. **`top_products`:** أفضل المنتجات مباعة وإيرادات كل منتج اعتماداً على تفكيك عناصر الطلبات (`$unwind`).
3. **`top_customers`:** كبار العملاء مرتبين حسب إجمالي الإنفاق وعدد الطلبات.
4. **`sales_by_period`:** توزيع المبيعات الشهرية وتطور الإيرادات عبر الفترات الزمنية.
5. **`orders_by_status`:** توزيع أعداد وقيم الطلبات حسب حالات الإنجاز والتسليم.

---

## 🔄 العروض المادية التزايدية (Incremental Materialized Views)

1. **`daily_sales_summary`:** ملخص يومي لإجمالي المبيعات وعدد الطلبات لكل تاريخ.
2. **`top_products_summary`:** ملخص إجمالي الكميات المباعة والعائدات لكل رمز منتج (SKU).

- **آلية التحديث:** تستخدم دالة `refresh_incremental` مجموعة علامات مائية `mv_watermarks` لحفظ آخر توقيت معالجة `last_processed_at`. عند التشغيل، لا تقرأ إلا الوثائق الأحدث فقط وتستخدم معامل الزيادة التراكمية `$inc` في MongoDB دون إعادة بناء أو قراءة البيانات السابقة.

---

## ⏰ المهام المجدولة وتوثيق التنفيذ (Scheduled Jobs & Audit Logs)

1. **`refresh_materialized_views`:** مهمة دورية كل ساعة لتحديث العروض المادية تزايدياً.
2. **`write_daily_status_report`:** مهمة يومية الساعة 23:55 UTC لتشغيل تقرير الحالات وحفظ لقطة دورية.

- **سجل التدقيق:** كل تشغيل (يدوي أو مجدول) يتم توثيقه في مجموعة `job_logs` و `job_runs` متضمناً:
  - `job_name`
  - `started_at` (وقت البداية الدقيق)
  - `ended_at` (وقت النهاية)
  - `duration_seconds` (زمن التنفيذ بالثواني)
  - `status` (`SUCCESS` أو `FAILED`)
  - `result` (النتيجة أو تفاصيل الخطأ)

---

## 🧪 تشغيل الاختبارات المؤتمتة (Automated Tests)

المشروع مزود بحزمة اختبارات شاملة بـ 24 اختباراً تغطي جميع متطلبات التكليف:
```bash
pytest -v
```
**نتائج الاختبارات:**
```text
tests/test_classification.py::test_missing_order_id PASSED               [  4%]
tests/test_classification.py::test_missing_customer_id PASSED            [  8%]
tests/test_classification.py::test_impossible_date PASSED                [ 12%]
tests/test_classification.py::test_corrupted_items_json PASSED           [ 16%]
tests/test_classification.py::test_empty_items PASSED                    [ 20%]
tests/test_classification.py::test_unknown_price PASSED                  [ 25%]
tests/test_classification.py::test_ambiguous_negative_value PASSED       [ 29%]
tests/test_classification.py::test_multiple_conflicting_errors PASSED    [ 33%]
tests/test_cleaning_rules.py::test_arabic_and_persian_digits_normalization PASSED [ 37%]
tests/test_cleaning_rules.py::test_currency_normalization PASSED         [ 41%]
tests/test_cleaning_rules.py::test_clean_numeric_price_thousands_and_words PASSED [ 45%]
tests/test_cleaning_rules.py::test_yemeni_phone_normalization PASSED     [ 50%]
tests/test_cleaning_rules.py::test_email_repeated_symbols_correction PASSED [ 54%]
tests/test_cleaning_rules.py::test_date_standardization_and_boundaries PASSED [ 58%]
tests/test_cleaning_rules.py::test_status_normalization PASSED           [ 62%]
tests/test_cleaning_rules.py::test_order_audit_trail_generation PASSED   [ 66%]
tests/test_idempotency.py::test_idempotent_ingestion PASSED              [ 70%]
tests/test_phase2.py::test_api_health PASSED                             [ 75%]
tests/test_phase2.py::test_api_indexes PASSED                            [ 79%]
tests/test_phase2.py::test_api_queries PASSED                            [ 83%]
tests/test_phase2.py::test_api_explain PASSED                            [ 87%]
tests/test_api_aggregations PASSED                                       [ 91%]
tests/test_phase2.py::test_api_materialized_views PASSED                 [ 95%]
tests/test_phase2.py::test_api_jobs_and_execution_logging PASSED         [100%]
======================== 24 passed in 1.59s ========================
```

---

## 📋 مصفوفة مطابقة المتطلبات (Requirements Compliance Matrix)

| المتطلب في وثيقة التكليف | الحالة | المكون المسؤول |
|---|---|---|
| استخراج عينة صغيرة متدفقة دون تحميل الذاكرة | ✅ مكتمل | `create_small_sample.py` |
| موجه تلقائي للمحرك بحد فاصل 200MB | ✅ مكتمل | `src/router.py:choose_engine` |
| تحميل دفعي متدفق بـ Python مع قياسات الدفعات | ✅ مكتمل | `src/batch_loader.py` |
| دعم PySpark بمخطط ثابت للملفات الكبيرة | ✅ مكتمل | `src/spark_loader.py` |
| تحميل أولي خام كامل إلى `orders_raw` | ✅ مكتمل | `src/pipeline.py` |
| 8 قواعد تنظيف آلي مع سجل الأثر `corrections` | ✅ مكتمل | `src/quality_rules.py` |
| عزل السجلات غير القابلة للإصلاح في `orders_quarantine` | ✅ مكتمل | `src/pipeline.py` |
| معادلة الاتساق $raw = valid + corrected + quarantine$ | ✅ مكتمل | `src/pipeline.py` |
| فهرس فريد وUpsert لإثبات عدم التكرار (Idempotency) | ✅ مكتمل | `src/mongo.py` & `src/pipeline.py` |
| حفظ القياسات الرسمية في `reports/results.json` | ✅ مكتمل | `src/main.py` |
| 5 استعلامات عملية و3 فهارس (منها مركب) | ✅ مكتمل | `src/reports.py` & `src/mongo.py` |
| مقارنة خطط التنفيذ قبل وبعد عبر Explain | ✅ مكتمل | `src/reports.py:explain_before_after` |
| 5 تقارير Aggregation مستقلة تعيد نتائج حقيقية | ✅ مكتمل | `src/reports.py` |
| عرضان ماديان بتحديث تزايدي دون إعادة البناء | ✅ مكتمل | `src/materialized_views.py` |
| مهمتان مجدولتان مع تسجيل الوقت والحالة | ✅ مكتمل | `src/jobs.py` |
| واجهة API موحدة عبر FastAPI مع توثيق Swagger | ✅ مكتمل | `src/main.py` & `run_api.py` |
| تقرير المرحلة النهائية في `final_phase_report.json` | ✅ مكتمل | `src/final_phase.py` |
| حزمة اختبارات شاملة بـ 24 اختباراً ناجحاً | ✅ مكتمل | `tests/` |
