import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "orders_db")

RAW_COLLECTION = os.getenv("RAW_COLLECTION", "orders_raw")
VALIDATED_COLLECTION = os.getenv("VALIDATED_COLLECTION", "orders_validated")
QUARANTINE_COLLECTION = os.getenv("QUARANTINE_COLLECTION", "orders_quarantine")
JOB_LOGS_COLLECTION = os.getenv("JOB_LOGS_COLLECTION", "job_logs")
WATERMARK_COLLECTION = os.getenv("WATERMARK_COLLECTION", "mv_watermarks")
MV_DAILY_SALES = os.getenv("MV_DAILY_SALES", "daily_sales_summary")
MV_TOP_PRODUCTS = os.getenv("MV_TOP_PRODUCTS", "top_products_summary")

SMALL_FILE_THRESHOLD_MB = float(os.getenv("SMALL_FILE_THRESHOLD_MB", "200"))
DEFAULT_BATCH_SIZE = int(os.getenv("DEFAULT_BATCH_SIZE", "5000"))

REPORTS_DIR = BASE_DIR / "reports"
RESULTS_JSON_PATH = REPORTS_DIR / "results.json"
DATA_DIR = BASE_DIR / "data"
