"""
股票筛选路由 - 实时数据版 (A股+港股+美股)
"""

# Global cache
ALL_STOCKS = []
CACHE_LOADED = False

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
import requests

from app.routers.auth import get_current_user
from app.services.database import get_db

router = APIRouter()

# 东方财富实时行情接口
DFCF_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"

async def get_stock_list(market: str = "a", page: int = 1, size: int = 100) -> list:
    """获取股票列表
    market: a=A股, hk=港股, us=美股
    """
    # A股: 沪深两市
    if market == "a":
        params = {
            "pn": page,
            "pz": size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:0+t:81,m:1+t:80",
            "fields": "f2,f3,f4,f5,f12,f13,f14"
        }
    # 港股
    elif market == "hk":
        params = {
            "pn": page,
            "pz": size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:81+s:2",
            "fields": "f2,f3,f4,f5,f12,f13,f14"
        }
    # 美股
    elif market == "us":
        params = {
            "pn": page,
            "pz": size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:81+s:1",
            "fields": "f2,f3,f4,f5,f12,f13,f14"
        }
    # 默认A股
    else:
        params = {
            "pn": page,
            "pz": size,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:0+t:81,m:1+t:80",
            "fields": "f2,f3,f4,f5,f12,f13,f14"
        }
    
    try:
        resp = requests.get(DFCF_LIST_URL, params=params, timeout=10)
        data = resp.json()
        
        stocks = []
        if data.get("data", {}).get("diff"):
            for item in data["data"]["diff"]:
                code = item.get("f12", "")
                # 美股需要加前缀
                if market == "us" and code and not code.startswith(("A", "B")):
                    code = "US." + code
                # 港股需要加后缀
                elif market == "hk" and code:
                    code = code + ".HK"
                    
                stocks.append({
                    "code": code,
                    "name": item.get("f14"),
                    "price": item.get("f2") or 0,
                    "change": item.get("f4") or 0,
                })
        return stocks
    except Exception as e:
        print(f"Error fetching stock list: {e}")
        return []

@router.get("/list")
async def get_list(
    market: str = Query("a", description="市场: a=A股, hk=港股, us=美股"),
    page: int = Query(1, description="页码"),
    size: int = Query(100, description="每页数量")
):
    """获取股票列表"""
    stocks = await get_stock_list(market, page, size)
    
    return {"success": True, "data": stocks, "total": len(stocks), "market": market}

@router.get("/search")
async def search_stock(q: str = Query("", description="搜索关键词")):
    """搜索股票 - 支持A股"""
    global ALL_STOCKS, CACHE_LOADED
    
    if not q:
        return {"success": True, "data": []}
    
    # Load cache on first call
    if not CACHE_LOADED:
        print("Loading stock cache...")
        try:
            for page in range(1, 101):
                params = {
                    "pn": page,
                    "pz": 100,
                    "po": 1,
                    "np": 1,
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": 2,
                    "invt": 2,
                    "fid": "f3",
                    # Try different filter to get more stocks
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                    "fields": "f2,f3,f4,f5,f12,f13,f14"
                }
                resp = requests.get(DFCF_LIST_URL, params=params, timeout=5)
                data = resp.json()
                if not data.get("data", {}).get("diff"):
                    break
                for item in data["data"]["diff"]:
                    ALL_STOCKS.append({
                        "code": str(item.get("f12", "")),
                        "name": item.get("f14", "") or "",
                        "price": item.get("f2") or 0,
                        "change": item.get("f4") or 0,
                    })
            CACHE_LOADED = True
            print(f"Cache loaded: {len(ALL_STOCKS)} stocks")
        except Exception as e:
            print(f"Cache error: {e}")
    
    # Search in cache - use set to avoid duplicates
    results = []
    seen = set()
    q_lower = q.lower()
    for stock in ALL_STOCKS:
        if stock["code"] in seen:
            continue
        if q in stock["code"] or q in stock["name"] or q_lower in stock["name"].lower():
            results.append(stock)
            seen.add(stock["code"])
        if len(results) >= 30:
            break
    
    return {"success": True, "data": results}

@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    """获取实时行情 - 使用股票详情API"""
    if symbol.endswith(".HK"):
        secid = f"116.{symbol.replace('.HK', '')}"
    elif symbol.startswith("US."):
        secid = f"105.{symbol.replace('US.', '')}"
    else:
        if symbol.startswith("6"):
            secid = f"1.{symbol}"
        else:
            secid = f"0.{symbol}"
    
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f57,f58,f60,f116,f162,f173"
    
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        
        if data.get("rc") != 0 or not data.get("data"):
            return {"success": False, "error": "股票未找到"}
        
        d = data["data"]
        return {
            "success": True,
            "data": {
                "symbol": d.get("f57"),
                "name": d.get("f58"),
                "price": d.get("f43", 0) / 100 if d.get("f43") else 0,
                "change": d.get("f44", 0) / 100 if d.get("f44") else 0,
                "change_pct": d.get("f45", 0) / 100 if d.get("f45") else 0,
                "volume": d.get("f46", 0),
                "amount": d.get("f47", 0),
                "high": d.get("f60", 0) / 100 if d.get("f60") else 0,
                "open": 0,
                "close": d.get("f43", 0) / 100 if d.get("f43") else 0,
                "turnover": d.get("f173", 0),
            }
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

class FavoriteRequest(BaseModel):
    symbol: str
    name: str

@router.post("/favorite")
async def add_favorite(req: FavoriteRequest, user: dict = Depends(get_current_user)):
    """添加自选股"""
    db = get_db()
    
    existing = db.favorites.find_one({
        "user_id": str(user["_id"]),
        "symbol": req.symbol
    })
    
    if existing:
        return {"success": False, "message": "股票已在自选"}
    
    db.favorites.insert_one({
        "user_id": str(user["_id"]),
        "symbol": req.symbol,
        "name": req.name,
        "created_at": "now"
    })
    
    return {"success": True, "message": "添加成功"}

@router.get("/favorites")
async def get_favorites(user: dict = Depends(get_current_user)):
    """获取自选股"""
    db = get_db()
    favorites = list(db.favorites.find({"user_id": str(user["_id"])}))
    
    for f in favorites:
        f["_id"] = str(f["_id"])
    
    return {"success": True, "data": favorites}

@router.delete("/favorite/{symbol}")
async def remove_favorite(symbol: str, user: dict = Depends(get_current_user)):
    """删除自选股"""
    db = get_db()
    db.favorites.delete_one({"user_id": str(user["_id"]), "symbol": symbol})
    
    return {"success": True, "message": "删除成功"}
