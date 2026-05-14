# -*- coding: utf-8 -*-
"""SQLite buffer store for server sleep analysis jobs."""

import json
import os
import sqlite3
from datetime import datetime

from app.utils.utils import resource_path


DONE_STATUSES = {"done"}


import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from app.utils.utils import resource_path


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{pw_hash}"


def verify_password(password, stored_hash):
    if ":" not in stored_hash:
        return False
    salt, _ = stored_hash.split(":", 1)
    return hash_password(password, salt) == stored_hash


class ServerSleepStore:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.getenv("SERVER_SLEEP_DB_PATH") or resource_path("server_sleep_jobs.db")
        # 兼容性处理：如果旧的数据库文件存在且新的不存在，则重命名
        old_db_path = resource_path("cloud_sleep_jobs.db")
        if not os.path.exists(self.db_path) and os.path.exists(old_db_path):
            try:
                os.rename(old_db_path, self.db_path)
            except:
                pass
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = self._connect()
        try:
            # 迁移：将旧的 cloud_sleep_jobs 表重命名为 server_sleep_jobs
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cloud_sleep_jobs'")
            if cursor.fetchone():
                conn.execute("ALTER TABLE cloud_sleep_jobs RENAME TO server_sleep_jobs")
                conn.commit()
            
            # 用户表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            # 会话表
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )
            # 任务表（增加 user_id）
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS server_sleep_jobs (
                    request_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    date TEXT,
                    status TEXT NOT NULL,
                    image_path TEXT,
                    result_json TEXT,
                    analysis_report TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    sync_count INTEGER DEFAULT 0,
                    acked_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )
            # 检查字段是否存在（用于平滑升级）
            cursor = conn.execute("PRAGMA table_info(server_sleep_jobs)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "user_id" not in columns:
                conn.execute("ALTER TABLE server_sleep_jobs ADD COLUMN user_id INTEGER")

            conn.commit()
        finally:
            conn.close()

    # --- 用户管理 ---

    def create_user(self, username, password):
        conn = self._connect()
        try:
            pw_hash = hash_password(password)
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (username, pw_hash, now_str()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def verify_user(self, username, password):
        conn = self._connect()
        try:
            row = conn.execute("SELECT id, password_hash FROM users WHERE username=?", (username,)).fetchone()
            if row and verify_password(password, row["password_hash"]):
                return row["id"]
            return None
        finally:
            conn.close()

    def create_session(self, user_id):
        token = secrets.token_urlsafe(32)
        ts = now_str()
        # 默认 30 天过期
        expires = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                (token, user_id, ts, expires),
            )
            conn.commit()
            return token
        finally:
            conn.close()

    def get_user_by_session(self, token):
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT u.id, u.username FROM users u
                JOIN sessions s ON u.id = s.user_id
                WHERE s.token = ? AND (s.expires_at IS NULL OR s.expires_at > ?)
                """,
                (token, now_str()),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_default_user_id(self):
        """获取第一个用户，用于 Legacy 模式"""
        conn = self._connect()
        try:
            row = conn.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
            return row["id"] if row else None
        finally:
            conn.close()

    # --- 任务管理 ---

    def create_job(self, request_id, image_path, user_id=None):
        ts = now_str()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO server_sleep_jobs
                (request_id, user_id, date, status, image_path, result_json, analysis_report, error, created_at, updated_at, sync_count, acked_at)
                VALUES (?, ?, NULL, 'queued', ?, NULL, NULL, NULL, ?, ?, 0, NULL)
                """,
                (request_id, user_id, image_path, ts, ts),
            )
            conn.commit()
        finally:
            conn.close()

    def mark_running(self, request_id):
        self._update_status(request_id, "running", error=None)

    def mark_error(self, request_id, error):
        self._update_status(request_id, "error", error=str(error))

    def mark_done(self, request_id, date, result_json, analysis_report):
        if not isinstance(result_json, str):
            result_json = json.dumps(result_json or {}, ensure_ascii=False)
        conn = self._connect()
        try:
            conn.execute(
                """
                UPDATE server_sleep_jobs
                SET status='done', date=?, result_json=?, analysis_report=?, error=NULL, updated_at=?
                WHERE request_id=?
                """,
                (date, result_json, analysis_report or "", now_str(), request_id),
            )
            conn.commit()
        finally:
            conn.close()

    def _update_status(self, request_id, status, error=None):
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE server_sleep_jobs SET status=?, error=?, updated_at=? WHERE request_id=?",
                (status, error, now_str(), request_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_job(self, request_id, user_id=None):
        conn = self._connect()
        try:
            if user_id:
                row = conn.execute("SELECT * FROM server_sleep_jobs WHERE request_id=? AND user_id=?", (request_id, user_id)).fetchone()
            else:
                row = conn.execute("SELECT * FROM server_sleep_jobs WHERE request_id=?", (request_id,)).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_done_since(self, since=None, user_id=None):
        conn = self._connect()
        try:
            query = "SELECT * FROM server_sleep_jobs WHERE status='done'"
            params = []
            if since:
                query += " AND updated_at > ?"
                params.append(since)
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY updated_at ASC"
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_sync_item(row) for row in rows]
        finally:
            conn.close()

    def ack_sync(self, request_ids):
        if not request_ids:
            return 0
        ts = now_str()
        conn = self._connect()
        try:
            count = 0
            for request_id in request_ids:
                cur = conn.execute(
                    """
                    UPDATE server_sleep_jobs
                    SET sync_count=COALESCE(sync_count, 0) + 1, acked_at=?, updated_at=updated_at
                    WHERE request_id=?
                    """,
                    (ts, request_id),
                )
                count += cur.rowcount
            conn.commit()
            return count
        finally:
            conn.close()

    def list_recent(self, limit=10, user_id=None):
        conn = self._connect()
        try:
            query = "SELECT * FROM server_sleep_jobs WHERE status='done'"
            params = []
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY date DESC, updated_at DESC LIMIT ?"
            params.append(int(limit))
            rows = conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_sync_item(row) for row in rows]
        finally:
            conn.close()

    def save_reflection(self, date, reflection, user_id=None):
        conn = self._connect()
        try:
            query = "SELECT * FROM server_sleep_jobs WHERE status='done' AND date=?"
            params = [date]
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            query += " ORDER BY updated_at DESC LIMIT 1"
            row = conn.execute(query, tuple(params)).fetchone()
            if not row:
                return False
            data = json.loads(row["result_json"] or "{}")
            data["sleep_reflection"] = reflection
            conn.execute(
                """
                UPDATE server_sleep_jobs
                SET result_json=?, updated_at=?
                WHERE request_id=?
                """,
                (json.dumps(data, ensure_ascii=False), now_str(), row["request_id"]),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @staticmethod
    def _row_to_dict(row):
        data = dict(row)
        if data.get("result_json"):
            try:
                data["sleep_data"] = json.loads(data["result_json"])
            except Exception:
                data["sleep_data"] = {}
        else:
            data["sleep_data"] = {}
        return data

    def _row_to_sync_item(self, row):
        data = self._row_to_dict(row)
        return {
            "request_id": data["request_id"],
            "date": data["date"],
            "updated_at": data["updated_at"],
            "sleep_data": data["sleep_data"],
            "analysis_report": data.get("analysis_report") or "",
        }
