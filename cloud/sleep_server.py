# -*- coding: utf-8 -*-
import io
import json
import os
import logging
import shutil
import threading
import time
import queue
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
import markdown

from PyQt6.QtCore import QObject, pyqtSignal

from app.utils.utils import resource_path

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

# 数据存储目录
SLEEP_DATA_DIR = resource_path(
    os.path.join("skills", "time-management", "huawei_health_data")
)
ATTACHMENTS_DIR = resource_path("attachments")

class MessageBroker:
    """消息代理：用于将 GUI 的进度推送到 HTTP SSE 客户端"""
    def __init__(self):
        self.queues = {} # {session_id: Queue}
        self.lock = threading.Lock()
        self.last_results = {} # 记录每个会话的最新完整结果

    def get_queue(self, session_id):
        with self.lock:
            if session_id not in self.queues:
                self.queues[session_id] = queue.Queue(maxsize=20)
            return self.queues[session_id]

    def push(self, session_id, data):
        """向指定会话推送数据"""
        with self.lock:
            # 核心改进：后端预渲染 Markdown
            if isinstance(data, dict) and data.get("status") == "done":
                res = data.get("result", {})
                raw = res.get("analysis_report") or res.get("official_interpretation") or ""
                if raw:
                    res["analysis_html"] = markdown.markdown(raw, extensions=['fenced_code', 'tables'])
                self.last_results[session_id] = data
            if session_id in self.queues:
                try:
                    self.queues[session_id].put_nowait(data)
                except queue.Full:
                    pass

    def get_last_result(self, session_id):
        with self.lock:
            return self.last_results.get(session_id)

    def cleanup(self, session_id):
        # 延迟清理：防止手机端网络波动导致的消息丢失
        def _later():
            time.sleep(300) # 延长到5分钟
            with self.lock:
                if session_id in self.queues:
                    del self.queues[session_id]
        threading.Thread(target=_later, daemon=True).start()

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
        name, filename = "", ""
        for line in header_text.split("\r\n"):
            if "Content-Disposition" in line:
                for token in line.split(";"):
                    token = token.strip()
                    if token.startswith("name="): name = token.split("=", 1)[1].strip('"')
                    elif token.startswith("filename="): filename = token.split("=", 1)[1].strip('"')
        if name:
            if filename:
                result[name] = (filename, file_data)
            else:
                result[name] = file_data.decode("utf-8", errors="replace").strip()
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
        elif self.path.startswith("/get_latest_result"):
            import urllib.parse
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            session_id = qs.get("id", ["default"])[0]
            result = broker.get_last_result(session_id)
            # 如果查询的是旧报告，也确保有预渲染内容
            if result and result.get("status") == "done":
                res = result.get("result", {})
                if "analysis_html" not in res:
                    raw = res.get("analysis_report") or res.get("official_interpretation") or ""
                    res["analysis_html"] = markdown.markdown(raw, extensions=['fenced_code', 'tables'])
            self._set_headers(200)
            self.wfile.write(json.dumps(result or {"status": "none"}).encode())
        elif self.path.startswith("/list_recent_reports"):
            # 获取最近 10 条睡眠记录
            from app.models.database import StudyLogger
            db = StudyLogger()
            try:
                conn = db._get_connection()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT date, sleep_score FROM huawei_sleep_data ORDER BY date DESC LIMIT 10")
                rows = cursor.fetchall()
                data = [{"date": r["date"], "score": r["sleep_score"]} for r in rows]
                conn.close()
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "ok", "data": data}).encode())
            except Exception as e:
                self._set_headers(500)
                self.wfile.write(json.dumps({"status": "error", "msg": str(e)}).encode())
        elif self.path.startswith("/get_report"):
            import urllib.parse
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            date_str = qs.get("date", [None])[0]
            from app.models.database import StudyLogger
            db = StudyLogger()
            try:
                conn = db._get_connection()
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM huawei_sleep_data WHERE date = ?", (date_str,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    res = dict(row)
                    # 对历史记录也进行后端渲染
                    raw = res.get("analysis_report") or res.get("official_interpretation") or ""
                    if raw:
                        res["analysis_html"] = markdown.markdown(raw, extensions=['fenced_code', 'tables'])
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"status": "done", "result": res}).encode())
                else:
                    self._set_headers(404)
            except Exception as e:
                self._set_headers(500)
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
                
                /* Markdown 渲染样式 */
                #res-advice h1, #res-advice h2 { font-size: 16px; color: var(--accent); margin-top: 15px; margin-bottom: 8px; border-left: 3px solid var(--accent); padding-left: 8px; }
                #res-advice p { margin: 8px 0; line-height: 1.6; }
                #res-advice ul, #res-advice ol { padding-left: 20px; margin: 8px 0; }
                #res-advice li { margin-bottom: 5px; }
                #res-advice strong { color: #FCD34D; }
                #res-advice blockquote { border-left: 4px solid #334155; margin: 10px 0; padding-left: 12px; color: var(--dim); font-style: italic; }
                #res-advice code { background: rgba(255,255,255,0.1); padding: 2px 5px; border-radius: 4px; font-family: monospace; font-size: 12px; }
                .container { width: 100%; max-width: 450px; padding: 10px; }
                .card { background: var(--card); border-radius: 32px; padding: 24px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); border: 1px solid rgba(255,255,255,0.05); overflow: hidden; }
                
                #dateHeader { font-size: 14px; font-weight: 700; color: var(--accent); letter-spacing: 1px; margin-bottom: 15px; display: none; text-align: center; background: rgba(16, 185, 129, 0.1); padding: 6px 12px; border-radius: 20px; display: inline-block; width: auto; }
                
                .score-circle { width: 120px; height: 120px; border: 8px solid #1E293B; border-radius: 50%; margin: 10px auto 25px; display: none; flex-direction: column; align-items: center; justify-content: center; transition: all 0.5s ease; }
                .score-val-big { font-size: 42px; font-weight: 900; line-height: 1; }
                .score-label-big { font-size: 11px; color: var(--dim); margin-top: 4px; font-weight: 600; }

                h1 { font-size: 22px; margin: 0 0 8px; font-weight: 800; }
                .desc { color: var(--dim); font-size: 13px; margin-bottom: 24px; line-height: 1.5; }
                
                .upload-btn { background: var(--primary); color: white; border: none; width: 100%; padding: 16px; border-radius: 18px; font-size: 16px; font-weight: 700; cursor: pointer; transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 10px; box-shadow: 0 10px 15px -3px rgba(79, 70, 229, 0.4); }
                .upload-btn:active { transform: scale(0.97); }
                
                .status-area { margin-top: 24px; display: none; text-align: center; }
                .progress-text { font-size: 14px; color: var(--accent); margin-bottom: 20px; font-weight: 500; min-height: 21px; }
                
                .result-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; margin-top: 15px; }
                .metric { background: rgba(255,255,255,0.02); padding: 12px 8px; border-radius: 16px; text-align: center; border: 1px solid rgba(255,255,255,0.03); }
                .m-val { display: block; font-size: 16px; font-weight: 800; color: #F8FAFC; }
                .m-lab { display: block; font-size: 10px; color: var(--dim); margin-top: 4px; white-space: nowrap; }
                
                .full-metric { grid-column: span 3; text-align: left; background: rgba(255, 255, 255, 0.03); padding: 16px; margin-top: 10px; }
                
                .reflection-area { margin-top: 20px; display: none; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 20px; }
                textarea { width: 100%; background: #0F172A; border: 1px solid #334155; border-radius: 16px; padding: 15px; color: white; font-size: 14px; resize: none; margin-bottom: 12px; }
                .submit-btn { background: var(--accent); color: white; border: none; width: 100%; padding: 14px; border-radius: 14px; font-weight: 700; cursor: pointer; }
                .history-btn { margin-top: 15px; background: transparent; color: var(--dim); border: 1px solid rgba(255,255,255,0.1); width: 100%; padding: 14px; border-radius: 18px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
                .history-btn:active { background: rgba(255,255,255,0.05); }
                
                .history-list { display: none; margin-top: 20px; }
                .history-item { background: rgba(255,255,255,0.03); padding: 16px; border-radius: 16px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.02); }
                .h-date { font-weight: 700; color: var(--text); }
                .h-score { font-size: 12px; color: var(--accent); background: rgba(16, 185, 129, 0.1); padding: 4px 10px; border-radius: 10px; }
                .back-link { color: var(--dim); font-size: 13px; margin-bottom: 15px; display: inline-block; cursor: pointer; padding: 5px 0; }
                
                #msg { font-size: 11px; color: var(--dim); margin-top: 30px; text-align: center; opacity: 0.6; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card" id="mainCard">
                    <div id="navBack" style="display:none" class="back-link" onclick="goHome()">⬅️ 返回主页</div>
                    <div id="dateHeader" style="display:none">2026-05-13</div>
                    
                    <div class="score-circle" id="scoreCircle">
                        <span class="score-val-big" id="res-score-big">--</span>
                        <span class="score-label-big">睡眠得分</span>
                    </div>

                    <div id="welcomeHeader">
                        <h1>🌙 睡眠深度分析</h1>
                        <p class="desc">上传华为健康截图，AI 将为您解析 10 大核心指标并提供专业复盘建议。</p>
                        <button class="upload-btn" id="upBtn" onclick="document.getElementById('file-input').click()">
                            <span>🚀 上传截图分析</span>
                        </button>
                        <input id="file-input" type="file" accept="image/*" style="display:none" onchange="handleUpload(this)">
                        <button class="history-btn" id="histBtn" onclick="showHistory()">🕒 往期记录查阅</button>
                    </div>

                    <div id="historyList" class="history-list">
                        <div style="font-size:16px; font-weight:800; margin-bottom:15px">🕒 最近 10 天记录</div>
                        <div id="historyContainer"></div>
                    </div>
 
                    <div class="status-area" id="statusArea">
                        <div class="pulse" id="pulse"></div>
                        <div class="progress-text" id="progText">等待上传...</div>
                        
                        <div class="result-grid" id="resultGrid" style="display:none">
                            <div class="metric"><span class="m-val" id="res-cycles">--</span><span class="m-lab">睡眠周期</span></div>
                            <div class="metric"><span class="m-val" id="res-deep">--</span><span class="m-lab">深睡时长</span></div>
                            <div class="metric"><span class="m-val" id="res-awake-m">--</span><span class="m-lab">清醒时长</span></div>
                            
                            <div class="metric"><span class="m-val" id="res-awake-c">--</span><span class="m-lab">清醒次数</span></div>
                            <div class="metric"><span class="m-val" id="res-asleep">--</span><span class="m-lab">入睡用时</span></div>
                            <div class="metric"><span class="m-val" id="res-wakeup">--</span><span class="m-lab">起床用时</span></div>
                            
                            <div class="metric full-metric">
                                <span class="m-lab" style="margin-bottom:8px; font-weight:700; color:var(--accent)">💡 AI 深度解读建议</span>
                                <span id="res-advice" style="font-size:13px; line-height:1.6; color:#E2E8F0"></span>
                            </div>
                        </div>
 
                        <div class="reflection-area" id="reflArea">
                            <textarea id="reflText" rows="3" placeholder="昨晚睡得怎么样？简单记录下感受..."></textarea>
                            <button class="submit-btn" id="subReflBtn" onclick="submitReflection()">✅ 提交复盘并存入库</button>
                        </div>
                    </div>
                </div>
                <div id="msg">连接已就绪</div>
            </div>
 
            <script>
                let sessionId = localStorage.getItem('sleep_session_id');
                if (!sessionId) {
                    sessionId = 'sess_' + Math.random().toString(36).substr(2, 9);
                    localStorage.setItem('sleep_session_id', sessionId);
                }
                
                let currentTargetDate = '';
                let es = null;
 
                function initSSE() {
                    if (es) es.close();
                    es = new EventSource('/events?id=' + sessionId);
                    es.onopen = () => {
                        document.getElementById('msg').innerText = '✅ 系统已就绪 | ID: ' + sessionId;
                        checkLatestResult();
                    };
                    es.onmessage = (e) => {
                        if (e.data === ':heartbeat') return;
                        const data = JSON.parse(e.data);
                        if (data.status === 'progress') {
                            document.getElementById('progText').innerText = data.msg;
                        } else if (data.status === 'done') {
                            showResults(data.result);
                        } else if (data.status === 'error') {
                            document.getElementById('progText').innerText = '❌ ' + data.msg;
                            document.getElementById('pulse').style.display = 'none';
                        }
                    };
                    es.onerror = () => {
                        document.getElementById('msg').innerText = '⚠️ 连接波动，正在自动找回...';
                        setTimeout(initSSE, 2000);
                    };
                }
 
                function checkLatestResult() {
                    if (document.getElementById('resultGrid').style.display === 'grid') return;
                    fetch('/get_latest_result?id=' + sessionId)
                    .then(res => res.json())
                    .then(data => {
                        if (data && data.status === 'done') showResults(data.result);
                    }).catch(e => {});
                }
 
                initSSE();
 
                function showHistory() {
                    document.getElementById('welcomeHeader').style.display = 'none';
                    document.getElementById('historyList').style.display = 'block';
                    document.getElementById('navBack').style.display = 'inline-block';
                    const container = document.getElementById('historyContainer');
                    container.innerHTML = '<div style="color:var(--dim); text-align:center; padding:20px;">正在加载历史记录...</div>';
                    
                    fetch('/list_recent_reports')
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'ok') {
                            container.innerHTML = '';
                            if (data.data.length === 0) {
                                container.innerHTML = '<div style="color:var(--dim); text-align:center; padding:20px;">暂无记录</div>';
                                return;
                            }
                            data.data.forEach(item => {
                                const div = document.createElement('div');
                                div.className = 'history-item';
                                div.onclick = () => loadReport(item.date);
                                div.innerHTML = `
                                    <span class="h-date">${item.date}</span>
                                    <span class="h-score">${item.score} 分</span>
                                `;
                                container.appendChild(div);
                            });
                        }
                    });
                }

                function loadReport(date) {
                    document.getElementById('historyList').style.display = 'none';
                    document.getElementById('statusArea').style.display = 'block';
                    document.getElementById('progText').innerText = '正在加载 ' + date + ' 报告...';
                    document.getElementById('pulse').style.display = 'block';
                    
                    fetch('/get_report?date=' + date)
                    .then(res => res.json())
                    .then(data => {
                        if (data && data.status === 'done') {
                            showResults(data.result);
                            document.getElementById('reflText').value = data.result.sleep_reflection || '';
                        }
                    });
                }

                function goHome() {
                    location.reload();
                }

                function handleUpload(input) {
                    const file = input.files[0];
                    if (!file) return;
                    document.getElementById('upBtn').style.display = 'none';
                    document.getElementById('welcomeHeader').style.display = 'none';
                    document.getElementById('statusArea').style.display = 'block';
                    document.getElementById('navBack').style.display = 'inline-block';
                    document.getElementById('progText').innerText = '正在上传数据至 PC 端...';
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('session_id', sessionId);
                    fetch('/upload?session_id=' + sessionId, { method: 'POST', body: formData })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'ok') document.getElementById('progText').innerText = '🚀 上传成功，AI 解析中...';
                    }).catch(err => { alert('上传出错'); resetUI(); });
                }
 
                function showResults(res) {
                    if (document.getElementById('resultGrid').style.display === 'grid') return;
                    
                    document.getElementById('welcomeHeader').style.display = 'none';
                    document.getElementById('historyList').style.display = 'none';
                    document.getElementById('navBack').style.display = 'inline-block';
                    document.getElementById('pulse').style.display = 'none';
                    document.getElementById('progText').innerText = '✨ 复盘分析已完成';
                    document.getElementById('progText').style.color = '#10B981';
                    
                    const dateH = document.getElementById('dateHeader');
                    dateH.innerText = res.date || '--';
                    dateH.style.display = 'inline-block';
                    
                    const score = parseInt(res.sleep_score) || 0;
                    const circle = document.getElementById('scoreCircle');
                    circle.style.display = 'flex';
                    document.getElementById('res-score-big').innerText = score;
                    
                    if (score >= 85) circle.style.borderColor = '#10B981';
                    else if (score >= 70) circle.style.borderColor = '#3B82F6';
                    else circle.style.borderColor = '#EF4444';
 
                    document.getElementById('resultGrid').style.display = 'grid';
                    document.getElementById('reflArea').style.display = 'block';
                    
                    document.getElementById('res-cycles').innerText = (res.sleep_cycles || '--');
                    document.getElementById('res-deep').innerText = (res.deep_sleep_min || '--') + 'm';
                    document.getElementById('res-awake-m').innerText = (res.awake_min || '0') + 'm';
                    document.getElementById('res-awake-c').innerText = (res.awake_count || '0') + '次';
                    document.getElementById('res-asleep').innerText = (res.fall_asleep_min || '--') + 'm';
                    document.getElementById('res-wakeup').innerText = (res.wake_up_min || '--') + 'm';
                    
                    // 直接使用后端预渲染好的 HTML，不再依赖手机端引擎
                    document.getElementById('res-advice').innerHTML = res.analysis_html || '解析成功，建议在 PC 端查看完整报告。';
                    
                    currentTargetDate = res.date;
                    if (window.navigator.vibrate) window.navigator.vibrate([200, 100, 200, 100, 400]); 
                }
 
                function submitReflection() {
                    const text = document.getElementById('reflText').value.trim();
                    if (!text) return alert('请输入评价内容');
                    const btn = document.getElementById('subReflBtn');
                    btn.innerText = '正在同步至 PC...';
                    btn.disabled = true;
                    fetch('/submit_evaluation', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ date: currentTargetDate, text: text })
                    })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'ok') {
                            alert('🎉 评价已成功保存并同步！');
                            goHome();
                        } else {
                            alert('提交失败');
                            btn.innerText = '✅ 提交评价并落库';
                            btn.disabled = false;
                        }
                    });
                }

                function resetUI() {
                    document.getElementById('upBtn').style.display = 'flex';
                    document.getElementById('statusArea').style.display = 'none';
                    document.getElementById('pulse').style.display = 'block';
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
                    # 降低超时时间，支持心跳发送
                    data = q.get(timeout=15)
                    msg = f"data: {json.dumps(data)}\n\n"
                    self.wfile.write(msg.encode())
                    self.wfile.flush()
                except queue.Empty:
                    # 发送心跳消息，防止连接被手机浏览器掐断
                    try:
                        self.wfile.write(b"data: :heartbeat\n\n")
                        self.wfile.flush()
                    except:
                        break # 连接已彻底断开
                except (ConnectionAbortedError, ConnectionResetError):
                    break
        except Exception as e:
            logger.info(f"SSE: 连接已安全关闭 {session_id}")
        finally:
            broker.cleanup(session_id)

    def do_POST(self):
        if self.path.startswith("/upload"): self._handle_upload()
        elif self.path.startswith("/submit_evaluation"): self._handle_evaluation()
        elif self.path.startswith("/update_ai_config"): self._handle_ai_config()
        else: self._set_headers(404)

    def _handle_ai_config(self):
        """接收并持久化来自客户端的 AI 配置"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(content_length).decode())
            
            # 更新 .env 文件 (如果存在) 或创建新的
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            env_content = []
            
            # 我们主要同步 vision 和 text 相关配置
            mapping = {
                "vision_base_url": "VISION_BASE_URL",
                "vision_api_key":  "VISION_API_KEY",
                "vision_model":    "VISION_MODEL",
                "text_base_url":   "TEXT_BASE_URL",
                "text_api_key":    "TEXT_API_KEY",
                "text_model":      "TEXT_MODEL"
            }
            
            # 读取现有内容以便保留非 AI 相关的配置
            existing_env = {}
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if "=" in line and not line.startswith("#"):
                            k, v = line.strip().split("=", 1)
                            existing_env[k] = v
            
            # 更新配置
            for cfg_key, env_key in mapping.items():
                if cfg_key in data:
                    existing_env[env_key] = data[cfg_key]
            
            # 写回文件
            with open(env_path, "w", encoding="utf-8") as f:
                for k, v in existing_env.items():
                    f.write(f"{k}={v}\n")
            
            logger.info("✅ 云端 AI 配置已同步并持久化。")
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok", "message": "Cloud config updated"}).encode())
        except Exception as e:
            logger.error(f"同步配置失败: {e}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())

    def _handle_upload(self):
        try:
            from urllib.parse import urlparse, parse_qs
            query = parse_qs(urlparse(self.path).query)
            
            # 优先从 URL 参数中提取 session_id，这是最可靠的
            session_id = query.get("session_id", [None])[0]
            
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            files = _parse_multipart(self.headers, body)
            
            # 如果 URL 没带，再看正文里有没有
            if not session_id:
                session_id = files.get("session_id", "default")

            if "file" not in files or not isinstance(files["file"], tuple):
                self._set_headers(400); return
            
            orig_filename, file_data = files["file"]
            # 简单清理下文件名，保留日期信息
            clean_name = "".join(c for c in orig_filename if c.isalnum() or c in ".-_")
            temp_filename = f"sleep_pending_{int(time.time())}_{clean_name}"
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
            
            from app.models.database import StudyLogger
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
            # 升级为多线程服务器并重写错误处理逻辑
            class SilentThreadingHTTPServer(ThreadingHTTPServer):
                def handle_error(self, request, client_address):
                    # 屏蔽常见的连接重置/中止报错 (WinError 10053/10054)
                    import sys
                    exctype, value = sys.exc_info()[:2]
                    if exctype in (ConnectionAbortedError, ConnectionResetError) or (isinstance(value, OSError) and value.errno in (10053, 10054)):
                        return # 静默处理
                    super().handle_error(request, client_address)

            self.server = SilentThreadingHTTPServer(("0.0.0.0", self.port), SleepDataHandler)
            self.server._signal_bridge = self.signal_bridge
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            logger.info(f"🌙 睡眠服务已启动推送模式 -> http://0.0.0.0:{self.port}")
        except Exception as e:
            logger.error(f"服务启动失败: {e}")

    def stop(self):
        if self.server: self.server.shutdown()
