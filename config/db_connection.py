# File: config/db_connection.py
import mysql.connector
from pymongo import MongoClient
from config.settings import Config

# ==========================================================
# 1. KẾT NỐI MONGODB (Cho AI)
# ==========================================================
class MongoDatabase:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDatabase, cls).__new__(cls)
            try:
                cls._instance.client = MongoClient(Config.MONGO_URI)
                cls._instance.db = cls._instance.client[Config.MONGO_DB_NAME]
                print(f"✅ [MongoDB] Đã kết nối tới database: {Config.MONGO_DB_NAME}")
            except Exception as e:
                print(f"❌ [MongoDB] Lỗi kết nối: {e}")
                cls._instance.db = None
        return cls._instance

    def get_collection(self, name):
        if self.db is not None:
            return self.db[name]
        return None

def get_mongo_db():
    return MongoDatabase().db

def get_db():
    return MongoDatabase().db

# ==========================================================
# 2. KẾT NỐI MYSQL (Chuyển sang Direct Connection để dứt điểm lỗi Pool)
# ==========================================================
def get_mysql_connection():
    """
    Tạo kết nối mới trực tiếp thay vì dùng Pool.
    Loại bỏ hoàn toàn lỗi 'queue is full' do xung đột thread khi Flask auto-reload.
    """
    try:
        conn = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DATABASE,
            port=Config.MYSQL_PORT
        )
        return conn
    except mysql.connector.Error as err:
        print(f"❌ [MySQL] Lỗi kết nối: {err}")
        raise err