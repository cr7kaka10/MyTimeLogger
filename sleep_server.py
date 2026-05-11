# -*- coding: utf-8 -*-
"""
睡眠数据 HTTP 接收服务 (sleep_server.py)
========================================
轻量级 HTTP 服务器，接收手机端 Hamibot/AutoX.js 上传的数据。

端点:
  POST /sleep   — 接收睡眠数据 JSON 并保存
  POST /upload  — 接收睡眠截图图片 (multipart/form-data)
  GET  /ping    — 健康检查

启动方式:
  由 MyTimeLogger 主程序在后台线程中自动启动。
"""

import io
import json
import os
import logging
import shutil
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

from PyQt6.QtCore import QObject, pyqtSignal, QMetaObject, Qt, Q_ARG

from utils import resource_path

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

# 数据存储目录
SLEEP_DATA_DIR = resource_path(
    os.path.join("document", "skills", "time-management", "huawei_health_data")
)

# 图片备份目录 (项目根目录)
ATTACHMENTS_DIR = resource_path("attachments")


def _parse_multipart(headers, body_bytes):
    """
    用标准库解析 multipart/form-data，返回 {field_name: (filename, data_bytes)} 字典。
    仅处理文件字段。
    """
    content_type = headers.get("Content-Type", "")
    if "boundary=" not in content_type:
        return {}

    boundary = content_type.split("boundary=")[-1].strip()
    # 有些客户端会带引号
    boundary = boundary.strip('"')

    parts = body_bytes.split(f"--{boundary}".encode())
    result = {}
    for part in parts:
        if not part or part.strip() == b"--" or part.strip() == b"":
            continue
        # 分割 header 和 body (用 \r\n\r\n)
        sep = b"\r\n\r\n"
        if sep not in part:
            continue
        header_section, file_data = part.split(sep, 1)
        # 去掉尾部 \r\n
        if file_data.endswith(b"\r\n"):
            file_data = file_data[:-2]

        header_text = header_section.decode("utf-8", errors="replace")
        # 解析 Content-Disposition
        if "filename=" not in header_text:
            continue
        # 提取 name 和 filename
        name = ""
        filename = ""
        for line in header_text.split("\r\n"):
            if "Content-Disposition" in line:
                for token in line.split(";"):
                    token = token.strip()
                    if token.startswith("name="):
                        name = token.split("=", 1)[1].strip('"')
                    elif token.startswith("filename="):
                        filename = token.split("=", 1)[1].strip('"')
        if name and filename:
            result[name] = (filename, file_data)
    return result


class SleepDataHandler(BaseHTTPRequestHandler):
    """处理手机端发来的睡眠数据请求"""

    def log_message(self, format, *args):
        """重定向 HTTP 日志到 logging"""
        logger.info(f"SleepServer: {format % args}")

    def _set_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        """CORS 预检"""
        self._set_headers(200)

    def do_GET(self):
        if self.path == "/ping":
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok", "service": "MyTimeLogger Sleep Server"}).encode())
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found"}).encode())

    def do_POST(self):
        if self.path == "/sleep":
            self._handle_sleep_json()
        elif self.path == "/upload":
            self._handle_upload()
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found. Use POST /sleep or /upload"}).encode())

    # ── POST /sleep (JSON 数据) ──
    def _handle_sleep_json(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": f"Invalid JSON: {e}"}).encode())
            return

        # 获取日期：优先使用数据中的 date 字段，否则用当前日期
        date_str = data.get("date", datetime.now(CST).strftime("%Y-%m-%d"))

        # 添加接收时间戳
        data["received_at"] = datetime.now(CST).isoformat()

        # 确保目录存在
        os.makedirs(SLEEP_DATA_DIR, exist_ok=True)

        # 保存文件
        filename = f"sleep_{date_str}.json"
        filepath = os.path.join(SLEEP_DATA_DIR, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"睡眠数据已保存: {filepath}")
            self._set_headers(200)
            self.wfile.write(json.dumps({
                "status": "ok",
                "message": f"Data saved to {filename}",
                "date": date_str
            }).encode())
        except Exception as e:
            logger.error(f"保存睡眠数据失败: {e}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    # ── POST /upload (图片上传) ──
    def _handle_upload(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Empty request body"}).encode())
                return
            if content_length > 20 * 1024 * 1024:  # 20MB 上限
                self._set_headers(413)
                self.wfile.write(json.dumps({"error": "File too large (max 20MB)"}).encode())
                return

            body = self.rfile.read(content_length)

            # 解析 multipart
            files = _parse_multipart(self.headers, body)
            if "file" not in files:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Missing 'file' field. Use multipart/form-data with field name 'file'."}).encode())
                return

            orig_filename, file_data = files["file"]
            if not file_data:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Empty file data"}).encode())
                return

            # 提取扩展名
            ext = os.path.splitext(orig_filename)[1].lower() if "." in orig_filename else ".png"
            if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
                ext = ".png"

            # 临时文件名 (AI 分析完后会按识别日期重命名)
            timestamp = datetime.now(CST).strftime("%Y%m%d_%H%M%S")
            temp_filename = f"sleep_pending_{timestamp}{ext}"

            # 确保 attachments 目录存在
            os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

            save_path = os.path.join(ATTACHMENTS_DIR, temp_filename)
            with open(save_path, "wb") as f:
                f.write(file_data)

            logger.info(f"📸 截图已接收并保存: {save_path} ({len(file_data)} bytes)")

            # 通知 UI (线程安全)
            srv = self.server
            if hasattr(srv, "_signal_bridge") and srv._signal_bridge:
                srv._signal_bridge.emit_image_received(save_path)

            self._set_headers(200)
            self.wfile.write(json.dumps({
                "status": "ok",
                "message": f"Image saved as {temp_filename}, AI analysis will start automatically.",
                "path": save_path
            }).encode())

        except Exception as e:
            logger.error(f"图片上传处理失败: {e}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())


class _SignalBridge(QObject):
    """
    Qt 信号桥：将 HTTP 线程中的事件安全地转发到 Qt 主线程。
    """
    image_received = pyqtSignal(str)  # 参数: 图片临时路径

    def emit_image_received(self, path):
        """线程安全地发射信号"""
        self.image_received.emit(path)


class SleepServer:
    """睡眠数据接收服务管理器"""

    def __init__(self, port=5055):
        self.port = port
        self.server = None
        self.thread = None
        self.signal_bridge = _SignalBridge()

    def start(self):
        """在后台线程启动 HTTP 服务"""
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), SleepDataHandler)
            # 将信号桥挂到 server 上，供 handler 访问
            self.server._signal_bridge = self.signal_bridge
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"🌙 睡眠数据接收服务已启动 -> http://0.0.0.0:{self.port}")
            logger.info(f"   POST /sleep   — 接收睡眠 JSON 数据")
            logger.info(f"   POST /upload  — 接收睡眠截图图片")
            logger.info(f"   GET  /ping    — 健康检查")
        except OSError as e:
            logger.error(f"睡眠数据服务启动失败 (端口 {self.port} 被占用?): {e}")

    def stop(self):
        """停止服务"""
        if self.server:
            self.server.shutdown()
            logger.info("睡眠数据接收服务已停止。")
