# -*- coding: utf-8 -*-
"""FastAPI server endpoint for sleep screenshot analysis."""

import asyncio
import json
import sys
import os
import queue
import shutil
import uuid
import logging
from datetime import datetime

import markdown
from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Request, UploadFile, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

# 加载当前目录下的 .env 文件
load_dotenv()

# 确保项目根目录在 sys.path 中，以便找到 app.utils
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("server")

try:
    from .store import ServerSleepStore
    from .runtime_config import ensure_server_runtime_config
    from .analyzer import SleepAnalyzer
except (ImportError, ValueError):
    from store import ServerSleepStore
    from runtime_config import ensure_server_runtime_config
    from analyzer import SleepAnalyzer

from app.utils.utils import resource_path
import logging
import uvicorn

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ATTACHMENTS_DIR = resource_path(os.path.join("server", "attachments"))

ensure_server_runtime_config()

app = FastAPI(title="MyTimeLogger Sleep Server API", version="1.0")
store = ServerSleepStore()
progress_queues: dict[str, queue.Queue] = {}


auth_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(auth_scheme)):
    token = credentials.credentials
    user = store.get_user_by_session(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

def get_current_user_optional(x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"), credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False))):
    """支持 Legacy Token 和 Bearer Token"""
    if credentials:
        user = store.get_user_by_session(credentials.credentials)
        if user: return user
    
    # Legacy 模式：匹配环境变量设置的 Token
    legacy_token = os.getenv("SLEEP_AUTH_TOKEN")
    if legacy_token and x_auth_token == legacy_token:
        uid = store.get_default_user_id()
        if uid: return {"id": uid, "username": "legacy_user"}
    
    raise HTTPException(status_code=401, detail="Authentication required")


def build_ai_cfg():
    return {
        "vision_base_url": os.getenv("VISION_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        "vision_api_key": os.getenv("VISION_API_KEY", ""),
        "vision_model": os.getenv("VISION_MODEL", "glm-4v-flash"),
        "text_base_url": os.getenv("TEXT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        "text_api_key": os.getenv("TEXT_API_KEY", ""),
        "text_model": os.getenv("TEXT_MODEL", "glm-4-flash"),
        "backup_base_url": os.getenv("BACKUP_BASE_URL", ""),
        "backup_api_key": os.getenv("BACKUP_API_KEY", ""),
        "backup_model": os.getenv("BACKUP_MODEL", ""),
    }


def _queue_for(request_id):
    if request_id not in progress_queues:
        progress_queues[request_id] = queue.Queue(maxsize=50)
    return progress_queues[request_id]


def _push_progress(request_id, payload):
    q = _queue_for(request_id)
    try:
        q.put_nowait(payload)
    except queue.Full:
        pass


def _public_job(job):
    if not job:
        return None
    # 兼容处理：支持从 store._row_to_dict 出来的 sleep_data 字段
    result = job.get("sleep_data") or {}
    # 优先从字段读取，如果没有则从 result 字典里读
    raw_report = job.get("analysis_report") or result.get("analysis_report") or ""
    
    if raw_report:
        result = dict(result)
        result["analysis_report"] = raw_report
        result["analysis_html"] = markdown.markdown(raw_report, extensions=["fenced_code", "tables"])
    
    return {
        "request_id": job.get("request_id"),
        "date": job.get("date") or result.get("date") or result.get("sleep_date"),
        "status": job.get("status"),
        "updated_at": job.get("updated_at"),
        "error": job.get("error"),
        "result": result,
    }


def _run_analysis(request_id, image_path, user_id):
    store.mark_running(request_id)
    _push_progress(request_id, {"status": "running", "msg": "开始服务端睡眠分析..."})

    def progress(msg):
        _push_progress(request_id, {"status": "progress", "msg": msg})

    analyzer = SleepAnalyzer(
        ai_cfg=build_ai_cfg(),
        image_path=image_path,
        include_time_analysis=False,
        db=None,
        progress_callback=progress,
    )
    result = analyzer.analyze()
    if result.status == "done":
        sleep_data = result.sleep_data or {}
        if result.analysis_report:
            sleep_data["analysis_report"] = result.analysis_report
        store.mark_done(request_id, result.date, sleep_data, result.analysis_report)
        _push_progress(request_id, {"status": "done", "result": sleep_data})
    else:
        store.mark_error(request_id, result.error)
        _push_progress(request_id, {"status": "error", "msg": result.error})


@app.post("/auth/register")
async def register(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if store.create_user(username, password):
        logger.info(f"🆕 New user registered: {username}")
        return {"status": "ok", "msg": "Registration successful"}
    logger.warning(f"⚠️ Registration failed (user exists): {username}")
    raise HTTPException(status_code=400, detail="Username already exists")


@app.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    user_id = store.verify_user(username, password)
    if user_id:
        token = store.create_session(user_id)
        logger.info(f"✅ User logged in: {username} (ID: {user_id})")
        return {"status": "ok", "token": token, "username": username}
    logger.warning(f"❌ Login failed for user: {username}")
    raise HTTPException(status_code=401, detail="Invalid username or password")


@app.get("/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": user}


@app.get("/ping")
def ping():
    return {"status": "ok", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/", response_class=FileResponse)
def index():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    return FileResponse(template_path)


@app.post("/upload")
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user_optional),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image uploads are accepted")
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large")

    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    request_id = uuid.uuid4().hex
    safe_name = "".join(c for c in (file.filename or "upload.jpg") if c.isalnum() or c in ".-_")
    # 路径修正：现在 analyzer.py 在 server/ 子目录下，skills 在根目录
    root_dir = os.path.dirname(os.path.dirname(__file__))
    skill_dir = os.path.join(root_dir, "skills", "time-management")
    image_path = os.path.join(ATTACHMENTS_DIR, f"{request_id}_{safe_name}")
    
    logger.info(f"📤 Upload received: {file.filename} -> {request_id} (User: {user['username']})")
    
    with open(image_path, "wb") as out:
        out.write(content)
    store.create_job(request_id, image_path, user_id=user["id"])
    background_tasks.add_task(_run_analysis, request_id, image_path, user_id=user["id"])
    return {"status": "ok", "request_id": request_id}


@app.get("/status/{request_id}")
def get_job_status(request_id: str, user: dict = Depends(get_current_user_optional)):
    job = store.get_job(request_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="request_id not found")
    return _public_job(job)


@app.get("/status_by_date/{date}")
def get_job_by_date(date: str, user: dict = Depends(get_current_user_optional)):
    job = store.get_job_by_date(date, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="date not found")
    return {"status": "ok", "result": _public_job(job)}


@app.get("/events/{request_id}")
async def events(request_id: str, request: Request, user: dict = Depends(get_current_user_optional)):
    if not store.get_job(request_id, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="request_id not found")
    q = _queue_for(request_id)

    async def event_stream():
        while True:
            if await request.is_disconnected():
                break
            try:
                item = q.get_nowait()
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("status") in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: :heartbeat\n\n"
                await asyncio.sleep(10)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/sync_data")
def sync_data(since: str = "", user: dict = Depends(get_current_user_optional)):
    return {"status": "ok", "data": store.list_done_since(since or None, user_id=user["id"])}


@app.post("/ack_sync")
async def ack_sync(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    request_ids = body.get("request_ids", [])
    return {"status": "ok", "acked": store.ack_sync(request_ids)}


@app.get("/recent")
def recent(limit: int = 10, user: dict = Depends(get_current_user_optional)):
    logger.info(f"📜 Fetching recent records (limit={limit}) for user: {user['username']}")
    conn = store._connect()
    try:
        query = "SELECT * FROM server_sleep_jobs WHERE status='done' AND user_id=? ORDER BY date DESC, updated_at DESC LIMIT ?"
        rows = conn.execute(query, (user["id"], int(limit))).fetchall()
        # 必须调用 store._row_to_dict 处理，否则 _public_job 找不到 sleep_data 字段
        return {"status": "ok", "data": [_public_job(store._row_to_dict(row)) for row in rows]}
    finally:
        conn.close()


@app.post("/reflection")
async def reflection(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    text = body.get("text", "")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    if not store.save_reflection(date, text, user_id=user["id"]):
        logger.warning(f"⚠️ Failed to save morning diary for {user['username']} on {date}")
        raise HTTPException(status_code=404, detail="date not found")
    logger.info(f"📝 Morning diary saved for {user['username']} on {date}")
    return {"status": "ok"}


@app.post("/evening_diary")
async def save_evening_diary(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    text = body.get("text", "")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    if not store.save_evening_diary(date, text, user_id=user["id"]):
        logger.warning(f"⚠️ Failed to save evening diary for {user['username']} on {date}")
        raise HTTPException(status_code=404, detail="date not found")
    logger.info(f"🌙 Evening diary saved for {user['username']} on {date}")
    return {"status": "ok"}


@app.post("/generate_report")
async def generate_report(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    logger.info(f"📄 Manual report generation requested for {user['username']} on {date}")
    
    # 查找当天的任务（如果有）
    job = store.get_job_by_date(date, user_id=user["id"])
    image_path = job.get("image_path") if job else None
    request_id = job.get("request_id") if job else uuid.uuid4().hex
    
    if not job:
        # 如果没有任务，创建一个占位任务
        store.create_job(request_id, "", user_id=user["id"], date=date)

    # 启动后台任务进行完整分析
    _run_analysis(request_id, image_path, user_id=user["id"])
    
    # 等待分析完成（简化处理：轮询数据库直到状态为 done）
    import time
    for _ in range(30): # 最多等待 30 秒
        time.sleep(1)
        updated_job = store.get_job(request_id, user_id=user["id"])
        if updated_job and updated_job.get("status") == "done":
            return {"status": "ok", "result": _public_job(updated_job)}
        if updated_job and updated_job.get("status") == "error":
            raise HTTPException(status_code=500, detail=updated_job.get("error", "Unknown analysis error"))
            
    return {"status": "ok", "msg": "Report generation started in background", "request_id": request_id}


if __name__ == "__main__":
    # 直接运行时的本地启动逻辑
    port = int(os.getenv("SLEEP_SERVER_PORT", 8000))
    print(f"🚀 MyTimeLogger Server 启动中...")
    print(f"🔗 访问地址: http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
