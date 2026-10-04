from fastapi import FastAPI
import uvicorn
from pymongo import MongoClient


from src.router import create_router

app = FastAPI(title="Orders Data Engineering API", version="2.0.0")

client = MongoClient("mongodb://localhost:27017/")
db = client["orders_db"]  # تأكد`ي من وضع اسم قاعدة البيانات الصحيح الخاص بمشروعك

# إنشاء الموجه وتمرير قاعدة البيانات له
api_router = create_router(db)

# ربط الموجه بالتطبيق الأساسي
app.include_router(api_router)

if name == "main":
    uvicorn.run(app, host="127.0.0.1", port=8000)