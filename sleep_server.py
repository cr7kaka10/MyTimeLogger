# -*- coding: utf-8 -*-
"""
睡眠数据 HTTP 接收服务 (sleep_server.py)
========================================
轻量级 HTTP 服务器，接收手机端 Hamibot/AutoX.js 通过无障碍服务
读取的华为运动健康睡眠数据（JSON），保存到本地文件供 SleepStatisticsWindow 展示。

端点:
  POST /sleep  — 接收睡眠数据 JSON 并保存
  GET  /ping   — 健康检查

启动方式:
  由 MyTimeLogger 主程序在后台线程中自动启动。
"""

import json
import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone

from utils import resource_path

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8))

# 数据存储目录
SLEEP_DATA_DIR = resource_path(
    os.path.join("document", "skills", "time-management", "huawei_health_data")
)


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
        if self.path != "/sleep":
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Not Found. Use POST /sleep"}).encode())
            return

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


class SleepServer:
    """睡眠数据接收服务管理器"""

    def __init__(self, port=5055):
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        """在后台线程启动 HTTP 服务"""
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), SleepDataHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            logger.info(f"🌙 睡眠数据接收服务已启动 -> http://0.0.0.0:{self.port}")
            logger.info(f"   POST /sleep  — 接收睡眠数据")
            logger.info(f"   GET  /ping   — 健康检查")
        except OSError as e:
            logger.error(f"睡眠数据服务启动失败 (端口 {self.port} 被占用?): {e}")

    def stop(self):
        """停止服务"""
        if self.server:
            self.server.shutdown()
            logger.info("睡眠数据接收服务已停止。")
