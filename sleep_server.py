# -*- coding: utf-8 -*-
import io
import json
import os
import logging
import shutil
import threading
import time
import queue
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone

from PyQt6.QtCore import QObject, pyqtSignal

from utils import resource_path

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

# 数据存储目录
SLEEP_DATA_DIR = resource_path(
    os.path.join("document", "skills", "time-management", "huawei_health_data")
)
ATTACHMENTS_DIR = resource_path("attachments")

class MessageBroker:
    """消息代理：用于将 GUI 的进度推送到 HTTP SSE 客户端"""
    def __init__(self):
        self.queues = {} # {session_id: Queue}
        self.lock = threading.Lock()

    def get_queue(self, session_id):
        with self.lock:
            if session_id not in self.queues:
                self.queues[session_id] = queue.Queue(maxsize=20)
            return self.queues[session_id]

    def push(self, session_id, data):
        """向指定会话推送数据"""
        with self.lock:
            if session_id in self.queues:
                try:
                    self.queues[session_id].put_nowait(data)
                except queue.Full:
                    pass

    def push_global(self, data):
        """向所有活跃会话推送（兜底方案）"""
        with self.lock:
            for q in self.queues.values():
                try: q.put_nowait(data)
                except: pass

    def cleanup(self, session_id):
        with self.lock:
            if session_id in self.queues:
                del self.queues[session_id]

broker = MessageBroker()

def _parse_multipart(headers, body_bytes):
    content_type = headers.get("Content-Type", "")
    if "boundary=" not in content_type: return {}
    boundary = content_type.split("boundary=")[-1].strip().strip('"')
    parts = body_bytes.split(f"--{boundary}".encode())
    result = {}
    for part in parts:
        if not part or part.strip() in (b"--", b""): continue
        sep = b"\r\n\r\n"
        if sep not in part: continue
        header_section, file_data = part.split(sep, 1)
        if file_data.endswith(b"\r\n"): file_data = file_data[:-2]
        header_text = header_section.decode("utf-8", errors="replace")
        if "filename=" not in header_text: continue
        name, filename = "", ""
        for line in header_text.split("\r\n"):
            if "Content-Disposition" in line:
                for token in line.split(";"):
                    token = token.strip()
                    if token.startswith("name="): name = token.split("=", 1)[1].strip('"')
                    elif token.startswith("filename="): filename = token.split("=", 1)[1].strip('"')
        if name and filename: result[name] = (filename, file_data)
    return result

class SleepDataHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info(f"SleepServer: {format % args}")

    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index.html"):
            self._handle_index()
        elif self.path.startswith("/events"):
            self._handle_sse()
        elif self.path == "/ping":
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok"}).encode())
        else:
            self._set_headers(404)

    def _handle_index(self):
        self._set_headers(200, "text/html; charset=utf-8")
        html = """
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
            <title>MyTimeLogger | 睡眠分析</title>
            <style>
                :root { --bg: #0A0F1E; --card: #161E31; --primary: #4F46E5; --accent: #10B981; --text: #F8FAFC; --dim: #94A3B8; }
                * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; outline: none; }
                body { font-family: 'Inter', -apple-system, sans-serif; background: var(--bg); color: var(--text); margin: 0; padding: 15px; display: flex; justify-content: center; min-height: 100vh; }
                .container { width: 100%; max-width: 450px; padding-top: 20px; }
                .card { background: var(--card); border-radius: 28px; padding: 24px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.05); }
                h1 { font-size: 24px; margin: 0 0 8px; font-weight: 800; }
                .desc { color: var(--dim); font-size: 14px; margin-bottom: 24px; line-height: 1.5; }
                
                .upload-btn { background: var(--primary); color: white; border: none; width: 100%; padding: 18px; border-radius: 18px; font-size: 16px; font-weight: 700; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 10px; }
                .upload-btn:active { transform: scale(0.97); opacity: 0.9; }
                
                .status-area { margin-top: 24px; display: none; text-align: center; }
                .progress-text { font-size: 14px; color: var(--accent); margin-bottom: 12px; font-weight: 500; min-height: 21px; }
                .pulse { width: 60px; height: 60px; background: var(--primary); border-radius: 50%; margin: 0 auto 15px; animation: pulse 1.5s infinite; }
                @keyframes pulse { 0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(79, 70, 229, 0.7); } 70% { transform: scale(1); box-shadow: 0 0 0 15px rgba(79, 70, 229, 0); } 100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(79, 70, 229, 0); } }

                .result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 15px; }
                .metric { background: rgba(255,255,255,0.03); padding: 15px; border-radius: 16px; text-align: center; }
                .m-val { display: block; font-size: 18px; font-weight: 800; color: #60A5FA; }
                .m-lab { display: block; font-size: 11px; color: var(--dim); margin-top: 4px; }
                .full-metric { grid-column: span 2; text-align: left; background: rgba(16, 185, 129, 0.05); border: 1px solid rgba(16, 185, 129, 0.1); }
                
                .reflection-area { margin-top: 20px; display: none; }
                textarea { width: 100%; background: #0F172A; border: 1px solid #334155; border-radius: 16px; padding: 15px; color: white; font-size: 14px; resize: none; margin-bottom: 12px; }
                .submit-btn { background: var(--accent); color: white; border: none; width: 100%; padding: 14px; border-radius: 14px; font-weight: 700; cursor: pointer; }
                
                #msg { font-size: 12px; color: var(--dim); margin-top: 20px; text-align: center; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card">
                    <h1>🌙 睡眠深度分析</h1>
                    <p class="desc">上传华为健康截图，AI 将为您解析 6 大核心指标并提供专业建议。</p>
                    
                    <button class="upload-btn" id="upBtn" onclick="document.getElementById('file-input').click()">
                        <span>🚀 上传截图分析</span>
                    </button>
                    <input id="file-input" type="file" accept="image/*" style="display:none" onchange="handleUpload(this)">

                    <div class="status-area" id="statusArea">
                        <div class="pulse" id="pulse"></div>
                        <div class="progress-text" id="progText">等待上传...</div>
                        
                        <div class="result-grid" id="resultGrid" style="display:none">
                            <div class="metric"><span class="m-val" id="res-score">--</span><span class="m-lab">睡眠评分</span></div>
                            <div class="metric"><span class="m-val" id="res-cycles">--</span><span class="m-lab">睡眠周期</span></div>
                            <div class="metric"><span class="m-val" id="res-deep">--</span><span class="m-lab">深睡时长</span></div>
                            <div class="metric"><span class="m-val" id="res-asleep">--</span><span class="m-lab">入睡用时</span></div>
                            <div class="metric"><span class="m-val" id="res-wakeup">--</span><span class="m-lab">起床用时</span></div>
                            <div class="metric"><span class="m-val" id="res-date">--</span><span class="m-lab">记录日期</span></div>
                            <div class="metric full-metric" style="grid-column: span 2">
                                <span class="m-lab" style="margin-bottom:5px">💡 官方解读与建议</span>
                                <span id="res-advice" style="font-size:13px; line-height:1.5"></span>
                            </div>
                        </div>

                        <div class="reflection-area" id="reflArea">
                            <textarea id="reflText" rows="3" placeholder="填写睡眠自我评价..."></textarea>
                            <button class="submit-btn" onclick="submitReflection()">✅ 提交评价并落库</button>
                        </div>
                    </div>
                </div>
                <div id="msg">连接已就绪</div>
            </div>

            <script>
                const sessionId = 'sess_' + Math.random().toString(36).substr(2, 9);
                let currentTargetDate = '';

                // 建立 SSE 连接
                const evtSource = new EventSource('/events?id=' + sessionId);
                evtSource.onmessage = (e) => {
                    const data = JSON.parse(e.data);
                    const progText = document.getElementById('progText');
                    
                    if (data.status === 'progress') {
                        progText.innerText = data.msg;
                    } else if (data.status === 'done') {
                        showResults(data.result);
                    }
                };

                function handleUpload(input) {
                    const file = input.files[0];
                    if (!file) return;

                    document.getElementById('upBtn').style.display = 'none';
                    document.getElementById('statusArea').style.display = 'block';
                    document.getElementById('progText').innerText = '正在上传文件...';
                    
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('session_id', sessionId);
                    
                    fetch('/upload', { method: 'POST', body: formData })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status !== 'ok') {
                            alert('上传失败: ' + data.error);
                            resetUI();
                        }
                    });
                }

                function showResults(res) {
                    document.getElementById('pulse').style.display = 'none';
                    document.getElementById('progText').innerText = '✅ 分析完成';
                    document.getElementById('resultGrid').style.display = 'grid';
                    document.getElementById('reflArea').style.display = 'block';
                    
                    document.getElementById('res-score').innerText = res.sleep_score || '--';
                    document.getElementById('res-cycles').innerText = res.sleep_cycles + ' 个';
                    document.getElementById('res-deep').innerText = res.deep_sleep_min + ' min';
                    document.getElementById('res-asleep').innerText = res.fall_asleep_min + ' min';
                    document.getElementById('res-wakeup').innerText = res.wake_up_min + ' min';
                    document.getElementById('res-date').innerText = res.date;
                    document.getElementById('res-advice').innerText = res.official_interpretation || '无建议';
                    
                    currentTargetDate = res.date;
                }

                function submitReflection() {
                    const text = document.getElementById('reflText').value.trim();
                    if (!text) return alert('请输入内容');
                    
                    fetch('/submit_evaluation', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ date: currentTargetDate, text: text })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'ok') {
                            alert('评价已存入数据库！');
                            location.reload();
                        }
                    });
                }

                function resetUI() {
                    document.getElementById('upBtn').style.display = 'flex';
                    document.getElementById('statusArea').style.display = 'none';
                }
            </script>
        </body>
        </html>
        """
        self.wfile.write(html.encode())

    def _handle_sse(self):
        """处理 SSE 实时推送"""
        import urllib.parse
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        session_id = qs.get("id", ["default"])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = broker.get_queue(session_id)
        logger.info(f"SSE: 客户端已连接 {session_id}")
        
        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    msg = f"data: {json.dumps(data)}\n\n"
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
        except Exception as e:
            logger.info(f"SSE: 连接中断 {session_id}: {e}")
        finally:
            broker.cleanup(session_id)

    def do_POST(self):
        if self.path == "/upload": self._handle_upload()
        elif self.path == "/submit_evaluation": self._handle_evaluation()
        else: self._set_headers(404)

    def _handle_upload(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            files = _parse_multipart(self.headers, body)
            
            # 解析 session_id
            session_id = "default"
            content_type = self.headers.get("Content-Type", "")
            boundary = content_type.split("boundary=")[-1].strip().strip('"')
            for part in body.split(f"--{boundary}".encode()):
                if b'name="session_id"' in part:
                    session_id = part.split(b"\r\n\r\n")[1].strip().decode()

            if "file" not in files:
                self._set_headers(400); return
            
            orig_filename, file_data = files["file"]
            ext = os.path.splitext(orig_filename)[1].lower() if "." in orig_filename else ".png"
            temp_filename = f"sleep_pending_{int(time.time())}{ext}"
            os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
            save_path = os.path.join(ATTACHMENTS_DIR, temp_filename)
            
            with open(save_path, "wb") as f: f.write(file_data)
            logger.info(f"📸 截图接收: {save_path}")

            # 通知 UI
            srv = self.server
            if hasattr(srv, "_signal_bridge"):
                # 将 session_id 一并传过去，方便回调
                srv._signal_bridge.image_received.emit(save_path, session_id)

            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok", "session_id": session_id}).encode())
        except Exception as e:
            logger.error(f"上传错误: {e}")
            self._set_headers(500)

    def _handle_evaluation(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(content_length).decode())
            date_str = data.get("date")
            text = data.get("text")
            
            from database import StudyLogger
            db = StudyLogger()
            success = db.save_sleep_reflection(date_str, text)
            
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok" if success else "error"}).encode())
        except Exception as e:
            self._set_headers(500)

class _SignalBridge(QObject):
    image_received = pyqtSignal(str, str) # path, session_id

class SleepServer:
    def __init__(self, port=5055):
        self.port = port
        self.server = None
        self.signal_bridge = _SignalBridge()

    def start(self):
        try:
            # 使用 ThreadingHTTPServer 支持并发处理（解决 SSE 阻塞上传的问题）
            self.server = ThreadingHTTPServer(("0.0.0.0", self.port), SleepDataHandler)
            self.server._signal_bridge = self.signal_bridge
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            logger.info(f"🌙 睡眠服务已启动推送模式 -> http://0.0.0.0:{self.port}")
        except Exception as e:
            logger.error(f"服务启动失败: {e}")

    def stop(self):
        if self.server: self.server.shutdown()
