"""
股票分析路由
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
import os

from app.routers.auth import get_current_user
from app.services.database import get_db
from app.routers.membership import check_and_update_usage

router = APIRouter()

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-fb25bfaea4614d32b89cead05c8293c0")

class AnalyzeRequest(BaseModel):
    symbol: str

async def analyze_stock(symbol: str) -> dict:
    """使用 AI 多维度分析股票"""
    
    prompt = f"""你是一个资深的股票分析师，具有10年以上从业经验。请对股票 {symbol} 进行全面专业的投资分析。

请按照以下维度进行详细分析：

## 1. 技术面分析
- 短期趋势判断
- 关键技术指标
- 支撑位与压力位

## 2. 基本面分析
- 公司主营业务
- 营收及利润情况
- 核心竞争力

## 3. 估值分析
- PE/PB分析
- 与行业对比

## 4. 新闻与事件
- 近期重大消息

## 5. 风险评估

## 6. 综合评级
请用专业的中文进行分析。"""

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 3000
    }
    
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=90)
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            return {
                "analysis": result["choices"][0]["message"]["content"],
                "model": "deepseek-chat"
            }
        else:
            return {"analysis": "分析服务暂时不可用", "error": str(result)}
    except Exception as e:
        return {"analysis": f"分析失败: {str(e)}", "error": str(e)}

@router.post("/analyze")
async def analyze(request: AnalyzeRequest, user: dict = Depends(get_current_user)):
    """分析股票"""
    membership = check_and_update_usage(user)
    
    result = await analyze_stock(request.symbol)
    
    # 获取股票名称
    stock_name = request.symbol
    try:
        if request.symbol.startswith("6"):
            secid = f"1.{request.symbol}"
        else:
            secid = f"0.{request.symbol}"
        quote_resp = requests.get(f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f58", timeout=5)
        quote_data = quote_resp.json()
        if quote_data.get("data"):
            stock_name = quote_data["data"].get("f58", request.symbol)
    except:
        pass
    
    db = get_db()
    record = {
        "user_id": str(user["_id"]),
        "username": user["username"],
        "symbol": request.symbol,
        "name": stock_name,
        "analysis": result.get("analysis", ""),
        "model": result.get("model", ""),
        "used_today": membership.get("used_today", 1),
        "created_at": datetime.now()
    }
    db.analysis.insert_one(record)
    
    return {
        "success": True,
        "data": {
            "symbol": request.symbol,
            "name": stock_name,
            "analysis": result.get("analysis", ""),
            "used_today": membership.get("used_today", 1),
            "remaining": membership.get("remaining", 0)
        }
    }

@router.get("/history")
async def get_history(user: dict = Depends(get_current_user), limit: int = 10):
    """获取分析历史"""
    db = get_db()
    records = list(db.analysis.find(
        {"user_id": str(user["_id"])}
    ).sort("created_at", -1).limit(limit))
    
    for r in records:
        r["_id"] = str(r["_id"])
        r["id"] = str(r["_id"])
        if not r.get("name"):
            symbol = r.get("symbol", "")
            try:
                if symbol.startswith("6"):
                    secid = f"1.{symbol}"
                else:
                    secid = f"0.{symbol}"
                resp = requests.get(f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f58", timeout=3)
                data = resp.json()
                if data.get("data"):
                    r["name"] = data["data"].get("f58", symbol)
                else:
                    r["name"] = symbol
            except:
                r["name"] = symbol
        r["created_at"] = r["created_at"].strftime("%Y-%m-%d %H:%M")
    
    return {"success": True, "data": records}

@router.get("/history/{record_id}")
async def get_history_record(record_id: str, user: dict = Depends(get_current_user)):
    """获取单条分析记录"""
    from bson import ObjectId
    db = get_db()
    
    try:
        record = db.analysis.find_one({
            "_id": ObjectId(record_id),
            "user_id": str(user["_id"])
        })
    except:
        return {"success": False, "error": "无效的记录ID"}
    
    if not record:
        return {"success": False, "error": "记录未找到"}
    
    record["_id"] = str(record["_id"])
    record["created_at"] = record["created_at"].strftime("%Y-%m-%d %H:%M:%S")
    
    return {"success": True, "data": record}

# ====== 股票走势预测 ======
@router.post("/predict")
async def predict_stock(request: AnalyzeRequest, user: dict = Depends(get_current_user)):
    """预测股票走势"""
    membership = check_and_update_usage(user)
    
    symbol = request.symbol
    
    # 获取K线数据
    if symbol.startswith("6"):
        secid = f"1.{symbol}"
    else:
        secid = f"0.{symbol}"
    
    url = f"https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61&klt=101&fqt=0&beg=20250101&end=20260221"
    
    kline_data = []
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("data") and data["data"].get("klines"):
            kline_data = data["data"]["klines"][-30:]
    except Exception as e:
        return {"success": False, "error": f"获取数据失败: {str(e)}"}
    
    if not kline_data:
        return {"success": False, "error": "无法获取K线数据"}
    
    kline_summary = "\n".join([f"{d[:10]} 开盘:{d.split(',')[1]} 收盘:{d.split(',')[2]} 最高:{d.split(',')[3]} 最低:{d.split(',')[4]} 成交量:{d.split(',')[5]}" for d in kline_data])
    
    prompt = f"""你是一个资深的股票量化分析师。请根据以下股票历史K线数据预测未来走势。

股票代码: {symbol}

最近30个交易日数据:
{kline_summary}

请分析并预测:
1. 短期走势（1周内）
2. 中期走势（1个月内）
3. 关键支撑位和压力位
4. 操作建议

请用专业的中文进行分析。"""
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=data, timeout=90)
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            prediction = result["choices"][0]["message"]["content"]
        else:
            prediction = "预测服务暂时不可用"
    except Exception as e:
        prediction = f"预测失败: {str(e)}"
    
    # 保存预测记录
    db = get_db()
    record = {
        "user_id": str(user["_id"]),
        "username": user["username"],
        "symbol": symbol,
        "prediction": prediction,
        "type": "predict",
        "used_today": membership.get("used_today", 1),
        "created_at": datetime.now()
    }
    db.analysis.insert_one(record)
    
    return {
        "success": True,
        "data": {
            "symbol": symbol,
            "prediction": prediction
        }
    }
