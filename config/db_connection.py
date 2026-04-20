# File: config/db_connection.py
from pymongo import MongoClient
from config.settings import Config # Sửa phần import này

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
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

def get_db():
    return Database().db