# -*- coding: utf-8 -*-
"""
数据库模块 (database.py) - 架构升级版
======================================
封装所有数据持久化逻辑:
- StudyLogger: 底层存储层，支持 SQLite（本地）和 MySQL（远程）双引擎
- 新增 tasks/habits 持久化支持，主键采用 BigInt
"""

import os
import json
import copy
import sqlite3
import logging
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal

from utils import resource_path
from config import DEFAULT_CONFIG

try:
    import pymysql
except ImportError:
    pymysql = None

class StudyLogger:
    """
    学习会话及任务/习惯的数据库读写层。
    """

    def __init__(self, config=None):
        self.config = config if config else DEFAULT_CONFIG
        self.db_type = self.config.get("db_type", "sqlite")
        self.log_path = resource_path("study_log.db")
        self._conn = None

        if self.db_type == "sqlite":
            self._initialize_db()
            self._migrate_from_json()

    def _get_connection(self):
        if self.db_type == "mysql":
            if pymysql is None:
                raise ImportError("未安装 pymysql，请运行 'pip install pymysql'")
            if self._conn:
                try:
                    self._conn.ping(reconnect=True)
                    return self._conn
                except Exception:
                    self._conn = None
            m_cfg = self.config.get("mysql_config", {})
            actual_cfg = {}
            for k, v in m_cfg.items():
                real_key = k.lstrip("/")
                if real_key not in actual_cfg or not k.startswith("//"):
                    actual_cfg[real_key] = v
            self._conn = pymysql.connect(
                host=actual_cfg.get("host", "127.0.0.1"),
                user=actual_cfg.get("user", "root"),
                password=actual_cfg.get("password", ""),
                database=actual_cfg.get("database", "mytimelogger"),
                port=int(actual_cfg.get("port", 3306)),
                charset='utf8mb4'
            )
            return self._conn
        else:
            return sqlite3.connect(self.log_path)

    def _initialize_db(self):
        """同步初始化表结构"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 1. 专注会话表
            if self.db_type == "mysql":
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS study_sessions (
                        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        start_time DATETIME NOT NULL,
                        end_time DATETIME NOT NULL,
                        net_duration_minutes DECIMAL(10,2) NOT NULL,
                        date DATE NOT NULL,
                        day_of_week VARCHAR(20),
                        pause_count INT DEFAULT 0,
                        pause_reasons TEXT,
                        session_summary TEXT,
                        category_id INT DEFAULT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                ''')
                # 2. 任务持久化表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        ticktick_id VARCHAR(64) UNIQUE,
                        title TEXT NOT NULL,
                        priority INT DEFAULT 0,
                        status INT DEFAULT 0,
                        category_id INT DEFAULT NULL,
                        project_name VARCHAR(100),
                        due_date TEXT,
                        raw_json JSON,
                        updated_at DATETIME
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                ''')
                # 3. 习惯持久化表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS habits (
                        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        ticktick_id VARCHAR(64) UNIQUE,
                        title TEXT NOT NULL,
                        category_id INT DEFAULT NULL,
                        raw_json JSON,
                        updated_at DATETIME
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                ''')
            else:
                # SQLite
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS study_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        start_time TIMESTAMP NOT NULL,
                        end_time TIMESTAMP NOT NULL,
                        net_duration_minutes REAL NOT NULL,
                        date TEXT NOT NULL,
                        day_of_week TEXT,
                        pause_count INTEGER DEFAULT 0,
                        pause_reasons TEXT,
                        session_summary TEXT,
                        category_id INTEGER DEFAULT NULL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticktick_id TEXT UNIQUE,
                        title TEXT NOT NULL,
                        priority INTEGER DEFAULT 0,
                        status INTEGER DEFAULT 0,
                        category_id INTEGER DEFAULT NULL,
                        project_name TEXT,
                        due_date TEXT,
                        raw_json TEXT,
                        updated_at TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS habits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticktick_id TEXT UNIQUE,
                        title TEXT NOT NULL,
                        category_id INTEGER DEFAULT NULL,
                        raw_json TEXT,
                        updated_at TIMESTAMP
                    )
                ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"数据库扩展初始化失败: {e}")

    def log_session(self, start_time: datetime, end_time: datetime,
                    net_duration_seconds: int, pause_count: int = 0,
                    pause_reasons: str = "", session_summary: str = "",
                    category_id: int = None):
        if not all([start_time, end_time, net_duration_seconds > 0]):
            return
        date_str = start_time.strftime('%Y-%m-%d')
        day_of_week = start_time.strftime('%A')
        net_duration_minutes = round(net_duration_seconds / 60, 2)

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            start_fmt = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_fmt = end_time.strftime('%Y-%m-%d %H:%M:%S')
            placeholder = "%s" if self.db_type == "mysql" else "?"

            sql = f'''
                INSERT INTO study_sessions 
                (start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary, category_id)
                VALUES ({", ".join([placeholder]*9)})
            '''
            cursor.execute(sql, (
                start_fmt, end_fmt, net_duration_minutes,
                date_str, day_of_week, pause_count,
                pause_reasons, session_summary, category_id
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"记录学习会话失败: {e}")

    def upsert_task(self, task_dict: dict):
        """根据 ticktick_id 更新或插入任务数据"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            tick_id = task_dict.get("id")
            title = task_dict.get("title", "")
            priority = task_dict.get("priority", 0)
            status = task_dict.get("status", 0)
            cat_id = task_dict.get("category_id")
            p_name = task_dict.get("project_name", "")
            due = task_dict.get("due_date", "")
            raw = json.dumps(task_dict)
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            if self.db_type == "mysql":
                sql = '''
                    INSERT INTO tasks (ticktick_id, title, priority, status, category_id, project_name, due_date, raw_json, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE 
                    title=%s, priority=%s, status=%s, category_id=%s, project_name=%s, due_date=%s, raw_json=%s, updated_at=%s
                '''
                cursor.execute(sql, (tick_id, title, priority, status, cat_id, p_name, due, raw, now,
                                    title, priority, status, cat_id, p_name, due, raw, now))
            else:
                sql = '''
                    INSERT INTO tasks (ticktick_id, title, priority, status, category_id, project_name, due_date, raw_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticktick_id) DO UPDATE SET
                    title=excluded.title, priority=excluded.priority, status=excluded.status, 
                    category_id=excluded.category_id, project_name=excluded.project_name, 
                    due_date=excluded.due_date, raw_json=excluded.raw_json, updated_at=excluded.updated_at
                '''
                cursor.execute(sql, (tick_id, title, priority, status, cat_id, p_name, due, raw, now))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"持久化任务失败: {e}")

    def _migrate_from_json(self):
        json_path = resource_path("study_log.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    records = json.load(f)
                if records:
                    conn = sqlite3.connect(self.log_path)
                    cursor = conn.cursor()
                    for r in records:
                        cursor.execute('''
                            INSERT INTO study_sessions 
                            (start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            r.get("start_time"), r.get("end_time"), r.get("net_duration_minutes"),
                            r.get("date"), r.get("day_of_week"), r.get("pause_count"),
                            r.get("pause_reasons"), r.get("session_summary")
                        ))
                    conn.commit()
                    conn.close()
                os.rename(json_path, json_path + ".bak")
            except Exception as e:
                logging.error(f"数据迁移失败: {e}")

    def get_all_sessions(self):
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary, category_id FROM study_sessions ORDER BY start_time ASC")
            rows = cursor.fetchall()
            conn.close()
            return [list(map(str, row)) for row in rows]
        except Exception as e:
            logging.error(f"读取数据库失败: {e}")
            return []

class DatabaseWorker(QObject):
    logged = pyqtSignal()
    stats_ready = pyqtSignal(list, bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.mysql_cfg = copy.deepcopy(config)
        self.mysql_cfg["db_type"] = "mysql"
        self.backup_logger = StudyLogger(self.mysql_cfg)

    def init_db(self):
        try:
            m_cfg = self.config.get("mysql_config", {})
            if any(not k.startswith("//") for k in m_cfg.keys()):
                self.backup_logger._initialize_db()
        except Exception as e:
            logging.error(f"[MySQL] 远程初始化失败: {e}")

    def sync_to_backup(self, data_dict):
        m_cfg = self.config.get("mysql_config", {})
        if any(not k.startswith("//") for k in m_cfg.keys()):
            try:
                self.backup_logger.log_session(**data_dict)
            except Exception as e:
                logging.error(f"[MySQL] 镜像同步过程中断: {e}")

    def fetch_stats(self, open_browser=False):
        try:
            local_cfg = copy.deepcopy(self.config)
            local_cfg["db_type"] = "sqlite"
            local_logger = StudyLogger(local_cfg)
            rows = local_logger.get_all_sessions()
            self.stats_ready.emit(rows, open_browser)
        except Exception as e:
            self.error_occurred.emit(str(e))
