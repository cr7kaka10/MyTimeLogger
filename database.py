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
                        title TEXT NOT NULL,
                        icon TEXT NOT NULL DEFAULT '✅',
                        color TEXT NOT NULL DEFAULT '#A3BE8C',
                        frequency TEXT NOT NULL DEFAULT 'daily',
                        category_id INTEGER DEFAULT NULL,
                        sort_order INTEGER NOT NULL DEFAULT 0,
                        is_active INTEGER NOT NULL DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS habit_checkins (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        habit_id INTEGER NOT NULL,
                        checkin_date TEXT NOT NULL,
                        checkin_time TEXT,
                        note TEXT DEFAULT '',
                        FOREIGN KEY (habit_id) REFERENCES habits(id)
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

    # ======================== 习惯系统 CRUD ========================

    # ==================== 难度 & 积分常量 ====================
    DIFFICULTY_MAP = {
        'trivial': {'task_coins': 1, 'habit_coins': 0.5, 'streak_bonus': 0.1, 'penalty': 0.25, 'color': '#4CAF50'},
        'easy':    {'task_coins': 2, 'habit_coins': 1,   'streak_bonus': 0.2, 'penalty': 0.5,  'color': '#2196F3'},
        'medium':  {'task_coins': 5, 'habit_coins': 2.5, 'streak_bonus': 0.5, 'penalty': 1.25, 'color': '#FF9800'},
        'hard':    {'task_coins': 10,'habit_coins': 5,   'streak_bonus': 1.0, 'penalty': 2.5,  'color': '#FF5252'},
    }
    PRIORITY_TO_DIFFICULTY = {5: 'hard', 3: 'medium', 1: 'easy', 0: 'trivial'}
    FORCE_CHANGE_FEE = 1.0  # 10s 强改手续费

    def _migrate_habits_table(self):
        """旧表迁移：若 habits 表缺少新字段则 ALTER"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(habits)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'icon' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN icon TEXT NOT NULL DEFAULT '✅'")
            if 'color' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN color TEXT NOT NULL DEFAULT '#A3BE8C'")
            if 'frequency' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN frequency TEXT NOT NULL DEFAULT 'daily'")
            if 'sort_order' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            if 'is_active' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
            if 'created_at' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            if 'time_start' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN time_start TEXT DEFAULT NULL")
            if 'time_end' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN time_end TEXT DEFAULT NULL")
            if 'difficulty' not in cols: cursor.execute("ALTER TABLE habits ADD COLUMN difficulty TEXT DEFAULT 'easy'")
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS habit_checkins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    habit_id INTEGER NOT NULL,
                    checkin_date TEXT NOT NULL,
                    checkin_time TEXT,
                    note TEXT DEFAULT '',
                    FOREIGN KEY (habit_id) REFERENCES habits(id)
                )
            ''')
            
            cursor.execute("PRAGMA table_info(habit_checkins)")
            checkin_cols = [c[1] for c in cursor.fetchall()]
            if 'status' not in checkin_cols:
                cursor.execute("ALTER TABLE habit_checkins ADD COLUMN status INTEGER DEFAULT 1")

            # 积分流水表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reward_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 奖励商品表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rewards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    icon TEXT DEFAULT '🎁',
                    price REAL NOT NULL DEFAULT 10,
                    description TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 自定义奖励配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reward_config (
                    item_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    coins REAL NOT NULL DEFAULT 1.0,
                    PRIMARY KEY (item_type, item_id)
                )
            ''')
                
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"习惯表迁移失败: {e}")

    def get_all_habits(self):
        """获取所有启用的习惯"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM habits WHERE is_active = 1 ORDER BY sort_order ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception as e:
            logging.error(f"获取习惯列表失败: {e}")
            return []

    def add_habit(self, title, icon='✅', color='#A3BE8C', frequency='daily', category_id=None, time_start=None, time_end=None, difficulty='easy'):
        """新增习惯"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(sort_order) FROM habits")
            max_order = cursor.fetchone()[0] or 0
            cursor.execute('''
                INSERT INTO habits (title, icon, color, frequency, category_id, sort_order, is_active, time_start, time_end, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            ''', (title, icon, color, frequency, category_id, max_order + 1, time_start, time_end, difficulty))
            new_id = cursor.lastrowid
            conn.commit()
            conn.close()
            return new_id
        except Exception as e:
            logging.error(f"新增习惯失败: {e}")
            return None

    def update_habit(self, habit_id, **kwargs):
        """更新习惯属性"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            updates, params = [], []
            for key in ['title', 'icon', 'color', 'frequency', 'category_id', 'sort_order', 'time_start', 'time_end', 'difficulty']:
                if key in kwargs:
                    updates.append(f"{key} = ?")
                    params.append(kwargs[key])
            if not updates:
                return False
            params.append(habit_id)
            cursor.execute(f"UPDATE habits SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"更新习惯失败: {e}")
            return False

    def remove_habit(self, habit_id):
        """软删除习惯"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE habits SET is_active = 0 WHERE id = ?", (habit_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"删除习惯失败: {e}")
            return False

    def toggle_checkin(self, habit_id, date_str=None, force=False):
        """打卡状态三态轮转（带积分入账）： 0(未打) -> 1(成功) -> -1(失败) -> 0(未打)"""
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, status, checkin_time FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?",
                           (habit_id, date_str))
            existing = cursor.fetchone()
            
            now = datetime.now()
            now_time = now.strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取习惯难度
            cursor.execute("SELECT difficulty, title FROM habits WHERE id = ?", (habit_id,))
            h_row = cursor.fetchone()
            diff = (h_row[0] if h_row and h_row[0] else 'easy')
            h_title = (h_row[1] if h_row else '未知习惯')
            diff_info = self.DIFFICULTY_MAP.get(diff, self.DIFFICULTY_MAP['easy'])
            
            coins_earned = 0  # 本次操作的积分变动
            
            if existing:
                rec_id = existing[0]
                curr_status = existing[1]
                c_time = existing[2]
                
                # 检查是否超过 10 秒
                if c_time and not force:
                    try:
                        try:
                            last_dt = datetime.strptime(c_time, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            last_dt = datetime.strptime(f"{date_str} {c_time}", '%Y-%m-%d %H:%M:%S')
                        if (now - last_dt).total_seconds() > 10:
                            conn.close()
                            return "timeout", 0, 0
                    except Exception:
                        pass
                
                # 强改手续费
                if force:
                    cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, 'penalty', ?, ?)",
                                   (-self.FORCE_CHANGE_FEE, habit_id, f'10s强改手续费: {h_title}'))
                    coins_earned -= self.FORCE_CHANGE_FEE
                
                if curr_status == 1:
                    cursor.execute("UPDATE habit_checkins SET status = -1, checkin_time = ? WHERE id = ?", (now_time, rec_id))
                    new_status = -1
                else:
                    cursor.execute("DELETE FROM habit_checkins WHERE id = ?", (rec_id,))
                    new_status = 0
            else:
                cursor.execute("INSERT INTO habit_checkins (habit_id, checkin_date, checkin_time, status) VALUES (?, ?, ?, 1)",
                               (habit_id, date_str, now_time))
                new_status = 1
                
            conn.commit()
            streak = self._calc_streak(cursor, habit_id, date_str, exclude_today=(new_status <= 0 and date_str == datetime.now().strftime('%Y-%m-%d')))
            
            # 积分入账
            if new_status == 1:
                base = diff_info['habit_coins']
                bonus = streak * diff_info['streak_bonus']
                total = round(base + bonus, 1)
                cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, 'habit_checkin', ?, ?)",
                               (total, habit_id, f'习惯打卡: {h_title} (🔥{streak})'))
                coins_earned += total
                conn.commit()
            
            conn.close()
            return new_status, streak, coins_earned
        except Exception as e:
            logging.error(f"打卡操作失败: {e}")
            return 0, 0, 0

    def _calc_streak(self, cursor, habit_id, today_str, exclude_today=False):
        """计算连续打卡天数（遇到 status=1 累加，遇到未打卡中断）"""
        from datetime import timedelta
        try:
            today = datetime.strptime(today_str, '%Y-%m-%d').date()
            streak = 0
            check_date = today if not exclude_today else today - timedelta(days=1)
            while True:
                date_s = check_date.strftime('%Y-%m-%d')
                cursor.execute("SELECT status FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?", (habit_id, date_s))
                row = cursor.fetchone()
                if row and row[0] == 1:
                    streak += 1
                    check_date -= timedelta(days=1)
                else:
                    break
            return streak
        except Exception:
            return 0

    def get_today_checkins(self, date_str=None):
        """获取今日所有打卡记状态，返回 {habit_id: status}"""
        if not date_str:
            date_str = datetime.now().strftime('%Y-%m-%d')
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT habit_id, status FROM habit_checkins WHERE checkin_date = ?", (date_str,))
            result = {row[0]: row[1] for row in cursor.fetchall()}
            conn.close()
            return result
        except Exception as e:
            logging.error(f"获取今日打卡失败: {e}")
            return {}

    def get_checkins_by_date_range(self, start_date_str, end_date_str):
        """批量获取打卡数据，返回 {habit_id: {date_str: status}}"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT habit_id, checkin_date, status FROM habit_checkins WHERE checkin_date BETWEEN ? AND ?", 
                           (start_date_str, end_date_str))
            result = {}
            for row in cursor.fetchall():
                hid, d, s = row[0], row[1], row[2]
                if hid not in result: result[hid] = {}
                result[hid][d] = s
            conn.close()
            return result
        except Exception as e:
            logging.error(f"获取范围打卡失败: {e}")
            return {}

    def get_habit_streak(self, habit_id):
        """获取某个习惯的连续成功天数"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            today_str = datetime.now().strftime('%Y-%m-%d')
            streak = self._calc_streak(cursor, habit_id, today_str)
            conn.close()
            return streak
        except Exception:
            return 0

    def auto_mark_missed_habits(self):
        """扫描并对超时的习惯注入 -1 的打卡失败记录（含惩罚扣分）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            now = datetime.now()
            today_str = now.strftime('%Y-%m-%d')
            now_time_str = now.strftime('%H:%M')
            full_time_str = now.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute("SELECT id, time_end, difficulty, title FROM habits WHERE is_active = 1 AND time_end IS NOT NULL AND time_end != ''")
            active_habits = cursor.fetchall()
            
            for hid, e_time, diff, title in active_habits:
                if now_time_str > e_time:
                    cursor.execute("SELECT id FROM habit_checkins WHERE habit_id = ? AND checkin_date = ?", (hid, today_str))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO habit_checkins (habit_id, checkin_date, checkin_time, status) VALUES (?, ?, ?, -1)",
                                       (hid, today_str, full_time_str))
                        # 超时惩罚扣分
                        diff = diff or 'easy'
                        penalty = self.DIFFICULTY_MAP.get(diff, self.DIFFICULTY_MAP['easy'])['penalty']
                        cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, 'habit_miss', ?, ?)",
                                       (-penalty, hid, f'超时未打卡: {title}'))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"超时打卡判定失败: {e}")

    # ======================== 积分系统 CRUD ========================

    def get_balance(self):
        """获取当前积分余额"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(amount) FROM reward_ledger")
            row = cursor.fetchone()
            conn.close()
            return round(row[0] or 0, 1)
        except Exception:
            return 0

    def add_ledger_entry(self, amount, source_type, source_id=None, description=''):
        """写入一条积分流水"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, ?, ?, ?)",
                           (amount, source_type, source_id, description))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"写入积分流水失败: {e}")
            return False

    # ======================== 自定义奖励配置 ========================

    def get_item_reward(self, item_type: str, item_id: str, default: float = 1.0) -> float:
        """获取指定任务/习惯的奖励金币数，不存在则返回默认值"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT coins FROM reward_config WHERE item_type = ? AND item_id = ?",
                           (item_type, item_id))
            row = cursor.fetchone()
            conn.close()
            return row[0] if row else default
        except Exception:
            return default

    def set_item_reward(self, item_type: str, item_id: str, coins: float):
        """设置指定任务/习惯的奖励金币数"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO reward_config (item_type, item_id, coins) VALUES (?, ?, ?)",
                (item_type, item_id, coins)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"设置奖励配置失败: {e}")
            return False

    def get_ledger_history(self, limit=30):
        """获取最近 N 条积分流水"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reward_ledger ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def get_all_rewards(self):
        """获取所有启用的奖励商品"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rewards WHERE is_active = 1 ORDER BY price ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def add_reward(self, title, icon='🎁', price=10, description=''):
        """新增奖励商品"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("INSERT INTO rewards (title, icon, price, description) VALUES (?, ?, ?, ?)",
                           (title, icon, price, description))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"新增奖励失败: {e}")
            return False

    def remove_reward(self, reward_id):
        """软删除奖励"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE rewards SET is_active = 0 WHERE id = ?", (reward_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def buy_reward(self, reward_id):
        """购买奖励：检查余额→扣款→写流水，返回 (success, message)"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rewards WHERE id = ? AND is_active = 1", (reward_id,))
            reward = cursor.fetchone()
            if not reward:
                conn.close()
                return False, '奖励不存在'
            price = reward['price']
            title = reward['title']
            
            cursor.execute("SELECT SUM(amount) FROM reward_ledger")
            balance = cursor.fetchone()[0] or 0
            if balance < price:
                conn.close()
                return False, f'余额不足（需要 {price}🪙，当前 {round(balance,1)}🪙）'
            
            cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description) VALUES (?, 'reward_buy', ?, ?)",
                           (-price, reward_id, f'购买奖励: {title}'))
            conn.commit()
            conn.close()
            return True, f'成功兑换「{title}」！'
        except Exception as e:
            logging.error(f"购买奖励失败: {e}")
            return False, str(e)

    def get_task_coins(self, priority):
        """根据任务优先级返回积分收益"""
        diff = self.PRIORITY_TO_DIFFICULTY.get(priority, 'trivial')
        return self.DIFFICULTY_MAP[diff]['task_coins']


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
