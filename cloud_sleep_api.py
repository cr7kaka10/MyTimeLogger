# -*- coding: utf-8 -*-
"""FastAPI cloud endpoint for sleep screenshot analysis."""

import asyncio
import json
import os
import queue
import shutil
import uuid
from datetime import datetime

import markdown
from fastapi import BackgroundTasks, FastAPI, File, Header, HTTPException, Request, UploadFile, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from cloud_sleep_store import CloudSleepStore
from cloud_runtime_config import ensure_cloud_runtime_config
from sleep_analyzer import SleepAnalyzer
from utils import resource_path


MAX_UPLOAD_BYTES = 15 * 1024 * 1024
ATTACHMENTS_DIR = resource_path("cloud_attachments")

ensure_cloud_runtime_config()

app = FastAPI(title="MyTimeLogger Sleep Cloud API", version="1.0")
store = CloudSleepStore()
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
    result = job.get("sleep_data") or {}
    raw_report = job.get("analysis_report") or ""
    if raw_report:
        result = dict(result)
        result["analysis_report"] = raw_report
        result["analysis_html"] = markdown.markdown(raw_report, extensions=["fenced_code", "tables"])
    return {
        "request_id": job["request_id"],
        "date": job.get("date"),
        "status": job["status"],
        "updated_at": job["updated_at"],
        "error": job.get("error"),
        "result": result,
    }


def _run_analysis(request_id, image_path, user_id):
    store.mark_running(request_id)
    _push_progress(request_id, {"status": "running", "msg": "开始云端睡眠分析..."})

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
        return {"status": "ok", "msg": "Registration successful"}
    raise HTTPException(status_code=400, detail="Username already exists")


@app.post("/auth/login")
async def login(request: Request):
    body = await request.json()
    username = body.get("username")
    password = body.get("password")
    user_id = store.verify_user(username, password)
    if user_id:
        token = store.create_session(user_id)
        return {"status": "ok", "token": token, "username": username}
    raise HTTPException(status_code=401, detail="Invalid username or password")


@app.get("/auth/me")
def get_me(user: dict = Depends(get_current_user)):
    return {"status": "ok", "user": user}


@app.get("/ping")
def ping():
    return {"status": "ok", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!doctype html>
    <html lang="zh-CN">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>MyTimeLogger 睡眠云分析</title>
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
      <style>
        :root{--primary:#6366f1;--primary-hover:#4f46e5;--bg:#0f172a;--card:#1e293b;--text:#f8fafc;--text-muted:#94a3b8}
        body{font-family:'Inter',-apple-system,sans-serif;background:linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);color:var(--text);margin:0;padding:20px;min-height:100vh}
        main{max-width:480px;margin:40px auto}
        .card{background:rgba(30, 41, 59, 0.7);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.1);border-radius:24px;padding:32px;box-shadow:0 20px 25px -5px rgba(0,0,0,0.3)}
        h2{margin:0 0 8px;font-weight:700;background:linear-gradient(to right, #fff, #94a3b8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
        .muted{color:var(--text-muted);font-size:14px;line-height:1.6}
        input{width:100%;box-sizing:border-box;margin-top:16px;padding:14px;border-radius:12px;border:1px solid #334155;background:rgba(15,23,42,0.6);color:#fff;outline:none;transition:border 0.2s}
        input:focus{border-color:var(--primary)}
        button{width:100%;margin-top:16px;padding:14px;border-radius:12px;border:0;background:var(--primary);color:#fff;font-weight:600;cursor:pointer;transition:all 0.2s}
        button:hover{background:var(--primary-hover);transform:translateY(-1px)}
        button.secondary{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1)}
        button.secondary:hover{background:rgba(255,255,255,0.1)}
        #status{margin-top:16px;padding:12px;border-radius:8px;background:rgba(0,0,0,0.2);display:none}
        .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:20px}
        .metric{background:rgba(255,255,255,0.05);padding:16px;border-radius:16px;text-align:center}
        .metric b{font-size:20px;display:block;margin-top:4px;color:var(--primary)}
        .auth-box{display:none}
        .user-info{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;font-size:14px;color:var(--text-muted)}
        .logout{cursor:pointer;color:var(--primary)}
        .analysis-html{margin-top:20px;font-size:14px;border-top:1px solid rgba(255,255,255,0.1);padding-top:20px}
        .analysis-html table{width:100%;border-collapse:collapse;margin:10px 0}
        .analysis-html td, .analysis-html th{border:1px solid rgba(255,255,255,0.1);padding:8px}
      </style>
    </head>
    <body><main>
      <!-- 登录/注册 -->
      <div id="authPanel" class="card">
        <h2 id="authTitle">欢迎回来</h2>
        <p class="muted" id="authDesc">请登录以同步您的睡眠健康数据</p>
        <input id="username" placeholder="用户名" />
        <input id="password" type="password" placeholder="密码" />
        <button onclick="doAuth()" id="authBtn">登录</button>
        <button class="secondary" onclick="toggleAuth()" id="toggleBtn">没有账号？注册</button>
      </div>

      <!-- 主界面 -->
      <div id="mainPanel" class="card" style="display:none">
        <div class="user-info">
          <span>你好，<b id="displayUser">--</b></span>
          <span class="logout" onclick="logout()">退出</span>
        </div>
        <h2>睡眠分析</h2>
        <p class="muted">上传华为健康截图，AI 将为您深度解析</p>
        <input id="file" type="file" accept="image/*" style="display:none" onchange="upload()" />
        <button onclick="document.getElementById('file').click()">选择截图并上传</button>
        <button class="secondary" onclick="recent()">查看最近记录</button>
        <div id="status"></div>
        <div id="result"></div>
      </div>
    </main>
    <script>
      let isLogin = true;
      let token = localStorage.getItem('sleep_token');
      
      async function init() {
        if(token) {
          const r = await fetch('/auth/me', {headers:{'Authorization':`Bearer ${token}`}});
          if(r.ok) {
            const j = await r.json();
            showMain(j.user.username);
            return;
          }
          localStorage.removeItem('sleep_token');
        }
        showAuth();
      }

      function toggleAuth(){
        isLogin = !isLogin;
        authTitle.innerText = isLogin ? '欢迎回来' : '注册账号';
        authDesc.innerText = isLogin ? '请登录以同步您的睡眠健康数据' : '为家人创建一个独立的睡眠分析账号';
        authBtn.innerText = isLogin ? '登录' : '立即注册';
        toggleBtn.innerText = isLogin ? '没有账号？注册' : '已有账号？登录';
      }

      async function doAuth(){
        const u = username.value; const p = password.value;
        if(!u || !p) return alert('请输入用户名和密码');
        const path = isLogin ? '/auth/login' : '/auth/register';
        const r = await fetch(path, {method:'POST', body:JSON.stringify({username:u, password:p})});
        const j = await r.json();
        if(!r.ok) return alert(j.detail || '操作失败');
        if(!isLogin) { alert('注册成功，请登录'); toggleAuth(); return; }
        token = j.token;
        localStorage.setItem('sleep_token', token);
        showMain(u);
      }

      function showMain(user){
        displayUser.innerText = user;
        authPanel.style.display = 'none';
        mainPanel.style.display = 'block';
      }
      function showAuth(){
        authPanel.style.display = 'block';
        mainPanel.style.display = 'none';
      }
      function logout(){
        localStorage.removeItem('sleep_token');
        location.reload();
      }

      async function upload(){
        const f = document.getElementById('file').files[0];
        if(!f) return;
        const fd = new FormData(); fd.append('file', f);
        status.style.display = 'block'; status.innerText = '正在上传...';
        const r = await fetch('/upload', {method:'POST', headers:{'Authorization':`Bearer ${token}`}, body:fd});
        const j = await r.json();
        if(!r.ok){ status.innerText = j.detail || '上传失败'; return; }
        poll(j.request_id);
      }

      async function poll(rid){
        const r = await fetch('/status/'+rid, {headers:{'Authorization':`Bearer ${token}`}});
        const j = await r.json();
        status.innerText = '状态: ' + j.status + (j.msg ? ' - ' + j.msg : '');
        if(j.status === 'done'){ 
          render(j.result || {});
          status.innerText = '分析完成！';
          return; 
        }
        if(j.status === 'error') { status.innerText = '出错: ' + (j.error || '未知错误'); return; }
        setTimeout(()=>poll(rid), 2500);
      }

      async function recent(){
        const r = await fetch('/recent?limit=10', {headers:{'Authorization':`Bearer ${token}`}});
        const j = await r.json();
        result.innerHTML = '<div style="margin-top:20px">' + (j.data || []).map(x=>`
          <div style="padding:12px;border-bottom:1px solid rgba(255,255,255,0.05)">
            <span style="font-weight:600">${x.date}</span> · 
            <span style="color:var(--primary)">${x.sleep_data?.sleep_score || '--'}分</span>
          </div>
        `).join('') + '</div>';
      }

      function render(d){
        result.innerHTML = `
          <div class="grid">
            <div class="metric">评分<b>${d.sleep_score || '--'}</b></div>
            <div class="metric">总睡眠<b>${d.total_sleep_min || '--'} min</b></div>
          </div>
          <div class="analysis-html">${d.analysis_html || '暂无深度建议'}</div>
        `;
      }

      init();
    </script></body></html>
    """


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
    image_path = os.path.join(ATTACHMENTS_DIR, f"{request_id}_{safe_name}")
    with open(image_path, "wb") as out:
        out.write(content)
    store.create_job(request_id, image_path, user_id=user["id"])
    background_tasks.add_task(_run_analysis, request_id, image_path, user_id=user["id"])
    return {"status": "ok", "request_id": request_id}


@app.get("/status/{request_id}")
def status(request_id: str, user: dict = Depends(get_current_user_optional)):
    job = store.get_job(request_id, user_id=user["id"])
    if not job:
        raise HTTPException(status_code=404, detail="request_id not found")
    return _public_job(job)


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
    return {"status": "ok", "data": store.list_recent(limit, user_id=user["id"])}


@app.post("/reflection")
async def reflection(request: Request, user: dict = Depends(get_current_user_optional)):
    body = await request.json()
    date = body.get("date")
    text = body.get("text", "")
    if not date:
        raise HTTPException(status_code=400, detail="date is required")
    if not store.save_reflection(date, text, user_id=user["id"]):
        raise HTTPException(status_code=404, detail="date not found")
    return {"status": "ok"}
