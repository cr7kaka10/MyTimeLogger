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

    def update_task_status(self, ticktick_id: str, status: int):
        """仅更新任务的状态（例如用于标记已检查且失败的任务）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET status = ? WHERE ticktick_id = ?", (status, ticktick_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"更新任务状态失败: {e}")
            return False

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

    def get_all_active_tasks(self):
        """获取本地缓存的所有未完成任务，用于启动时比对丢失任务"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT raw_json FROM tasks WHERE status = 0")
            rows = cursor.fetchall()
            conn.close()
            result = []
            for r in rows:
                try:
                    result.append(json.loads(r['raw_json']))
                except: pass
            return result
        except Exception as e:
            logging.error(f"读取本地活跃任务失败: {e}")
            return []

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
            cursor.execute("PRAGMA table_info(rewards)")
            reward_cols = [c[1] for c in cursor.fetchall()]
            if 'unlock_task_id' not in reward_cols:
                cursor.execute("ALTER TABLE rewards ADD COLUMN unlock_task_id TEXT DEFAULT NULL")
                cursor.execute("ALTER TABLE rewards ADD COLUMN unlock_task_title TEXT DEFAULT NULL")
            # 自定义奖励配置表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reward_config (
                    item_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    coins REAL NOT NULL DEFAULT 0.1,
                    PRIMARY KEY (item_type, item_id)
                )
            ''')
            # 外部系统静默打卡奖励表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS external_rewards (
                    id TEXT PRIMARY KEY,
                    item_type TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    coins REAL NOT NULL DEFAULT 0,
                    status INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 目标挑战表 (类似 aTimeLogger Pro Goals)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    category_id INTEGER,  -- 关联的时间分类ID
                    metric TEXT NOT NULL,  -- 'duration'(时长) 或 'count'(次数)
                    target_value REAL NOT NULL, -- 目标值（分钟或次数）
                    period TEXT NOT NULL,  -- 'daily', 'weekly', 'monthly'
                    reward_coins REAL DEFAULT 0,
                    reward_id INTEGER DEFAULT NULL, -- 关联的兑换项ID
                    operator TEXT DEFAULT '>=',      -- '>=' 或 '<='
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime'))
                )
            ''')
            # 自动迁移 goals 表
            cursor.execute("PRAGMA table_info(goals)")
            cols = [c[1] for c in cursor.fetchall()]
            if 'reward_id' not in cols:
                cursor.execute("ALTER TABLE goals ADD COLUMN reward_id INTEGER DEFAULT NULL")
            if 'operator' not in cols:
                cursor.execute("ALTER TABLE goals ADD COLUMN operator TEXT DEFAULT '>='")
            if 'penalty_coins' not in cols:
                cursor.execute("ALTER TABLE goals ADD COLUMN penalty_coins REAL DEFAULT 0")

            # 再次检查 reward_config
            cursor.execute("PRAGMA table_info(reward_config)")
            rc_cols = [c[1] for c in cursor.fetchall()]
            if 'penalty' not in rc_cols:
                cursor.execute("ALTER TABLE reward_config ADD COLUMN penalty REAL DEFAULT NULL")
                
            # 兼容 MySQL
            if self.db_type == "mysql":
                 cursor.execute('''
                    CREATE TABLE IF NOT EXISTS goals (
                        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
                        title TEXT NOT NULL,
                        category_id INT,
                        metric VARCHAR(20) NOT NULL,
                        target_value DECIMAL(10,2) NOT NULL,
                        period VARCHAR(20) NOT NULL,
                        reward_coins DECIMAL(10,2) DEFAULT 0,
                        reward_id INT DEFAULT NULL,
                        operator VARCHAR(10) DEFAULT '>=',
                        is_active TINYINT DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
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
                        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, 'habit_miss', ?, ?, ?)",
                                       (-penalty, hid, f'超时未打卡: {title}', now_str))
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

    def add_ledger_entry(self, amount, source_type, source_id=None, description='', created_at=None):
        """写入一条积分流水，并防止重复入账"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 校验重复：如果 source_id 存在，检查是否已经有该来源的记录
            if source_id:
                cursor.execute("SELECT id FROM reward_ledger WHERE source_type = ? AND source_id = ?", (source_type, str(source_id)))
                if cursor.fetchone():
                    logging.info(f"忽略重复流水: {source_type}/{source_id}")
                    conn.close()
                    return False

            now_str = created_at if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # 在描述中补全具体的打卡时间点，方便用户回溯详情
            final_desc = description
            if now_str not in description:
                # 提取日期时间，如果是补卡则保留补卡字样
                final_desc = f"{description} [{now_str}]"

            cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, ?, ?, ?, ?)",
                           (amount, source_type, source_id, final_desc, now_str))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"写入积分流水失败: {e}")
            return False

    # ======================== 自定义奖励配置 ========================

    def get_item_reward(self, item_type: str, item_id: str, default: float = 0.1) -> dict:
        """获取指定任务/习惯的奖励配置，返回 {'reward': x, 'penalty': y}"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT coins, penalty FROM reward_config WHERE item_type = ? AND item_id = ?",
                           (item_type, item_id))
            row = cursor.fetchone()
            conn.close()
            if row:
                return {
                    'reward': row[0],
                    'penalty': row[1] if row[1] is not None else row[0] # 默认惩罚=奖励
                }
            return {'reward': default, 'penalty': default}
        except Exception:
            return {'reward': default, 'penalty': default}

    def set_item_reward(self, item_type: str, item_id: str, coins: float, penalty: float = None):
        """设置指定任务/习惯的奖励和惩罚金币数"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO reward_config (item_type, item_id, coins, penalty) VALUES (?, ?, ?, ?)",
                (item_type, item_id, coins, penalty if penalty is not None else coins)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"设置奖励配置失败: {e}")
            return False

    def add_external_reward(self, ext_id: str, item_type: str, item_name: str, coins: float, status: int = 0):
        """添加外部完成奖励记录 (status=0待领取, status=1已本地领取/完成)"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            # 使用 INSERT OR IGNORE 防重复。如果是本地先完成插入的status=1，后面后台扫描到也不会被覆盖
            cursor.execute(
                "INSERT OR IGNORE INTO external_rewards (id, item_type, item_name, coins, status) VALUES (?, ?, ?, ?, ?)",
                (ext_id, item_type, item_name, coins, status)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"添加外部奖励失败: {e}")
            return False

    def remove_external_reward(self, ext_id: str):
        """移除外部奖励记录（用于取消打卡时）"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM external_rewards WHERE id = ?", (ext_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_unclaimed_rewards(self) -> list:
        """获取所有待领取的外部奖励"""
        import time
        now = time.time()
        if not hasattr(self, '_last_auto_settle') or now - self._last_auto_settle > 10:
            self.auto_settle_goals()
            self._last_auto_settle = now
            
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM external_rewards WHERE status = 0 ORDER BY created_at DESC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def claim_rewards(self, ext_ids: list) -> float:
        """将指定的奖励标记为已领取，并分条写入积分流水"""
        if not ext_ids: return 0.0
        total_coins = 0.0
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 获取所有待领取的项详情
            placeholders = ','.join(['?'] * len(ext_ids))
            cursor.execute(f"SELECT id, item_name, coins FROM external_rewards WHERE status = 0 AND id IN ({placeholders})", tuple(ext_ids))
            items = cursor.fetchall()
            
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            for item_id, item_name, coins in items:
                total_coins += coins
                # 为每一项单独插入流水，满足用户分条展示的需求
                cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, 'external_claim', ?, ?, ?)",
                               (coins, item_id, f"领取奖励: {item_name}", now_str))
            
            # 批量更新外部奖励表状态为已领取
            cursor.execute(f"UPDATE external_rewards SET status = 1 WHERE status = 0 AND id IN ({placeholders})", tuple(ext_ids))
            
            conn.commit()
            conn.close()
            return total_coins
        except Exception as e:
            logging.error(f"领取外部奖励失败: {e}")
            return 0.0

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

    def add_reward(self, title, icon='🎁', price=10, description='', unlock_task_id=None, unlock_task_title=None):
        """新增奖励商品"""
        try:
            self._migrate_habits_table()
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO rewards (title, icon, price, description, unlock_task_id, unlock_task_title) VALUES (?, ?, ?, ?, ?, ?)",
                (title, icon, price, description, unlock_task_id, unlock_task_title)
            )
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

    def update_reward(self, reward_id, title, icon='🎁', price=10, description='', unlock_task_id=None, unlock_task_title=None):
        """修改奖励商品配置"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE rewards SET title=?, icon=?, price=?, description=?, unlock_task_id=?, unlock_task_title=? WHERE id=?",
                (title, icon, price, description, unlock_task_id, unlock_task_title, reward_id)
            )
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"修改奖励失败: {e}")
            return False

    def is_task_completed(self, ticktick_id: str) -> bool:
        """检查指定任务是否已完成（本地或外部记录）"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            # 检查本地 tasks 表
            cursor.execute("SELECT status FROM tasks WHERE ticktick_id = ?", (ticktick_id,))
            row = cursor.fetchone()
            if row:
                conn.close()
                # 如果任务存在于本地表中，必须是完成状态 (2)
                return row[0] == 2
                
            # 1. 检查目标解锁额度 (ID 以 goal_ 开头)
            if ticktick_id.startswith("goal_"):
                # 注意：此处为向后兼容保留，建议直接调用 get_available_unlocks
                return False

            # 2. 检查外部领取记录（包括任务和习惯）
            cursor.execute("SELECT 1 FROM external_rewards WHERE id = ? OR id = ?", (f"task_{ticktick_id}", f"habit_{ticktick_id}"))
            if cursor.fetchone():
                conn.close()
                return True
                
            conn.close()
            return False
        except Exception:
            return False

    def get_available_unlocks(self, unlock_task_id: str, reward_id: int) -> int:
        """
        计算特定解锁条件剩余的兑换额度。
        原理：目标达成总次数（扣除惩罚记录） - 该奖励已被兑换的总次数
        """
        if not unlock_task_id:
            return 0
            
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 1. 计算达成总次数
            achieved_count = 0
            if unlock_task_id.startswith("goal_"):
                # 对于目标，查找 external_rewards 中所有大于等于0金币（排除惩罚）的记录
                cursor.execute("SELECT COUNT(*) FROM external_rewards WHERE id LIKE ? AND coins >= 0", (f"{unlock_task_id}_%",))
                achieved_count = cursor.fetchone()[0] or 0
            else:
                # 对于任务或习惯，通常只能完成一次
                cursor.execute("SELECT 1 FROM tasks WHERE ticktick_id = ? AND status = 2", (unlock_task_id,))
                if cursor.fetchone():
                    achieved_count = 1
                else:
                    cursor.execute("SELECT COUNT(*) FROM external_rewards WHERE id = ? OR id = ?", (f"task_{unlock_task_id}", f"habit_{unlock_task_id}"))
                    achieved_count = cursor.fetchone()[0] or 0
                    
            # 2. 计算已兑换次数
            cursor.execute("SELECT COUNT(*) FROM reward_ledger WHERE source_type = 'reward_unlock' AND source_id = ?", (reward_id,))
            used_count = cursor.fetchone()[0] or 0
            
            conn.close()
            return max(0, achieved_count - used_count)
        except Exception as e:
            logging.error(f"获取解锁额度失败: {e}")
            return 0

    def get_all_rewards(self):
        """获取所有激活的奖励项目"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM rewards WHERE is_active = 1 ORDER BY price ASC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

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
            
            # 兼容旧表可能没有这些字段
            unlock_task_id = reward['unlock_task_id'] if 'unlock_task_id' in reward.keys() else None
            unlock_task_title = reward['unlock_task_title'] if 'unlock_task_title' in reward.keys() else None

            if unlock_task_id:
                # 这是一个任务/目标解锁型奖励
                conn.close() 
                available = self.get_available_unlocks(unlock_task_id, reward_id)
                if available <= 0:
                    return False, f'需要先完成条件「{unlock_task_title or "未知"}」才能兑换（或剩余额度不足）！'
                
                # 如果有剩余额度，兑换成功，但不扣积分，记录0金币的流水
                now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn = self._get_connection()
                cursor = conn.cursor()
                cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, 'reward_unlock', ?, ?, ?)",
                               (0, reward_id, f'任务解锁兑换: {title}', now_str))
                conn.commit()
                conn.close()
                return True, f'成功兑换「{title}」！'
            
            cursor.execute("SELECT SUM(amount) FROM reward_ledger")
            balance = cursor.fetchone()[0] or 0
            if balance < price:
                conn.close()
                return False, f'余额不足（需要 {price}🪙，当前 {round(balance,1)}🪙）'
            
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("INSERT INTO reward_ledger (amount, source_type, source_id, description, created_at) VALUES (?, 'reward_buy', ?, ?, ?)",
                           (-price, reward_id, f'购买奖励: {title}', now_str))
            conn.commit()
            conn.close()
            return True, f'成功兑换「{title}」！'
        except Exception as e:
            logging.error(f"购买奖励失败: {e}")
            return False, str(e)

    # ======================== 目标挑战系统 (Goals) ========================

    def add_goal(self, title, category_id, metric, target_value, period, reward_coins, reward_id=None, operator='>=', penalty_coins=None):
        """添加新目标"""
        try:
            if penalty_coins is None: penalty_coins = reward_coins
            conn = self._get_connection()
            cursor = conn.cursor()
            placeholder = "%s" if self.db_type == "mysql" else "?"
            sql = f"INSERT INTO goals (title, category_id, metric, target_value, period, reward_coins, reward_id, operator, penalty_coins) VALUES ({','.join([placeholder]*9)})"
            cursor.execute(sql, (title, category_id, metric, target_value, period, reward_coins, reward_id, operator, penalty_coins))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"添加目标失败: {e}")
            return False

    def remove_goal(self, goal_id):
        """下架/删除目标"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE goals SET is_active = 0 WHERE id = ?", (goal_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def update_goal(self, goal_id, **kwargs):
        """更新目标配置"""
        if not kwargs: return False
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            fields = ", ".join([f"{k} = ?" for k in kwargs.keys()])
            values = list(kwargs.values())
            values.append(goal_id)
            cursor.execute(f"UPDATE goals SET {fields} WHERE id = ?", values)
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"更新目标失败: {e}")
            return False

    def get_all_goals(self):
        """获取所有激活的目标"""
        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM goals WHERE is_active = 1 ORDER BY created_at DESC")
            rows = [dict(r) for r in cursor.fetchall()]
            conn.close()
            return rows
        except Exception:
            return []

    def auto_settle_goals(self):
        """自动结算单次和每日目标（包括成功和失败）"""
        try:
            from datetime import date, timedelta
            today = date.today()
            yesterday = today - timedelta(days=1)
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM goals WHERE is_active = 1")
            goals = [dict(r) for r in cursor.fetchall()]
            
            for g in goals:
                g_id, title, cat_id, period, metric = g['id'], g['title'], g['category_id'], g['period'], g['metric']
                target = g['target_value']
                operator = g.get('operator', '>=')
                reward_coins = g['reward_coins']
                penalty_coins = g.get('penalty_coins', reward_coins)
                created_at_goal = g.get('created_at', '2000-01-01') # 目标创建时间
                
                def _issue(claim_id, is_met, val, target_val, operator_str, date_str, fail_if_not_met=False):
                    cursor.execute("SELECT 1 FROM external_rewards WHERE id = ?", (claim_id,))
                    if cursor.fetchone(): return
                    
                    amount, desc = 0, ""
                    unit = "m" if metric == 'duration' else "次"
                    status_text = "达成" if is_met else "未达标"
                    # 详细描述：目标达成[2026-05-05]: 标题 (实际 45m / 目标 <=60m)
                    desc = f"目标{status_text}[{date_str}]: {title} ({int(val)}{unit} / {operator_str}{int(target_val)}{unit})"
                    
                    if is_met:
                        amount = reward_coins
                    elif fail_if_not_met:
                        amount = -abs(penalty_coins)
                    else:
                        return
                        
                    if amount != 0:
                        cursor.execute("INSERT INTO external_rewards (id, item_type, item_name, coins, status, created_at) VALUES (?, 'goal', ?, ?, 0, ?)",
                                       (claim_id, desc, amount, now_str))
                
                last_reset_str = self.config.get("last_reset_time", "2026-05-01 00:00:00")
                
                if period == 'per_session':
                    cursor.execute("SELECT id, net_duration_minutes, start_time FROM study_sessions WHERE category_id = ? AND date = ? AND start_time > ?", (cat_id, today.strftime('%Y-%m-%d'), last_reset_str))
                    for s_id, s_dur, s_time in cursor.fetchall():
                        # 会话开始时间也必须在目标创建之后
                        if s_time < created_at_goal:
                            continue
                        is_met = (s_dur >= target) if operator == '>=' else (s_dur <= target)
                        # 单次目标每次完成后立刻结算
                        _issue(f"goal_{g_id}_session_{s_id}", is_met, s_dur, target, operator, s_time[:10], fail_if_not_met=True)
                
                elif period == 'daily':
                    for d in [yesterday, today]:
                        d_str = d.strftime('%Y-%m-%d')
                        # 核心修正：结算日期不能早于目标创建日期
                        if d_str < created_at_goal[:10]:
                            continue
                        
                        if d_str < last_reset_str[:10]:
                            continue
                            
                        if metric == 'duration':
                            cursor.execute("SELECT SUM(net_duration_minutes) FROM study_sessions WHERE category_id = ? AND date = ? AND start_time > ?", (cat_id, d_str, last_reset_str))
                        else:
                            cursor.execute("SELECT COUNT(*) FROM study_sessions WHERE category_id = ? AND date = ? AND start_time > ?", (cat_id, d_str, last_reset_str))
                        val = cursor.fetchone()[0] or 0.0
                        
                        is_met = (val >= target) if operator == '>=' else (val <= target)
                        claim_id = f"goal_{g_id}_{d_str.replace('-', '')}"
                        
                        if d == yesterday:
                            # 昨天已结束，无论成败均结算
                            _issue(claim_id, is_met, val, target, operator, d_str, fail_if_not_met=True)
                        else:
                            # 今天：仅在确定状态（>= 达成 或 <= 失败）时提前结算
                            if operator == '>=' and is_met:
                                _issue(claim_id, True, val, target, operator, d_str)
                            elif operator == '<=' and not is_met:
                                _issue(claim_id, False, val, target, operator, d_str, fail_if_not_met=True)
                            # 对于 <= 且当前未超限的情况，必须等到明天结算
            
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"目标自动结算失败: {e}")

    def get_goal_progress(self, goal_dict, active_session_info=None):
        """计算目标的当前进度"""
        from datetime import date, timedelta
        import calendar

        metric = goal_dict['metric']
        period = goal_dict['period']
        cat_id = goal_dict['category_id']
        
        # 计算起止日期
        today = date.today()
        start_date = today
        end_date = today

        if period == 'daily':
            start_date = today
            end_date = today
        elif period == 'weekly':
            # 周一为起点
            start_date = today - timedelta(days=today.weekday())
            end_date = start_date + timedelta(days=6)
        elif period == 'monthly':
            start_date = today.replace(day=1)
            _, last_day = calendar.monthrange(today.year, today.month)
            end_date = today.replace(day=last_day)
        
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        operator = goal_dict.get('operator', '>=')
        target = goal_dict.get('target_value', 0)

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if period == 'per_session':
                # "每次" 逻辑：查找今日最近一次尚未领取的达标记录
                # 首先找到今日该分类的所有 session id
                cursor.execute("SELECT id, net_duration_minutes FROM study_sessions WHERE category_id = ? AND date = ? ORDER BY id DESC",
                               (cat_id, today.strftime('%Y-%m-%d')))
                sessions = cursor.fetchall()
                
                val = 0
                claim_id = ""
                is_claimed = False
                
                # 寻找最新一个符合条件的且未领取的 session
                for s_id, s_dur in sessions:
                    # 检查达标条件
                    met = False
                    if operator == '>=': met = (s_dur >= target)
                    else: met = (s_dur <= target)
                    
                    if met:
                        c_id = f"goal_{goal_dict['id']}_session_{s_id}"
                        cursor.execute("SELECT 1 FROM external_rewards WHERE id = ?", (c_id,))
                        if cursor.fetchone():
                            # 已领取，继续找下一个（或者如果这是最新的，就显示已完成）
                            if not claim_id:
                                claim_id = c_id
                                is_claimed = True
                                val = s_dur
                            continue
                        else:
                            # 找到了一个符合条件且未领取的
                            val = s_dur
                            claim_id = c_id
                            is_claimed = False
                            break
                
                # 如果完全没找到 session，尝试使用当前计时器
                if not sessions and active_session_info:
                    a_cat_id = active_session_info.get('category_id')
                    a_duration = active_session_info.get('duration_minutes', 0)
                    if a_cat_id == cat_id:
                        val = a_duration
                        # 当前计时器无法领取，因为它还没入库
                
                conn.close()
                return val, is_claimed, claim_id

            # 以下为累计型逻辑 (daily/weekly/monthly)
            if metric == 'duration':
                # 计算累计时长
                cursor.execute("SELECT SUM(net_duration_minutes) FROM study_sessions WHERE category_id = ? AND date BETWEEN ? AND ?",
                               (cat_id, start_str, end_str))
                val = cursor.fetchone()[0] or 0.0
            else:
                # 计算累计次数
                cursor.execute("SELECT COUNT(*) FROM study_sessions WHERE category_id = ? AND date BETWEEN ? AND ?",
                               (cat_id, start_str, end_str))
                val = cursor.fetchone()[0] or 0
                
            # 实时进度叠加：如果当前正在计时且分类匹配
            if active_session_info:
                a_cat_id = active_session_info.get('category_id')
                a_duration = active_session_info.get('duration_minutes', 0)
                if a_cat_id == cat_id:
                    if metric == 'duration':
                        val += a_duration
                    # 次数通常在结束后结算，实时刷新不计次
            
            # 检查是否已领取
            period_tag = start_str.replace('-', '')
            if period == 'weekly':
                period_tag = f"{start_date.year}W{start_date.isocalendar()[1]}"
            elif period == 'monthly':
                period_tag = start_date.strftime('%Y%m')
                
            claim_id = f"goal_{goal_dict['id']}_{period_tag}"
            cursor.execute("SELECT 1 FROM external_rewards WHERE id = ?", (claim_id,))
            is_claimed = cursor.fetchone() is not None
            
            conn.close()
            return val, is_claimed, claim_id
        except Exception as e:
            logging.error(f"计算目标进度失败: {e}")
            return 0, False, ""

    def get_goal_daily_stats(self, goal_dict, start_str, end_str):
        """
        获取目标在指定日期范围内的每日进度统计。
        返回格式: {'YYYY-MM-DD': value}
        """
        metric = goal_dict['metric']
        cat_id = goal_dict['category_id']
        period = goal_dict['period']
        
        # 单次目标不提供每日趋势
        if period == 'per_session':
            return {}

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            if metric == 'duration':
                cursor.execute("SELECT date, SUM(net_duration_minutes) FROM study_sessions WHERE category_id = ? AND date BETWEEN ? AND ? GROUP BY date", (cat_id, start_str, end_str))
            else:
                cursor.execute("SELECT date, COUNT(*) FROM study_sessions WHERE category_id = ? AND date BETWEEN ? AND ? GROUP BY date", (cat_id, start_str, end_str))
                
            rows = cursor.fetchall()
            conn.close()
            
            return {r[0]: r[1] for r in rows}
        except Exception as e:
            logging.error(f"获取目标趋势失败: {e}")
            return {}

    def get_task_coins(self, priority):
        """根据任务优先级返回积分收益"""
        diff = self.PRIORITY_TO_DIFFICULTY.get(priority, 'trivial')
        return self.DIFFICULTY_MAP[diff]['task_coins']

    # ======================== 重置功能 = : redesigned ========================

    def reset_coins(self):
        """重置金币：清空流水和待领取"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reward_ledger")
            cursor.execute("DELETE FROM external_rewards")
            conn.commit()
            conn.close()
            
            # 记录重置时间点，防止旧记录重新触发奖励结算
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.config["last_reset_time"] = now_str
            from config import save_config
            save_config(self.config)
            
            return True
        except Exception as e:
            logging.error(f"重置金币失败: {e}")
            return False

    def reset_ledger(self):
        """重置金币流水：仅清空流水记录"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reward_ledger")
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"重置流水失败: {e}")
            return False

    def reset_focus_records(self):
        """重置专注记录：清空 study_sessions 表"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM study_sessions")
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"重置专注记录失败: {e}")
            return False


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
