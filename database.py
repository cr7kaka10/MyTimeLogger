# -*- coding: utf-8 -*-
"""
数据库模块 (database.py)
========================
封装所有数据持久化逻辑:
- StudyLogger: 底层存储层，支持 SQLite（本地）和 MySQL（远程）双引擎
- DatabaseWorker: 基于 QThread 的异步工作者，负责 MySQL 镜像同步和统计数据拉取
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

# MySQL 驱动（可选依赖）
try:
    import pymysql
except ImportError:
    pymysql = None


# ==============================================================================
# 学习日志记录器 (底层存储)
# ==============================================================================
class StudyLogger:
    """
    学习会话的数据库读写层。

    支持 SQLite 和 MySQL 两种后端:
    - SQLite: 本地存储，构造时即完成初始化（毫秒级）
    - MySQL: 远程存储，由 DatabaseWorker 异步初始化

    还负责从旧版 JSON 日志自动迁移数据到 SQLite。
    """

    def __init__(self, config=None):
        self.config = config if config else DEFAULT_CONFIG
        self.db_type = self.config.get("db_type", "sqlite")
        self.log_path = resource_path("study_log.db")
        self._conn = None

        # 本地 SQLite 初始化在构造时完成（毫秒级）
        if self.db_type == "sqlite":
            self._initialize_db()
            self._migrate_from_json()
        # MySQL 的初始化由 DatabaseWorker 异步处理，不在构造函数进行

    def _get_connection(self):
        """
        根据配置获取数据库连接。

        MySQL 模式下支持连接复用和自动重连。
        SQLite 模式下每次返回新连接。
        """
        if self.db_type == "mysql":
            if pymysql is None:
                raise ImportError("未安装 pymysql，请运行 'pip install pymysql'")

            # 检查现有连接是否依然活跃
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
        """初始化数据库表结构（采用 IF NOT EXISTS 确保数据非破坏性）"""
        if self.db_type == "sqlite":
            self._migrate_from_json()
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            if self.db_type == "mysql":
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS study_sessions (
                        id INT AUTO_INCREMENT PRIMARY KEY COMMENT '唯一标识',
                        start_time DATETIME NOT NULL COMMENT '开始时间',
                        end_time DATETIME NOT NULL COMMENT '结束时间',
                        net_duration_minutes DECIMAL(10,2) NOT NULL COMMENT '专注时长(分)',
                        date DATE NOT NULL COMMENT '日期',
                        day_of_week VARCHAR(20) COMMENT '星期',
                        pause_count INT DEFAULT 0 COMMENT '暂停次数',
                        pause_reasons TEXT COMMENT '暂停原因明细',
                        session_summary TEXT COMMENT '专注总结内容',
                        category_id VARCHAR(36) DEFAULT NULL COMMENT '所属分类'
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='专注学习记录表';
                ''')
            else:
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
                        category_id TEXT DEFAULT NULL
                    )
                ''')
            conn.commit()
            conn.close()
            self._migrate_add_category_id()
        except Exception as e:
            print(f"数据库初始化失败: {e}")

    def _migrate_add_category_id(self):
        """如果表已存在且缺失，补充 category_id 字段"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            if self.db_type == "mysql":
                cursor.execute("SHOW COLUMNS FROM study_sessions LIKE 'category_id'")
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE study_sessions ADD COLUMN category_id VARCHAR(36) DEFAULT NULL COMMENT '所属分类'")
            else:
                cursor.execute("PRAGMA table_info(study_sessions)")
                columns = [row[1] for row in cursor.fetchall()]
                if "category_id" not in columns:
                    cursor.execute("ALTER TABLE study_sessions ADD COLUMN category_id TEXT DEFAULT NULL")
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"字段迁移 category_id 失败: {e}")

    def _migrate_from_json(self):
        """如果存在旧的 JSON 日志文件，则迁移数据到 SQLite"""
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
                    logging.info(f"完成从 JSON 迁移 {len(records)} 条记录到数据库。")

                # 迁移成功后重命名旧文件
                os.rename(json_path, json_path + ".bak")
            except Exception as e:
                logging.error(f"数据迁移失败: {e}")

    def log_session(self, start_time: datetime, end_time: datetime,
                    net_duration_seconds: int, pause_count: int = 0,
                    pause_reasons: str = "", session_summary: str = "",
                    category_id: str = None):
        """
        记录一个完整的学习会话到数据库。

        Args:
            start_time: 会话开始时间
            end_time: 会话结束时间
            net_duration_seconds: 净专注时长（秒）
            pause_count: 暂停次数
            pause_reasons: 暂停原因明细（分号分隔）
            session_summary: 专注总结内容
            category_id: 柳比歇夫分类 ID
        """
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

            # sqlite3 使用 ?, pymysql 使用 %s
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

    def get_all_sessions(self):
        """
        从数据库读取所有会话记录。

        Returns:
            list: 所有记录的列表，每条记录为字符串列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT start_time, end_time, net_duration_minutes, date, day_of_week, 
                       pause_count, pause_reasons, session_summary, category_id 
                FROM study_sessions
                ORDER BY start_time ASC
            ''')
            rows = cursor.fetchall()
            conn.close()
            return [list(map(str, row)) for row in rows]
        except Exception as e:
            logging.error(f"读取数据库失败: {e}")
            return []


# ==============================================================================
# 异步数据库工作者 (Worker Thread)
# ==============================================================================
class DatabaseWorker(QObject):
    """
    后台线程工作者，处理耗时的数据库操作。

    职责:
    - 异步初始化远程 MySQL 连接
    - 将本地记录镜像同步到远程 MySQL
    - 异步拉取统计数据供 GUI 渲染

    通过 Qt 信号与主线程通信，避免阻塞 UI。
    """
    logged = pyqtSignal()
    stats_ready = pyqtSignal(list, bool)     # (数据行列表, 是否打开浏览器)
    error_occurred = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        # 创建专门用于远程备份的 Logger 实例（强制为 mysql 模式）
        self.mysql_cfg = copy.deepcopy(config)
        self.mysql_cfg["db_type"] = "mysql"
        self.backup_logger = StudyLogger(self.mysql_cfg)

    def init_db(self):
        """后台异步初始化远程数据库连接"""
        try:
            m_cfg = self.config.get("mysql_config", {})
            if any(not k.startswith("//") for k in m_cfg.keys()):
                logging.info("[MySQL] 正在后台建立远程连接并自检表结构...")
                self.backup_logger._initialize_db()
                logging.info("[MySQL] 远程数据库连接成功，镜像同步已就绪。")
            else:
                logging.info("[MySQL] 未检测到有效配置，跳过远程同步。")
        except Exception as e:
            logging.error(f"[MySQL] 远程初始化失败 (不影响本地): {e}")

    def sync_to_backup(self, data_dict):
        """将本地记录异步镜像到远程 MySQL"""
        m_cfg = self.config.get("mysql_config", {})
        if any(not k.startswith("//") for k in m_cfg.keys()):
            try:
                logging.info("[MySQL] 正在将专注记录同步至云端...")
                self.backup_logger.log_session(**data_dict)
                logging.info("[MySQL] 镜像同步完成。")
            except Exception as e:
                logging.error(f"[MySQL] 镜像同步过程中断: {e}")

    def fetch_stats(self, open_browser=False):
        """从本地 SQLite 读取统计数据（确保速度）"""
        try:
            local_cfg = copy.deepcopy(self.config)
            local_cfg["db_type"] = "sqlite"
            local_logger = StudyLogger(local_cfg)
            rows = local_logger.get_all_sessions()
            self.stats_ready.emit(rows, open_browser)
        except Exception as e:
            self.error_occurred.emit(str(e))
