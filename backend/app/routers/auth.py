"""
认证路由 - 支持QQ邮箱SMTP验证码
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from datetime import datetime, timedelta
import jwt
import hashlib
import time
import random
import string
import smtplib
from email.mime.text import MIMEText

from app.services.database import get_db

router = APIRouter()

SECRET_KEY = "stockai-secret-key-change-in-production"
ALGORITHM = "HS256"

# QQ邮箱SMTP配置
SMTP_CONFIG = {
    "smtp_server": "smtp.qq.com",
    "smtp_port": 587,
    "username": "janus.hu@qq.com",
    "password": "pxzemgltuqjvbchd"  # QQ邮箱授权码
}

# 验证码存储 (生产环境用Redis)
verification_codes = {}

def send_email(to_email: str, code: str):
    """发送验证码邮件"""
    try:
        msg = MIMEText(f"您的注册验证码是: {code}\n\n有效期10分钟，请勿泄露给他人。", "plain", "utf-8")
        msg["Subject"] = "StockAI 注册验证码"
        msg["From"] = SMTP_CONFIG["username"]
        msg["To"] = to_email
        
        server = smtplib.SMTP(SMTP_CONFIG["smtp_server"], SMTP_CONFIG["smtp_port"])
        server.starttls()
        server.login(SMTP_CONFIG["username"], SMTP_CONFIG["password"])
        server.sendmail(SMTP_CONFIG["username"], [to_email], msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"发送邮件失败: {e}")
        return False

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
    code: str

class LoginRequest(BaseModel):
    username: str
    password: str

class SendCodeRequest(BaseModel):
    email: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def create_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(days=7)
    payload = {"sub": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except:
        return None

async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未授权", headers={"WWW-Authenticate": "Bearer"})
    
    token = authorization.replace("Bearer ", "")
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Token无效")
    
    db = get_db()
    user = db.users.find_one({"username": username})
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    # 移除密码字段
    user.pop("password", None)
    return user

@router.post("/send-code")
async def send_code(request: SendCodeRequest):
    """发送验证码到邮箱"""
    code = ''.join(random.choices(string.digits, k=6))
    verification_codes[request.email] = {"code": code, "expire": time.time() + 600}  # 10分钟有效
    
    # 发送邮件
    if send_email(request.email, code):
        print(f"📧 验证码已发送到 {request.email}: {code}")
        return {"success": True, "message": "验证码已发送到您的邮箱"}
    else:
        return {"success": False, "detail": "发送失败，请稍后重试"}

@router.post("/register")
async def register(request: RegisterRequest):
    """用户注册 - 需要邮箱验证码"""
    db = get_db()
    
    # 验证邮箱验证码
    if not request.email or request.email not in verification_codes:
        raise HTTPException(status_code=400, detail="请先获取邮箱验证码")
    
    stored = verification_codes[request.email]
    if time.time() > stored["expire"]:
        del verification_codes[request.email]
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    
    if stored["code"] != request.code:
        raise HTTPException(status_code=400, detail="验证码错误")
    
    # 检查用户名和邮箱
    if db.users.find_one({"username": request.username}):
        raise HTTPException(status_code=400, detail="用户名已存在")
    
    if db.users.find_one({"email": request.email}):
        raise HTTPException(status_code=400, detail="邮箱已被注册")
    
    user = {
        "username": request.username,
        "email": request.email,
        "password": hash_password(request.password),
        "membership": {
            "level": "free",
            "expire_at": None,
            "daily_limit": 3,
            "used_today": 0,
            "last_reset_date": None
        },
        "created_at": datetime.now(),
        "is_admin": False
    }
    db.users.insert_one(user)
    
    return {"success": True, "message": "注册成功"}

@router.post("/login")
async def login(request: LoginRequest):
    """用户登录"""
    db = get_db()
    user = db.users.find_one({"username": request.username})
    
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    if user["password"] != hash_password(request.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    token = create_token(request.username)
    
    return {
        "success": True,
        "data": {
            "access_token": token,
            "user": {
                "username": user["username"],
                "email": user["email"],
                "membership": user.get("membership", {}),
                "is_admin": user.get("is_admin", False)
            }
        }
    }

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "username": user["username"],
        "email": user["email"],
        "membership": user.get("membership", {})
    }
