"""
数据库服务
"""

from pymongo import MongoClient
import os

client = None
db = None

MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:tradingagents123@localhost:27017/")
MONGO_DB = os.getenv("MONGO_DB", "stockai")

async def init_db():
    global client, db
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    
    # 创建索引
    db.users.create_index("username", unique=True)
    db.users.create_index("email", unique=True)
    db.analysis.create_index([("user_id", 1), ("created_at", -1)])
    db.favorites.create_index([("user_id", 1), ("symbol", 1)])

async def close_db():
    if client:
        client.close()

def get_db():
    return db
