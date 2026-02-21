"""
会员路由
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timedelta

from app.routers.auth import get_current_user
from app.services.database import get_db

router = APIRouter()

# 套餐配置
def check_and_update_usage(user: dict) -> dict:
    """检查并更新用户使用量"""
    from datetime import datetime
    db = get_db()
    
    membership = user.get("membership", {})
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    
    # 检查是否是同一天
    last_date = membership.get("last_date", "")
    if last_date != today:
        membership["used_today"] = 0
        membership["last_date"] = today
    
    daily_limit = membership.get("daily_limit", 3)
    used = membership.get("used_today", 0)
    
    # 免费用户检查次数
    if daily_limit > 0 and used >= daily_limit:
        raise HTTPException(status_code=403, detail="今日免费次数已用完，请升级会员")
    
    # 更新使用次数
    used += 1
    membership["used_today"] = used
    
    db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"membership": membership}}
    )
    
    remaining = -1 if daily_limit == -1 else max(0, daily_limit - used)
    
    return {
        "used_today": used,
        "daily_limit": daily_limit,
        "remaining": remaining
    }

PLANS = {
    "free": {
        "id": "free",
        "name": "免费用户",
        "price": 0,
        "daily_limit": 3,
        "features": ["每日3次", "基础分析"]
    },
    "vip": {
        "id": "vip",
        "name": "VIP会员",
        "price": 99,
        "daily_limit": -1,
        "features": ["无限次", "高级分析", "优先处理"]
    },
    "svip": {
        "id": "svip",
        "name": "SVIP会员", 
        "price": 199,
        "daily_limit": -1,
        "features": ["无限次", "深度分析", "历史记录", "专属客服"]
    }
}

@router.get("/plans")
async def get_plans():
    """获取套餐列表"""
    plans = []
    for level, plan in PLANS.items():
        p = plan.copy()
        if level == "vip":
            p["recommended"] = True
        plans.append(p)
    return {"success": True, "data": plans}

@router.get("/info")
async def get_membership_info(user: dict = Depends(get_current_user)):
    """获取会员信息"""
    membership = user.get("membership", {})
    
    daily_limit = membership.get("daily_limit", 3)
    used_today = membership.get("used_today", 0)
    
    return {
        "success": True,
        "data": {
            "level": membership.get("level", "free"),
            "expire_at": membership.get("expire_at"),
            "daily_limit": daily_limit,
            "used_today": used_today,
            "remaining": -1 if daily_limit == -1 else max(0, daily_limit - used_today)
        }
    }

@router.post("/upgrade")
async def upgrade_membership(
    level: str,
    user: dict = Depends(get_current_user)
):
    """升级会员 (测试模式)"""
    if level not in PLANS:
        raise HTTPException(status_code=400, detail="无效的会员等级")
    
    db = get_db()
    
    # 计算过期时间
    days = 30 if level == "vip" else 90
    expire_at = datetime.now() + timedelta(days=days)
    
    # 更新会员信息
    membership = user.get("membership", {})
    membership["level"] = level
    membership["expire_at"] = expire_at
    membership["daily_limit"] = PLANS[level]["daily_limit"]
    
    db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"membership": membership}}
    )
    
    return {
        "success": True,
        "message": f"已升级为 {PLANS[level]['name']}",
        "data": {
            "level": level,
            "expire_at": expire_at.strftime("%Y-%m-%d %H:%M:%S"),
            "daily_limit": PLANS[level]["daily_limit"]
        }
    }

@router.get("/admin/users")
async def admin_list_users(user: dict = Depends(get_current_user)):
    """管理员 - 用户列表"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="权限不足")
    
    db = get_db()
    users = list(db.users.find({}, {"password": 0}))
    
    for u in users:
        u["_id"] = str(u["_id"])
        if u.get("created_at"):
            a["created_at"] = str(u["created_at"])[:10]("%Y-%m-%d")
    
    return {"success": True, "data": users}

# ====== 管理员功能 ======
@router.get("/admin/stats")
async def get_admin_stats(user: dict = Depends(get_current_user)):
    """获取系统统计数据"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="权限不足")
    
    db = get_db()
    
    # 用户统计
    total_users = db.users.count_documents({})
    
    # 会员统计
    vip_users = db.users.count_documents({"membership.level": "vip"})
    svip_users = db.users.count_documents({"membership.level": "svip"})
    
    # 分析次数统计
    today = datetime.now().strftime("%Y-%m-%d")
    analyses_today = db.analysis.count_documents({
        "created_at": {"$gte": datetime.strptime(today, "%Y-%m-%d")}
    })
    analyses_total = db.analysis.count_documents({})
    
    return {
        "success": True,
        "data": {
            "total_users": total_users,
            "vip_users": vip_users,
            "svip_users": svip_users,
            "analyses_today": analyses_today,
            "analyses_total": analyses_total
        }
    }

@router.get("/admin/users")
async def admin_list_users(user: dict = Depends(get_current_user), page: int = 1, limit: int = 20):
    """管理员获取用户列表"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="权限不足")
    
    db = get_db()
    skip = (page - 1) * limit
    
    users = list(db.users.find({}, {"password": 0}).skip(skip).limit(limit))
    total = db.users.count_documents({})
    
    for u in users:
        u["_id"] = str(u["_id"])
        if u.get("created_at"):
            a["created_at"] = str(u["created_at"])[:10]("%Y-%m-%d")
    
    return {
        "success": True,
        "data": {
            "users": users,
            "total": total,
            "page": page,
            "limit": limit
        }
    }

@router.post("/admin/user/{user_id}/membership")
async def admin_update_membership(user_id: str, level: str = "free", expire: str = None, user: dict = Depends(get_current_user)):
    """管理员修改用户会员等级"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="权限不足")
    
    if level not in PLANS and level != "free":
        raise HTTPException(status_code=400, detail="无效的会员等级")
    
    db = get_db()
    from bson import ObjectId
    
    # 计算过期时间
    if expire:
        try:
            expire_at = datetime.strptime(expire, "%Y-%m-%d")
        except:
            expire_at = datetime.now() + timedelta(days=30)
    else:
        days = 30 if level == "vip" else 90 if level == "svip" else 0
        expire_at = datetime.now() + timedelta(days=days) if days > 0 else None
    
    membership = {
        "level": level,
        "expire_at": expire_at.strftime("%Y-%m-%d %H:%M:%S") if expire_at else None,
        "daily_limit": PLANS.get(level, {}).get("daily_limit", 3) if level != "free" else 3
    }
    
    # 尝试用ObjectId查询
    try:
        db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {"membership": membership}}
        )
    except:
        # 如果不是ObjectId，尝试用username查询
        db.users.update_one(
            {"username": user_id},
            {"$set": {"membership": membership}}
        )
    
    plan_name = PLANS.get(level, {}).get("name", "免费用户")
    return {"success": True, "message": f"已更新会员等级为 {plan_name}，到期时间: {expire or '无'}" if expire else f"已更新会员等级为 {plan_name}"}

# 文章管理
@router.get("/admin/articles")
async def admin_list_articles(user: dict = Depends(get_current_user), page: int = 1, limit: int = 20):
    """获取文章列表"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="权限不足")
    
    db = get_db()
    skip = (page - 1) * limit
    
    articles = list(db.articles.find({}).skip(skip).limit(limit).sort("created_at", -1))
    total = db.articles.count_documents({})
    
    for a in articles:
        a["_id"] = str(a["_id"])
        if a.get("created_at"):
            a["created_at"] = str(a["created_at"])[:10]("%Y-%m-%d")
    
    return {
        "success": True,
        "data": {
            "articles": articles,
            "total": total,
            "page": page,
            "limit": limit
        }
    }

@router.post("/admin/article")
async def admin_create_article(title: str, content: str, user: dict = Depends(get_current_user)):
    """创建文章"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="权限不足")
    
    db = get_db()
    article = {
        "title": title,
        "content": content,
        "author": user["username"],
        "created_at": datetime.now(),
        "status": "published"
    }
    db.articles.insert_one(article)
    
    return {"success": True, "message": "文章创建成功"}

@router.delete("/admin/article/{article_id}")
async def admin_delete_article(article_id: str, user: dict = Depends(get_current_user)):
    """删除文章"""
    if not user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="权限不足")
    
    from bson import ObjectId
    db = get_db()
    db.articles.delete_one({"_id": ObjectId(article_id)})
    
    return {"success": True, "message": "文章已删除"}
