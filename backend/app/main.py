"""
StockAI - 轻量级股票分析后端
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.routers import auth, analysis, membership, stocks
from app.services.database import init_db, close_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    await init_db()
    yield
    # 关闭
    await close_db()

app = FastAPI(
    title="StockAI API",
    description="轻量级股票分析平台",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(analysis.router, prefix="/api/analysis", tags=["分析"])
app.include_router(membership.router, prefix="/api/membership", tags=["会员"])
app.include_router(stocks.router, prefix="/api/stocks", tags=["股票"])

@app.get("/")
def root():
    return FileResponse("html/v6.html")

@app.get("/health")
def health():
    return {"status": "ok"}

# Serve frontend
FRONTEND_PATH = "/app/html"

def no_cache_file_response(path):
    response = FileResponse(path)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.get("/v2.html")
async def serve_frontend():
    return no_cache_file_response(os.path.join(FRONTEND_PATH, "v2.html"))

@app.get("/v3.html")
async def serve_frontend_v3():
    return no_cache_file_response(os.path.join(FRONTEND_PATH, "v3.html"))

@app.get("/{path:path}")
async def serve_static(path: str):
    if path == "v2.html":
        return no_cache_file_response(os.path.join(FRONTEND_PATH, "v2.html"))
    if path == "v3.html":
        return no_cache_file_response(os.path.join(FRONTEND_PATH, "v3.html"))
    file_path = os.path.join(FRONTEND_PATH, path)
    if os.path.isfile(file_path):
        return no_cache_file_response(file_path)
    return no_cache_file_response(os.path.join(FRONTEND_PATH, "v2.html"))
