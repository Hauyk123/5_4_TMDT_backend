# File: config/settings.py
import os
from dotenv import load_dotenv

# Load các biến môi trường từ file .env
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))


class Config:
    BASE_DIR = BASE_DIR

    # Cấu hình bảo mật và MongoDB
    SECRET_KEY = os.environ.get('SECRET_KEY')
    MONGO_URI = os.environ.get('MONGO_URI')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME')

    # --- BỔ SUNG TÊN COLLECTION MONGODB ---
    COL_PRODUCTS = 'products'  # Hoặc 'metadata' tùy thuộc vào tên bảng bạn đã nạp vào Mongo
    COL_REVIEWS = 'reviews'

    # Cấu hình thư mục Data cho AI
    DATA_DIR = os.path.join(BASE_DIR, 'ai_core', 'data')
    FILE_REVIEWS = 'Appliances.jsonl.gz'
    FILE_META = 'meta_Appliances.jsonl.gz'

    # Cấu hình MySQL
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DATABASE = os.environ.get('MYSQL_DATABASE', 'tmdt_giadung')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))