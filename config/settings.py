# File: config/settings.py
import os
from dotenv import load_dotenv

# Load các biến môi trường từ file .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))


class Config:
    BASE_DIR = BASE_DIR  # <--- DÒNG MỚI ĐƯỢC THÊM VÀO ĐÂY

    SECRET_KEY = os.environ.get('SECRET_KEY')
    MONGO_URI = os.environ.get('MONGO_URI')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME')

    # Cấu hình thư mục Data cho AI
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    FILE_REVIEWS = 'Appliances.jsonl.gz'
    FILE_META = 'meta_Appliances.jsonl.gz'