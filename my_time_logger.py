# --- START OF FILE my_time_logger.py ---

import time
import random
import os
import sys
import json
import pygame
import sqlite3
import copy
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

# --- PyQt6 Imports ---
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QSystemTrayIcon, QMessageBox, QSizeGrip, QInputDialog, QLineEdit, QPushButton, QDialog, QTextEdit, QDialogButtonBox
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QSettings, QSize, QThread, QLockFile
from PyQt6.QtGui import QIcon, QAction, QTextListFormat, QTextCursor
import re

# --- MySQL 支持 (可选) ---
try:
    import pymysql
except ImportError:
    pymysql = None

# --- 外部依赖: 全局快捷键 ---
# 请先安装: pip install pynput
try:
    from pynput import keyboard
except ImportError:
    # 在GUI中显示更友好的提示
    def show_pynput_error():
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("缺少关键组件: pynput")
        msg_box.setInformativeText("快捷键功能无法使用。\n请在命令行中运行 'pip install pynput' 来安装它。")
        msg_box.setWindowTitle("依赖缺失")
        msg_box.exec()
    # 稍后在主程序中调用
    keyboard = None


# --- 资源路径函数 ---
def resource_path(relative_path):
    """
    获取资源绝对路径，适配开发环境和 PyInstaller 单文件/文件夹打包模式。
    内置资源（音频/图标）存储在临时目录中；
    用户数据（配置/数据库/报表）存储在可执行文件同级目录中。
    """
    # 定义哪些文件是用户可写/持久化的数据
    user_data_files = [
        'config.json', 'study_log.db', 'study_log.json', 
        'statistics.html', 'study_log.csv'
    ]
    
    # 获取基础路径
    if relative_path in user_data_files or relative_path.endswith('.db') or relative_path.endswith('.json'):
        # 对于用户数据，始终使用可执行文件所在的真实目录
        try:
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.abspath(".")
        except Exception:
            base_path = os.path.abspath(".")
    else:
        # 对于只读资源（音乐、图标），优先使用 PyInstaller 的临时解压目录
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")
            
    return os.path.join(base_path, relative_path)

# --- 默认配置 ---
DEFAULT_CONFIG = {
    "study_time_min": 5 * 60,
    "study_time_max": 7 * 60,
    "short_break_duration": 10,
    "long_break_threshold": 90 * 60,
    "long_break_duration": 20 * 60,
    "music_folder": "study_music",
    "sound_files": {
        "start_short_break": "start_short_break.mp3",
        "start_long_break": "start_long_break.mp3",
        "end_long_break": "end_long_break.mp3",
        "victory": "victory.mp3",
        "start_study": "start_study.mp3"
    },
    "total_study_time": 0,
    "reset_password": "111",
    "hotkeys": {
        "start": "<alt>+z",
        "toggle_pause": "<alt>+c",
        "reset_cycle": "<ctrl>+<alt>+r"
    },
    "db_type": "sqlite",
    "mysql_config": {
        "//host": "127.0.0.1",
        "//user": "root",
        "//password": "your_password",
        "//database": "mytimelogger",
        "//port": 3306
    }
}

# --- 配置文件加载/创建函数 ---
# ==============================================================================
# 全局日志配置 (按日轮转)
# ==============================================================================
def setup_logging():
    """初始化日志系统，支持控制台和文件同步输出"""
    # 获取程序运行目录，确保日志留在本地
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    log_dir = os.path.join(base_dir, "log")
    
    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # 定义日志文件名
        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
        
        # 配置根记录器
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # 防止重复添加 Handler
        if not logger.handlers:
            # 终端处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(console_handler)
            
            # 文件处理器 (按天轮转，保留最近 30 天)
            file_handler = TimedRotatingFileHandler(
                log_file, when="midnight", interval=1, backupCount=30, encoding='utf-8'
            )
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)
            
        logging.info("MyTimeLogger 日志系统初始化完成。")
    except Exception as e:
        # 这里还不能使用 logging，因为 logging 可能还没初始化成功
        print(f"日志初始化失败: {e}")

setup_logging()

def load_or_create_config():
    config_path = resource_path('config.json')
    if not os.path.exists(config_path):
        logging.info("未找到 config.json, 正在创建默认配置文件...")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            return DEFAULT_CONFIG
        except Exception as e:
            logging.error(f"创建默认配置文件失败: {e}")
            return DEFAULT_CONFIG

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            updated = False
            
            if "hotkeys" in user_config:
                hk = user_config["hotkeys"]
                if "start_resume" in hk and "start" not in hk:
                    hk["start"] = hk.pop("start_resume")
                    updated = True
                if "pause" in hk and "toggle_pause" not in hk:
                    hk["toggle_pause"] = hk.pop("pause")
                    updated = True
                for k, v in DEFAULT_CONFIG["hotkeys"].items():
                    if k not in hk:
                        hk[k] = v
                        updated = True

            for key, value in DEFAULT_CONFIG.items():
                if key not in user_config:
                    user_config[key] = value
                    updated = True
                elif isinstance(value, dict) and isinstance(user_config.get(key), dict):
                    # 只有当用户配置中完全缺失该子项时才补充，避免覆盖用户的现有字段
                    for sub_k, sub_v in value.items():
                        # 对于 mysql_config 这种特殊的带注释字段，如果用户已经有了非注释版本，不要再加默认注释版本
                        clean_sub_k = sub_k.lstrip("/")
                        user_has_keys = [k.lstrip("/") for k in user_config[key].keys()]
                        if clean_sub_k not in user_has_keys:
                            user_config[key][sub_k] = sub_v
                            updated = True
            if updated:
                logging.info("配置文件已更新，添加了新字段。")
                save_config(user_config)
            return user_config
    except (json.JSONDecodeError, TypeError) as e:
        QMessageBox.warning(None, "配置解析错误", f"读取 config.json 失败（很可能是您修改时的格式有误，如漏掉引号或逗号）:\n{e}\n\n程序已自动暂时重置为默认配置。")
        return DEFAULT_CONFIG

# --- 配置文件保存函数 ---
def save_config(config_data):
    config_path = resource_path('config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"保存配置文件失败: {e}")

# ==============================================================================
# 异步数据库工作者 (Worker Thread)
# ==============================================================================
class DatabaseWorker(QObject):
    """专门处理异步任务的 Worker，包括 MySQL 同步和耗时计算"""
    logged = pyqtSignal()
    stats_ready = pyqtSignal(list, bool)
    error_occurred = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        # 创建一个专门用于远程备份的 Logger 实例 (强制为 mysql 模式)
        self.mysql_cfg = copy.deepcopy(config)
        self.mysql_cfg["db_type"] = "mysql"
        self.backup_logger = StudyLogger(self.mysql_cfg)

    def init_db(self):
        """后台异步初始化远程数据库备份"""
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
        """直接从本地读取统计数据 (快)"""
        try:
            # 统计读取始终固定为本地 sqlite，确保速度
            local_cfg = copy.deepcopy(self.config)
            local_cfg["db_type"] = "sqlite"
            local_logger = StudyLogger(local_cfg)
            rows = local_logger.get_all_sessions()
            self.stats_ready.emit(rows, open_browser)
        except Exception as e:
            self.error_occurred.emit(str(e))

# ==============================================================================
# 学习日志记录器 (底层存储)
# ==============================================================================
class StudyLogger:
    def __init__(self, config=None):
        self.config = config if config else DEFAULT_CONFIG
        self.db_type = self.config.get("db_type", "sqlite")
        self.log_path = resource_path("study_log.db")
        self._conn = None 
        # 本地 SQLite 初始化在构造时完成 (毫秒级)
        if self.db_type == "sqlite":
            self._initialize_db()
            self._migrate_from_json()
        # MySQL 的初始化由 DatabaseWorker 异步处理，不在构造函数进行

    def _get_connection(self):
        """根据配置获取数据库连接 (MySQL 模式下支持连接复用)"""
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
        """初始化数据库表结构 (采用 IF NOT EXISTS 确保数据非破坏性)"""
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
                        session_summary TEXT COMMENT '专注总结内容'
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
                        session_summary TEXT
                    )
                ''')
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"数据库初始化失败: {e}")

    def _migrate_from_json(self):
        """如果存在旧的 JSON 日志，则迁移数据到 SQLite"""
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

    def log_session(self, start_time: datetime, end_time: datetime, net_duration_seconds: int, pause_count: int = 0, pause_reasons: str = "", session_summary: str = ""):
        """记录一个完整的学习会话到数据库"""
        if not all([start_time, end_time, net_duration_seconds > 0]):
            return

        date_str = start_time.strftime('%Y-%m-%d')
        day_of_week = start_time.strftime('%A')
        net_duration_minutes = round(net_duration_seconds / 60, 2)

        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # 处理时间格式适配
            start_fmt = start_time.strftime('%Y-%m-%d %H:%M:%S')
            end_fmt = end_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # SQL 参数化在 sqlite3 和 pymysql 中略有不同 (Python DB-API 通常支持 %s 或 ?)
            # sqlite3 使用 ?, pymysql 使用 %s
            placeholder = "%s" if self.db_type == "mysql" else "?"
            
            sql = f'''
                INSERT INTO study_sessions 
                (start_time, end_time, net_duration_minutes, date, day_of_week, pause_count, pause_reasons, session_summary)
                VALUES ({", ".join([placeholder]*8)})
            '''
            
            cursor.execute(sql, (
                start_fmt, end_fmt, net_duration_minutes,
                date_str, day_of_week, pause_count,
                pause_reasons, session_summary
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"记录学习会话失败: {e}")

    def get_all_sessions(self):
        """从数据库读取所有会话记录"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT start_time, end_time, net_duration_minutes, date, day_of_week, 
                       pause_count, pause_reasons, session_summary 
                FROM study_sessions
                ORDER BY start_time ASC
            ''')
            rows = cursor.fetchall()
            conn.close()
            # 统一转为列表格式，处理 MySQL 结果通常是元组的问题
            return [list(map(str, row)) for row in rows]
        except Exception as e:
            logging.error(f"读取数据库失败: {e}")
            return []


# ==============================================================================
# Markdown 输入对话框 (Typora-like Live rendering)
# ==============================================================================
class MarkdownTextEdit(QTextEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptRichText(True)
        self.setPlaceholderText("")
        self.document().setDocumentMargin(0) # 彻底归零文档边距

    def keyPressEvent(self, event):
        cursor = self.textCursor()
        
        # 处理空格键：触发列表转换
        if event.key() == Qt.Key.Key_Space:
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            line_text = cursor.selectedText()
            cursor.clearSelection()

            # 无序列表 (- , + , * )
            if line_text in ["-", "+", "*"]:
                cursor.beginEditBlock()
                # 删除输入的符号
                for _ in range(len(line_text)): 
                    cursor.deletePreviousChar()
                # 插入真正的列表
                list_format = QTextListFormat()
                list_format.setStyle(QTextListFormat.Style.ListDisc)
                list_format.setIndent(1) # 设置最小缩进
                cursor.createList(list_format)
                cursor.endEditBlock()
                return

            # 有序列表 (1. )
            elif line_text == "1.":
                cursor.beginEditBlock()
                for _ in range(2): cursor.deletePreviousChar()
                list_format = QTextListFormat()
                list_format.setStyle(QTextListFormat.Style.ListDecimal)
                list_format.setIndent(1) # 设置最小缩进
                cursor.createList(list_format)
                cursor.endEditBlock()
                return

        # 处理回车键：列表项自动续行 (QTextEdit 默认支持列表回车续行)
        # 新增: 处理 Ctrl+Enter 快捷提交
        if event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # 寻找所属对话框并触发 accept
                parent_dialog = self.window()
                if isinstance(parent_dialog, QDialog):
                    parent_dialog.accept()
                    return

        super().keyPressEvent(event)

class MarkdownInputDialog(QDialog):
    def __init__(self, title, label, parent=None, initial_text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 350)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        
        layout = QVBoxLayout(self)
        
        self.label = QLabel(label)
        self.label.setStyleSheet("font-weight: bold; color: #88C0D0; margin-bottom: 5px;")
        layout.addWidget(self.label)
        
        self.text_edit = MarkdownTextEdit()
        # 恢复正常的视图边距，防止截断
        self.text_edit.setViewportMargins(0, 0, 0, 0)
        self.text_edit.document().setDocumentMargin(5)
        
        # 默认起始列表符号为 "+"
        display_text = initial_text if initial_text else "+ "
        self.text_edit.setMarkdown(display_text)
        
        # 确保光标在文本末尾
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)
        
        layout.addWidget(self.text_edit)
        
        # 手动创建按钮布局以精确控制顺序：Cancel 在左，OK 在右
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self.reject)
        
        self.ok_btn = QPushButton("OK")
        self.ok_btn.setFixedWidth(80)
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)
        
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background-color: #2E3440; }
            QLabel { color: #ECEFF4; font-size: 14px; }
            QTextEdit { 
                background-color: #3B4252; 
                color: #ECEFF4; 
                border: 1px solid #4C566A; 
                border-radius: 4px;
                padding: 10px 10px 10px 5px; /* 留 5px 防止由于太靠左而显得被截断 */
                margin: 0px;
                font-size: 14px;
                selection-background-color: #88C0D0;
            }
            QPushButton { 
                background-color: #4C566A; 
                color: #ECEFF4; 
                border-radius: 4px; 
                padding: 6px 15px;
            }
            QPushButton:hover { background-color: #5E81AC; }
        """)

    def textValue(self):
        # 导出为 Markdown 格式字符串
        return self.text_edit.toMarkdown()

# ==============================================================================
# 核心逻辑层 (已修改)
# ==============================================================================
class MyTimeLoggerLogic(QObject):
    state_changed = pyqtSignal(str, str)
    time_updated = pyqtSignal(int)
    notification_requested = pyqtSignal(str, str)
    input_reason_requested = pyqtSignal()
    input_summary_requested = pyqtSignal()
    session_logged = pyqtSignal()
    
    # 定义信号 (必须在类级别定义)
    _async_log_trigger = pyqtSignal(dict)
    _sync_trigger = pyqtSignal(dict) # 新增：远程同步专用

    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # 核心逻辑：UI 始终直连本地 SQLite，确保存取在毫秒级完成
        local_cfg = copy.deepcopy(config)
        local_cfg["db_type"] = "sqlite"
        self.local_logger = StudyLogger(local_cfg)
        
        # 初始化异步 Worker (负责处理 MySQL 同步/备份)
        self.db_thread = QThread()
        self.db_worker = DatabaseWorker(self.config)
        self.db_worker.moveToThread(self.db_thread)
        
        # 连接同步逻辑：由 Logic 触发镜像备份
        self._sync_trigger.connect(self.db_worker.sync_to_backup)
        
        self.db_thread.start()
        # 100ms 后后台开始镜像初始化
        QTimer.singleShot(100, self.db_worker.init_db)

        # 2. 内存状态初始化
        self.is_paused = False
        self.time_remaining_on_pause = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timer_timeout)

        # 3. 极速启动核心：音频加载延后到 2s，彻底避开启动主进程峰值
        self._audio_initialized = False
        QTimer.singleShot(2000, self._async_init_audio)
        
        self.total_study_time = self.config.get("total_study_time", 0)

        # 用于触发长休息的当前周期学习时长
        self.current_cycle_study_time = 0

        # 大专注状态
        self.large_session_start_time = None
        self.large_session_pause_count = 0
        self.large_session_pause_reasons = []
        self.large_session_net_duration = 0
        
        self.current_pause_start_time = None
        self.pending_pause_reason = "无"
        
        # 临时记录
        self.current_session_start_time = None
        self.current_session_duration = 0
        
        self.reset_cycle()

    def _clear_large_session(self):
        self.large_session_start_time = None
        self.large_session_pause_count = 0
        self.large_session_pause_reasons = []
        self.large_session_net_duration = 0
        self.current_pause_start_time = None
        self.pending_pause_reason = "无"

    def _clear_current_session(self):
        """清空当前会话的临时记录"""
        self.current_session_start_time = None
        self.current_session_duration = 0

    def reset_cycle(self):
        self.timer.stop()
        self.cycle_count = 0
        self.current_state = "stopped"
        self.is_paused = False
        self._clear_current_session()
        self._clear_large_session()
        self.current_cycle_study_time = 0
        self.state_changed.emit("沉浸式学习\n右键单击开始", self.current_state)
        self.time_updated.emit(self.total_study_time)

    def reset_all(self):
        self.total_study_time = 0
        self.reset_cycle() # reset_cycle 会调用 clear_session
        self.time_updated.emit(self.total_study_time)
        # 注意: 此处不清除日志文件，用户应手动管理

    def on_timer_timeout(self):
        if self.current_state == "studying":
            study_duration = self.timer.property("duration")
            self.total_study_time += study_duration
            self.current_cycle_study_time += study_duration
            self.large_session_net_duration += study_duration
            self._clear_current_session()

            if self.current_cycle_study_time >= self.config["long_break_threshold"]:
                self._play_sound("victory")
                self.input_summary_requested.emit()
            else:
                self._run_short_break_cycle()

        elif self.current_state == "short_breaking":
            self._run_study_cycle()
            
        elif self.current_state == "long_breaking":
            self._finish_long_break()

    def _finish_long_break(self):
        """结束长休息的共用逻辑"""
        self.timer.stop()
        self._play_sound("end_long_break")
        self.current_state = "long_break_finished"
        self.state_changed.emit("🎉 长休息结束\n右键开始新征程", self.current_state)
        self.notification_requested.emit("长休息结束", "精力恢复！可以开始下一轮学习了。")

    def end_break_now(self):
        """手动结束当前休息（短休息或长休息）"""
        if self.current_state == "short_breaking":
            self.timer.stop()
            self._run_study_cycle()
        elif self.current_state == "long_breaking":
            self._finish_long_break()

    def commit_large_session(self, summary):
        if self.large_session_start_time and self.large_session_net_duration > 0:
            end_time = datetime.now()
            pause_reasons_str = "; ".join(self.large_session_pause_reasons) if self.large_session_pause_reasons else "无"
            
            # 使用包装好的字典同步数据
            log_data = {
                "start_time": self.large_session_start_time,
                "end_time": end_time,
                "net_duration_seconds": self.large_session_net_duration,
                "pause_count": self.large_session_pause_count,
                "pause_reasons": pause_reasons_str,
                "session_summary": summary if summary else "无总结"
            }
            
            # 第一步：极其迅速地存入本地 SQLite (主线程操作，毫秒级，保证数据不丢)
            self.local_logger.log_session(**log_data)
            
            # 第二步：发送信号让后台镜像同步到远程 MySQL
            self._sync_trigger.emit(log_data)
            
            logging.info(f"大专注会话已提交! 纯时长: {self.large_session_net_duration}s, 暂停: {self.large_session_pause_count}次, 摘要: {summary[:50]}...")
            self.session_logged.emit()
            
        self._clear_large_session()
        self._run_long_break_cycle()
        
    def add_pause_reason(self, reason):
        if reason:
            self.pending_pause_reason = reason
            logging.info(f"记录暂停原因: {reason}")
        else:
            self.pending_pause_reason = "无"

    def _run_study_cycle(self):
        self.cycle_count += 1
        self.current_state = "studying"
        study_duration = random.randint(self.config["study_time_min"], self.config["study_time_max"])
        
        if self.current_cycle_study_time == 0:
            self.large_session_start_time = datetime.now()
            self.large_session_pause_count = 0
            self.large_session_pause_reasons = []
            self.large_session_net_duration = 0
            
        self.current_session_start_time = datetime.now()
        self.current_session_duration = study_duration

        self.state_changed.emit(f"📚 学习中...\n(第 {self.cycle_count} 轮)", self.current_state)
        logging.info(f"开始第 {self.cycle_count} 轮学习。预设时长: {study_duration}s")
        # 仅在非第一次开始时（如短休息结束）播放声音
        if self.current_cycle_study_time > 0:
            self._play_sound("start_study")
        self.timer.setProperty("duration", study_duration)
        self.timer.start(study_duration * 1000)

    # --- 以下方法基本不变 ---
    def load_persistent_time(self, total_study_time):
        self.total_study_time = total_study_time
        self.time_updated.emit(self.total_study_time)

    def _validate_and_get_sound_paths(self):
        folder_path = resource_path(self.config["music_folder"])
        if not os.path.isdir(folder_path): raise FileNotFoundError(f"资源文件夹未找到: {folder_path}")
        paths = {}
        for key, filename in self.config["sound_files"].items():
            path = os.path.join(folder_path, filename)
            if not os.path.isfile(path): raise FileNotFoundError(f"音频文件未找到: {path}")
            paths[key] = path
        return paths

    def _async_init_audio(self):
        """异步初始化音频，防止阻塞启动"""
        try:
            pygame.mixer.init()
            self.sound_paths = self._validate_and_get_sound_paths()
            self._audio_initialized = True
        except Exception as e:
            logging.error(f"音频初始化失败: {e}")

    def _play_sound(self, sound_key):
        if not self._audio_initialized: return
        sound_path = self.sound_paths.get(sound_key)
        if not sound_path: return
        try:
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
        except pygame.error as e:
            logging.error(f"播放音频时出错: {e}")

    def start_only(self):
        if self.current_state in ["stopped", "long_break_finished"]:
            self.is_paused = False
            if self.current_state == "long_break_finished": self.reset_cycle()
            if self.current_cycle_study_time >= self.config["long_break_threshold"]:
                self._run_long_break_cycle()
            else:
                self._run_study_cycle()

    def toggle_pause(self):
        if self.is_paused:
            self._resume()
        elif self.timer.isActive():
            self.pause()
            if self.current_state == "studying":
                self.input_reason_requested.emit()

    def start_or_resume(self):
        self.start_only()

    def _run_short_break_cycle(self):
        self.current_state = "short_breaking"
        break_duration = self.config["short_break_duration"]
        self.state_changed.emit("☕ 短暂休息中...", self.current_state)
        self.time_updated.emit(self.total_study_time)
        self._play_sound("start_short_break")
        self.timer.setProperty("duration", 0)
        self.timer.start(break_duration * 1000)

    def _run_long_break_cycle(self):
        self.current_state = "long_breaking"
        break_duration = self.config["long_break_duration"]
        self.state_changed.emit("🧘 长时间休息...", self.current_state)
        self.time_updated.emit(self.total_study_time)
        self._play_sound("start_long_break")
        # 一旦开始长休息，就清零周期计时器
        # 这样，长休息结束后，下一个周期会从0开始计算
        self.current_cycle_study_time = 0
        self.timer.setProperty("duration", 0)
        self.timer.start(break_duration * 1000)
    
    def pause(self):
        if self.timer.isActive():
            self.time_remaining_on_pause = self.timer.remainingTime()
            self.timer.stop()
            self.is_paused = True
            self.current_pause_start_time = datetime.now()
            logging.info(f"计时器已暂停。状态: {self.current_state}")
            self.state_changed.emit("⏸️ 已暂停", self.current_state)

    @staticmethod
    def _format_pause_duration(pause_sec):
        """将秒数格式化为人类可读的时长字符串"""
        if pause_sec < 60:
            return f"{pause_sec}秒"
        elif pause_sec < 3600:
            m, s = divmod(pause_sec, 60)
            return f"{m}分{s}秒" if s else f"{m}分"
        else:
            h, rem = divmod(pause_sec, 3600)
            m, s = divmod(rem, 60)
            parts = f"{h}时{m}分" if m else f"{h}时"
            if s:
                parts += f"{s}秒"
            return parts

    def _resume(self):
        if self.is_paused:
            self.timer.start(self.time_remaining_on_pause)
            self.is_paused = False
            
            if self.current_pause_start_time:
                pause_sec = int((datetime.now() - self.current_pause_start_time).total_seconds())
                self.large_session_pause_count += 1
                duration_str = self._format_pause_duration(pause_sec)
                reason_str = f"{self.pending_pause_reason} ({duration_str})"
                self.large_session_pause_reasons.append(reason_str)
                logging.info(f"计时器已恢复。暂停时长: {duration_str}, 原因: {self.pending_pause_reason}")
                self.current_pause_start_time = None
                self.pending_pause_reason = "无"
                
            original_state_text = {
                "studying": f"📚 学习中...\n(第 {self.cycle_count} 轮)",
                "short_breaking": "☕ 短暂休息中...",
                "long_breaking": "🧘 长时间休息..."
            }.get(self.current_state, "未知状态")
            self.state_changed.emit(original_state_text, self.current_state)

    def stop(self):
        self.timer.stop()
        pygame.mixer.quit()

# ==============================================================================
# 快捷键管理器 (无变化)
# ==============================================================================
class HotkeyManager(QObject):
    start_triggered = pyqtSignal()
    toggle_pause_triggered = pyqtSignal()
    reset_cycle_triggered = pyqtSignal()

    def __init__(self, hotkey_config, parent=None):
        super().__init__(parent)
        if not keyboard:
            logging.warning("HotkeyManager: pynput 未安装，全局快捷键功能已禁用。")
            self.listener = None
            return

        self.hotkey_config = hotkey_config
        self.listener = None
        self.hotkey_map = {
            'start': self.start_triggered.emit,
            'toggle_pause': self.toggle_pause_triggered.emit,
            'reset_cycle': self.reset_cycle_triggered.emit,
        }

    def start(self):
        if not self.listener:
            try:
                pynput_map = {
                    self.hotkey_config[action]: callback
                    for action, callback in self.hotkey_map.items()
                    if action in self.hotkey_config and self.hotkey_config[action]
                }
                if not pynput_map:
                    print("未配置任何有效的快捷键。")
                    return
                
                self.listener = keyboard.GlobalHotKeys(pynput_map)
                self.listener.start()
                print(f"快捷键监听器已启动: {pynput_map.keys()}")
            except Exception as e:
                print(f"启动快捷键监听器失败: {e}. 请检查 config.json 中的快捷键格式。")
                self.listener = None

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
            print("快捷键监听器已停止。")

# ==============================================================================
# 图形界面层 (已修改)
# ==============================================================================
class MyTimeLoggerGUI(QWidget):
    def __init__(self, config):
        super().__init__()
        
        self.config = config
        
        try:
            self.logic = MyTimeLoggerLogic(self.config)
        except FileNotFoundError as e:
            QMessageBox.critical(None, "资源错误", f"{e}\n\n请确保所有资源文件都在正确的位置，然后重启程序。")
            self._init_failed = True
            return
        self._init_failed = False
        self.setWindowTitle("MyTimeLogger")
        self.setWindowIcon(QIcon(resource_path(os.path.join("document", "icon.ico"))))
        
        self.dragPos = None
        self.is_locked = False
        
        self.settings = QSettings("MyTimeLogger", "App")
        
        self.is_always_on_top = self.settings.value("ui/alwaysOnTop", True, type=bool)
        self.is_mini_mode = self.settings.value("ui/isMiniMode", False, type=bool)

        self.create_tray_icon()
        
        self.hotkey_manager = HotkeyManager(self.config.get('hotkeys', {}))
        self.hotkey_manager.start_triggered.connect(self.logic.start_only)
        self.hotkey_manager.toggle_pause_triggered.connect(self.logic.toggle_pause)
        self.hotkey_manager.reset_cycle_triggered.connect(self.logic.reset_cycle)
        # 延迟启动热键监听，优先级调低
        QTimer.singleShot(1000, self.hotkey_manager.start)

        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self.update_countdown_display)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint if self.is_always_on_top else Qt.WindowType.Widget
        )
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.background_widget = QWidget(self)
        self.background_widget.setObjectName("background")

        # 布局切换按钮 (放置在 background_widget 上面，绝对定位或通过布局)
        self.mini_toggle_btn = QPushButton(self.background_widget)
        self.mini_toggle_btn.setFixedSize(20, 20)
        self.mini_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mini_toggle_btn.clicked.connect(self.toggle_mini_mode)
        self.mini_toggle_btn.setStyleSheet("QPushButton { background: transparent; color: #88C0D0; border: none; font-size: 14px; } QPushButton:hover { color: #A3BE8C; }")

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(False) # 迷你模式不需要换行
        
        self.total_time_label = QLabel()
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_time_label.setObjectName("total_time_label")
        
        self.rebuild_layout()


        # 移除旧的 grip_layout 逻辑
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.background_widget)

        self.load_settings()
        self.update_stylesheet()

        # 绑定异步数据库回调
        self.logic.db_worker.stats_ready.connect(self._on_stats_ready)
        self.logic.db_worker.error_occurred.connect(self._on_db_error)

        self.logic.state_changed.connect(self.update_status)
        self.logic.time_updated.connect(self.update_total_time)
        self.logic.notification_requested.connect(self.show_notification)
        self.logic.input_reason_requested.connect(self.prompt_for_pause_reason)
        self.logic.input_summary_requested.connect(self.prompt_for_session_summary)
        self.logic.session_logged.connect(self.generate_statistics_html)

        # 结束休息按钮
        self._build_end_break_button()
        
        self.generate_statistics_html()
        
        self.logic.reset_cycle()

    def show_notification(self, title, message):
        self.tray.showMessage(title, message, self.tray_icon, 5000)

    @staticmethod
    def _force_foreground(hwnd):
        """Windows 下强制将窗口设为前台"""
        if sys.platform == 'win32':
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetForegroundWindow(hwnd)
            except Exception:
                pass

    def _activate_dialog(self, dialog):
        """确保弹窗获得前台焦点（Windows 下用 AttachThreadInput 组合拳）"""
        dialog.activateWindow()
        dialog.raise_()
        if sys.platform == 'win32':
            try:
                import ctypes
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                hwnd = int(dialog.winId())
                foreground_hwnd = user32.GetForegroundWindow()
                foreground_tid = user32.GetWindowThreadProcessId(foreground_hwnd, None)
                current_tid = kernel32.GetCurrentThreadId()
                if foreground_tid != current_tid:
                    user32.AttachThreadInput(current_tid, foreground_tid, True)
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
                if foreground_tid != current_tid:
                    user32.AttachThreadInput(current_tid, foreground_tid, False)
            except Exception:
                pass

    def prompt_for_pause_reason(self):
        dialog = MarkdownInputDialog("暂停提醒", "请输入本次暂停的原因（支持 markdown 语法）：", self)
        QTimer.singleShot(100, lambda: self._activate_dialog(dialog))
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            reason = dialog.textValue()
            self.logic.add_pause_reason(reason.strip() if reason.strip() else "无")
        else:
            self.logic.add_pause_reason("无")

    def prompt_for_session_summary(self):
        dialog = MarkdownInputDialog("大专注完成！", "恭喜完成一段深度专注！请总结你做了哪些事（支持 markdown 语法）：", self)
        QTimer.singleShot(100, lambda: self._activate_dialog(dialog))

        if dialog.exec() == QDialog.DialogCode.Accepted:
            summary = dialog.textValue()
            final_summary = summary.strip() if summary.strip() else "未填写总结"
            self.logic.commit_large_session(final_summary)
        else:
            self.logic.commit_large_session("未填写总结")

    def toggle_mini_mode(self):
        self.is_mini_mode = not self.is_mini_mode
        self.settings.setValue("ui/isMiniMode", self.is_mini_mode)
        self.rebuild_layout()
        self.update_stylesheet()

    def rebuild_layout(self):
        # 清现有的 layout
        if self.background_widget.layout():
            # 彻底清理旧布局中的内容映射
            old_layout = self.background_widget.layout()
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget() and item.widget() not in [self.status_label, self.total_time_label, self.end_break_btn, self.mini_toggle_btn]:
                    item.widget().deleteLater()
            from PyQt6 import sip
            sip.delete(old_layout)

        if self.is_mini_mode:
            self.setFixedSize(280, 40)
            self.background_widget.setFixedSize(280, 40)
            self.status_label.setWordWrap(False)
            new_layout = QHBoxLayout(self.background_widget)
            new_layout.setContentsMargins(10, 0, 10, 0)
            new_layout.setSpacing(10)
            
            new_layout.addWidget(self.mini_toggle_btn)
            new_layout.addWidget(self.status_label)
            new_layout.addWidget(self.total_time_label)
            
            self.mini_toggle_btn.setIcon(QIcon(resource_path(os.path.join('document', 'expand.svg'))))
            self.mini_toggle_btn.setIconSize(QSize(16, 16))
        else:
            self.setFixedSize(220, 140)
            self.background_widget.setFixedSize(220, 140)
            self.status_label.setWordWrap(True)
            new_layout = QVBoxLayout(self.background_widget)
            new_layout.setContentsMargins(10, 5, 10, 10)
            new_layout.setSpacing(2)
            
            top_row = QHBoxLayout()
            top_row.addStretch()
            top_row.addWidget(self.mini_toggle_btn)
            new_layout.addLayout(top_row)
            
            new_layout.addWidget(self.status_label, 0, Qt.AlignmentFlag.AlignCenter)
            new_layout.addWidget(self.total_time_label, 0, Qt.AlignmentFlag.AlignCenter)
            new_layout.addStretch()
            
            self.mini_toggle_btn.setIcon(QIcon(resource_path(os.path.join('document', 'shrink.svg'))))
            self.mini_toggle_btn.setIconSize(QSize(16, 16))
        
        # 重新插入结束休息按钮（如果已创建）
        if hasattr(self, 'end_break_btn'):
            new_layout.addWidget(self.end_break_btn, 0, Qt.AlignmentFlag.AlignCenter)
            if self.is_mini_mode:
                self.end_break_btn.setFixedSize(75, 20)
                self.end_break_btn.setStyleSheet(self.end_break_btn.styleSheet().replace("font-size: 12px;", "font-size: 10px;").replace("font-size: 13px;", "font-size: 10px;"))
            else:
                self.end_break_btn.setFixedSize(120, 30)
                curr_style = self.end_break_btn.styleSheet()
                if "font-size: 10px;" in curr_style:
                    self.end_break_btn.setStyleSheet(curr_style.replace("font-size: 10px;", "font-size: 12px;"))

    # --- NEW: 打开日志文件夹的方法 ---
    def open_log_folder(self):
        log_dir = resource_path(".") # 获取日志文件所在的目录
        try:
            # 跨平台方式打开文件夹
            if sys.platform == 'win32':
                os.startfile(log_dir)
            elif sys.platform == 'darwin': # macOS
                os.system(f'open "{log_dir}"')
            else: # Linux
                os.system(f'xdg-open "{log_dir}"')
        except Exception as e:
            print(f"无法打开文件夹: {e}")
            QMessageBox.warning(self, "操作失败", f"无法自动打开文件夹。\n请手动前往: {log_dir}")

    def confirm_and_reset_all(self):
        reply = QMessageBox.question(
            self,
            '安全提示',
            "您确定要彻底清空所有学习记录和由于此产生的报表吗？此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            pwd, ok = QInputDialog.getText(self, "高危操作鉴权", "请输入授权密码：", QLineEdit.EchoMode.Password)
            
            correct_pwd = "111"
            try:
                with open(resource_path('config.json'), 'r', encoding='utf-8') as f:
                    correct_pwd = json.load(f).get("reset_password", "111")
            except Exception:
                correct_pwd = self.config.get("reset_password", "111")
                
            if ok and pwd == correct_pwd:
                self.logic.reset_all()
                log_path = self.logic.logger.log_path
                if os.path.exists(log_path):
                    try:
                        # 彻底清空数据库
                        conn = sqlite3.connect(log_path)
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM study_sessions")
                        conn.commit()
                        conn.close()
                        # 也可选择删除文件以便重新初始化逻辑能跑通
                        os.remove(log_path)
                    except Exception as e:
                        print(f"清理数据库失败: {e}")
                self.logic.logger._initialize_db()
                self.generate_statistics_html()
                QMessageBox.information(self, "清理成功", "所有记录及统计报表已彻底清空。")
            elif ok:
                QMessageBox.warning(self, "密码错误", "密码不正确，操作已取消。")

    def populate_context_menu(self, menu: QMenu):
        menu.clear()
        menu.setStyleSheet("""
            QMenu { background-color: #3B4252; border: 1px solid #4C566A; }
            QMenu::item { padding: 8px 20px; color: #ECEFF4; }
            QMenu::item:selected { background-color: #5E81AC; }
            QMenu::item:disabled { color: #4C566A; }
            QMenu::separator { height: 1px; background: #4C566A; margin: 4px 0; }
        """)
        
        hotkey_config = self.config.get('hotkeys', {})

        if self.logic.timer.isActive() or self.logic.is_paused:
            remaining_ms = self.logic.time_remaining_on_pause if self.logic.is_paused else self.logic.timer.remainingTime()
            mins, secs = divmod(remaining_ms // 1000, 60)
            status_text = f"⏳ {self.logic.current_state.replace('_', ' ')}: {int(mins)}m {int(secs)}s"
            info_action = QAction(status_text, self); info_action.setDisabled(True)
            menu.addAction(info_action)
            # menu.addSeparator()
        # 新增: 显示距离长休息的剩余时间
        # 仅在计时器未停止时显示此信息
        if self.logic.current_state != 'stopped':
            long_break_threshold = self.config.get("long_break_threshold", 90 * 60)
            current_study_time = self.logic.total_study_time
            
            # 如果还没到长休息时间
            if current_study_time < long_break_threshold:
                remaining_seconds = long_break_threshold - current_study_time
                mins, secs = divmod(remaining_seconds, 60)
                # 在学习状态时，额外加上当前轮次剩余的时间
                if self.logic.current_state == "studying" and self.logic.timer.isActive():
                    timer_remaining_secs = self.logic.timer.remainingTime() // 1000
                    remaining_seconds -= timer_remaining_secs
                    mins, secs = divmod(remaining_seconds, 60)

                long_break_status_text = f"🎯 距长休息约: {int(mins)}分"
            else:
                # 如果已经达到或超过长休息时间
                long_break_status_text = "🎉 已可进入长休息"

            long_break_action = QAction(long_break_status_text, self)
            long_break_action.setDisabled(True) # 设为禁用，仅作为信息展示
            menu.addAction(long_break_action)
        menu.addSeparator()

        is_running = self.logic.timer.isActive()
        is_paused = self.logic.is_paused

        start_hotkey = hotkey_config.get('start', '')
        start_text = "▶️ 开 始" + (f"  ({start_hotkey})" if start_hotkey else "")
        start_action = QAction(start_text, self)
        start_action.triggered.connect(self.logic.start_only)
        if is_running or is_paused: start_action.setDisabled(True)
        
        pause_hotkey = hotkey_config.get('toggle_pause', '')
        pause_text = "⏯️ 暂停 / 继续" + (f"  ({pause_hotkey})" if pause_hotkey else "")
        pause_action = QAction(pause_text, self)
        pause_action.triggered.connect(self.logic.toggle_pause)
        if not is_running and not is_paused: pause_action.setDisabled(True)

        lock_text = "🔓 解锁 (可交互)" if self.is_locked else "🔒 锁定 (鼠标穿透)"
        lock_action = QAction(lock_text, self); lock_action.triggered.connect(self.toggle_mouse_penetration)
        
        always_on_top_text = f"{'✅' if self.is_always_on_top else '🔲'} 总在最前"
        always_on_top_action = QAction(always_on_top_text, self); always_on_top_action.triggered.connect(self.toggle_always_on_top)

        # --- NEW: Configuration Menus ---
        config_menu = QMenu("⚙️ 设置", self)
        
        hotkey_menu = QMenu("快捷键设置", self)
        set_start_action = QAction(f"设置开始键 (当前: {self.config.get('hotkeys', {}).get('start', '<alt>+z')})", self)
        set_start_action.triggered.connect(lambda: self.configure_hotkey('start', '开始键'))
        set_pause_action = QAction(f"设置暂停/恢复键 (当前: {self.config.get('hotkeys', {}).get('toggle_pause', '<alt>+c')})", self)
        set_pause_action.triggered.connect(lambda: self.configure_hotkey('toggle_pause', '暂停/恢复键'))
        hotkey_menu.addAction(set_start_action)
        hotkey_menu.addAction(set_pause_action)
        
        interval_menu = QMenu("随机休息间隔", self)
        intervals = [("30秒 (测试)", 0.5, 0.5), ("3~5 分钟", 3, 5), ("5~7 分钟", 5, 7), ("6~9 分钟", 6, 9)]
        for label, min_m, max_m in intervals:
            action = QAction(label, self)
            action.setCheckable(True)
            if self.config.get("study_time_min", 5*60) == int(min_m * 60) and self.config.get("study_time_max", 7*60) == int(max_m * 60):
                action.setChecked(True)
            action.triggered.connect(lambda checked, mn=min_m, mx=max_m: self.set_interval_config(mn, mx))
            interval_menu.addAction(action)
            
        duration_menu = QMenu("大专注时长", self)
        durations = [("1 分钟 (测试)", 1), ("30 分钟", 30), ("60 分钟", 60), ("90 分钟", 90), ("120 分钟", 120)]
        for label, mins in durations:
            action = QAction(label, self)
            action.setCheckable(True)
            if self.config.get("long_break_threshold", 90*60) == mins * 60:
                action.setChecked(True)
            action.triggered.connect(lambda checked, m=mins: self.set_duration_config(m))
            duration_menu.addAction(action)
            
        db_menu = QMenu("数据库设置", self)
        sqlite_action = QAction("SQLite (当前本地)", self)
        sqlite_action.setCheckable(True)
        if self.config.get("db_type", "sqlite") == "sqlite": sqlite_action.setChecked(True)
        sqlite_action.triggered.connect(lambda: self.switch_database("sqlite"))
        
        mysql_action = QAction("MySQL (远程同步)", self)
        mysql_action.setCheckable(True)
        if self.config.get("db_type") == "mysql": mysql_action.setChecked(True)
        mysql_action.triggered.connect(lambda: self.switch_database("mysql"))
        
        db_menu.addAction(sqlite_action)
        db_menu.addAction(mysql_action)

        config_menu.addMenu(interval_menu)
        config_menu.addMenu(duration_menu)
        config_menu.addMenu(hotkey_menu)
        config_menu.addMenu(db_menu)

        opacity_menu = QMenu("💧 透明度", self)
        for val in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4,0.3,0.2,0.1,0.01]:
            op_action = QAction(f"{int(val*100)}%", self); op_action.triggered.connect(lambda _, v=val: self.set_opacity(v))
            opacity_menu.addAction(op_action)
            
        reset_menu = QMenu("🔄 重置", self)
        
        reset_cycle_hotkey = hotkey_config.get('reset_cycle', '')
        reset_cycle_text = "重置当前轮次" + (f"  ({reset_cycle_hotkey})" if reset_cycle_hotkey else "")
        reset_cycle_action = QAction(reset_cycle_text, self)
        reset_cycle_action.triggered.connect(self.logic.reset_cycle)
        
        clear_all_action = QAction("🗑️ 清空所有记录", self); clear_all_action.triggered.connect(self.confirm_and_reset_all)
        reset_menu.addAction(reset_cycle_action)
        reset_menu.addAction(clear_all_action)
        
        # --- NEW: "打开日志" 菜单项 ---
        open_log_action = QAction("📂 打开日志文件夹", self)
        open_log_action.triggered.connect(self.open_log_folder)
        
        stat_action = QAction("📊 查看统计 (网页版)", self)
        stat_action.triggered.connect(lambda: self.generate_statistics_html(open_browser=True))

        quit_action = QAction("❌ 退 出", self); quit_action.triggered.connect(self.close)

        menu.addAction(start_action)
        menu.addAction(pause_action)
        menu.addSeparator()
        menu.addAction(lock_action)
        menu.addAction(always_on_top_action)
        menu.addMenu(config_menu)
        menu.addMenu(opacity_menu)
        menu.addMenu(reset_menu)
        menu.addAction(open_log_action)
        menu.addAction(stat_action)
        menu.addSeparator()
        menu.addAction(quit_action)

    # --- 以下方法基本不变 ---
    def update_stylesheet(self):
        opacity = self.settings.value("ui/opacity", 0.8, type=float)
        border_style = "border: none;" if self.is_locked else "border: 1px solid #88C0D0;"
        
        # 根据模式动态调整字体
        label_font = 13 if self.is_mini_mode else 15
        total_time_font = 20 if self.is_mini_mode else 26
        
        self.background_widget.setStyleSheet(f"""
            #background {{ background-color: rgba(46, 52, 64, {opacity}); border-radius: 10px; {border_style} }}
            QLabel {{ background-color: transparent; color: #D8DEE9; font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif; font-size: {label_font}px; }}
            #total_time_label {{ font-size: {total_time_font}px; font-weight: bold; color: #00CED1; padding-top: 2px; letter-spacing: 1px; }}
        """)

    def _build_end_break_button(self):
        """创建结束休息按钮，初始隐藏"""
        self.end_break_btn = QPushButton("⏹ 结束休息", self.background_widget)
        self.end_break_btn.setObjectName("end_break_btn")
        self.end_break_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end_break_btn.setStyleSheet("""
            QPushButton#end_break_btn {
                background-color: #BF616A;
                color: #ECEFF4;
                border: none;
                border-radius: 6px;
                padding: 2px 10px;
                font-size: 12px;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-weight: bold;
            }
            QPushButton#end_break_btn:hover {
                background-color: #D08770;
            }
        """)
        self.end_break_btn.clicked.connect(self.logic.end_break_now)
        self.end_break_btn.hide()
        # 触发一次布局重绘以包含此按钮
        self.rebuild_layout()

    def _update_end_break_btn_visibility(self, state_name):
        """根据状态显隐结束休息按钮（仅长休息）"""
        if state_name == "long_breaking":
            self.end_break_btn.show()
        else:
            self.end_break_btn.hide()

    def update_status(self, status_text, state_name):
        self.current_state_text = status_text
        self._update_end_break_btn_visibility(state_name)
        if state_name not in ["stopped", "long_break_finished"]:
            self.countdown_timer.start()
            self.update_countdown_display()
        else:
            self.countdown_timer.stop()
            self.status_label.setText(status_text)
        self.update_stylesheet()
        
    def update_countdown_display(self):
        if self.logic.timer.isActive():
            remaining_ms = self.logic.timer.remainingTime()
            mins, secs = divmod(remaining_ms // 1000, 60)
            state = self.logic.current_state
            
            if state == "studying":
                session_elapsed = self.logic.current_session_duration - (remaining_ms // 1000)
                active_cycle_time = self.logic.current_cycle_study_time + session_elapsed
                self.update_total_time(active_cycle_time, realtime=True)
            
            if state == "long_breaking":
                self.status_label.setText(f"🧘 长休息\n{int(mins):02}:{int(secs):02}")
            elif state == "short_breaking":
                self.status_label.setText(f"☕ 短暂休息中...\n{int(mins):02}:{int(secs):02}")
            elif state == "studying":
                self.status_label.setText(f"📚 学习中...\n(第 {self.logic.cycle_count} 轮)")
            else:
                self.status_label.setText(f"{int(mins):02}:{int(secs):02}")
        elif self.logic.is_paused:
            self.status_label.setText("⏸️ 已暂停")

    def create_tray_icon(self):
        self.tray_icon = QIcon(resource_path(os.path.join('document', 'icon.ico')))
        self.tray = QSystemTrayIcon(self.tray_icon, self)
        self.tray.setToolTip("MyTimeLogger - 保持专注")
        self.tray_menu = QMenu(self)
        self.tray_menu.aboutToShow.connect(self.update_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show()
                self.activateWindow()
                self.raise_()

    def update_tray_menu(self):
        self.populate_context_menu(self.tray_menu)

    def contextMenuEvent(self, event):
        if self.is_locked: return
        context_menu = QMenu(self)
        self.populate_context_menu(context_menu)
        context_menu.exec(event.globalPos())

    def toggle_mouse_penetration(self):
        self.is_locked = not self.is_locked
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, self.is_locked)
        self.show()
        if not self.is_locked: self.activateWindow()
        self.update_stylesheet()

    def toggle_always_on_top(self):
        self.is_always_on_top = not self.is_always_on_top
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.is_always_on_top)
        self.show()

    def set_interval_config(self, min_m, max_m):
        self.config["study_time_min"] = int(min_m * 60)
        self.config["study_time_max"] = int(max_m * 60)
        save_config(self.config)
        self.logic.config = self.config

    def set_duration_config(self, mins):
        self.config["long_break_threshold"] = mins * 60
        save_config(self.config)
        self.logic.config = self.config
        self.update_total_time()

    def configure_hotkey(self, action_key, label_name):
        current = self.config.get("hotkeys", {}).get(action_key, "")
        new_key, ok = QInputDialog.getText(self, f"修改{label_name}", f"请输入组合键：\n(例如 <alt>+z 或 <ctrl>+<alt>+p)", QLineEdit.EchoMode.Normal, current)
        if ok and new_key.strip():
            if "hotkeys" not in self.config:
                self.config["hotkeys"] = {}
            self.config["hotkeys"][action_key] = new_key.strip()
            save_config(self.config)
            
            # Restart hotkey manager
            self.hotkey_manager.stop()
            self.hotkey_manager.hotkey_config = self.config["hotkeys"]
            self.hotkey_manager.start()
            QMessageBox.information(self, "配置成功", f"{label_name}已动态更新为: {new_key.strip()}")

    def _on_db_error(self, error_msg):
        """数据库异步操作失败回调"""
        print(f"数据库操作失败: {error_msg}")
        if "Can't connect to MySQL" in error_msg:
             QMessageBox.critical(self, "数据库连接失败", f"无法连接到 MySQL 远程服务器，请检查网络或配置。\n\n具体错误: {error_msg}")

    def switch_database(self, db_type):
        """切换数据库并根据需要引导配置"""
        curr_db = self.config.get("db_type", "sqlite")
        if db_type == curr_db:
            return
            
        self.config["db_type"] = db_type
        
        if db_type == "mysql":
            # 自动取消 MySQL 配置项的注释符号 (//)
            m_cfg = self.config.get("mysql_config", {})
            new_m_cfg = {}
            for k, v in m_cfg.items():
                new_key = k.lstrip("//")
                new_m_cfg[new_key] = v
            self.config["mysql_config"] = new_m_cfg
            
            save_config(self.config)
            
            msg = "数据库已切换为 MySQL。\n\n程序将自动打开 config.json，请填写 host/user/password 等配置。\n填完后请【重启软件】以确认连接。"
            if pymysql is None:
                msg += "\n\n检测到未安装依赖，请在终端运行:\npip install pymysql"
            
            QMessageBox.information(self, "数据库设置已变更", msg)
            # 自动打开配置文件
            os.startfile(resource_path('config.json'))
        else:
            save_config(self.config)
            QMessageBox.information(self, "数据库设置", "已切回本地 SQLite。请重启软件生效。")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.toggle_mouse_penetration()

    def mousePressEvent(self, event):
        if not self.is_locked and event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if not self.is_locked and event.buttons() == Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)
    
    def mouseReleaseEvent(self, event):
        self.dragPos = None

    def closeEvent(self, event):
        self.logic._clear_current_session() # 确保退出时不记录未完成的会话
        self.save_settings()
        if not self._init_failed:
            try:
                with open(resource_path('config.json'), 'r', encoding='utf-8') as f:
                    final_config = json.load(f)
            except Exception:
                final_config = self.config
                
            final_config['total_study_time'] = self.logic.total_study_time
            final_config['hotkeys'] = self.config.get('hotkeys', {})
            final_config['study_time_min'] = self.config.get('study_time_min')
            final_config['study_time_max'] = self.config.get('study_time_max')
            final_config['long_break_threshold'] = self.config.get('long_break_threshold')
            save_config(final_config)
            
            self.logic.stop()
            self.hotkey_manager.stop()
            self.tray.hide()
        event.accept()
        QApplication.quit()
        
    def update_total_time(self, active_cycle_time_or_total=None, realtime=False):
        if not realtime:
            active_cycle_time = self.logic.current_cycle_study_time
        else:
            active_cycle_time = active_cycle_time_or_total
            
        threshold = self.config.get("long_break_threshold", 90 * 60)
        remaining = max(0, threshold - active_cycle_time)
        
        mins, secs = divmod(remaining, 60)
        if self.logic.current_state in ["long_breaking", "long_break_finished"]:
            self.total_time_label.setText("")
        else:
            self.total_time_label.setText(f"{int(mins):02}:{int(secs):02}")

    def _render_markdown_lists(self, text):
        if not text or text == "无" or text == "未填写总结": return text
        
        lines = text.split('\n')
        result = []
        in_ul = False
        in_ol = False
        
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                if in_ul: result.append("</ul>"); in_ul = False
                if in_ol: result.append("</ol>"); in_ol = False
                continue
            
            # 识别列表模式 (例如: - item, + item, * item, 1. item)
            ul_match = re.match(r'^[\-\+\*]\s+(.*)', trimmed)
            ol_match = re.match(r'^(\d+)\.\s+(.*)', trimmed)
            
            if ul_match:
                if in_ol: result.append("</ol>"); in_ol = False
                if not in_ul: result.append("<ul>"); in_ul = True
                result.append(f"<li>{ul_match.group(1)}</li>")
            elif ol_match:
                if in_ul: result.append("</ul>"); in_ul = False
                if not in_ol: result.append("<ol>"); in_ol = True
                result.append(f"<li>{ol_match.group(2)}</li>")
            else:
                if in_ul: result.append("</ul>"); in_ul = False
                if in_ol: result.append("</ol>"); in_ol = False
                result.append(trimmed + "<br>")
                
        if in_ul: result.append("</ul>")
        if in_ol: result.append("</ol>")
        return "".join(result)

    def generate_statistics_html(self, open_browser=False, *args):
        """发起异步报表生成请求"""
        # 如果是手动查看，先弹系统小通知或改变状态
        if open_browser:
            self.status_label.setText("正在加载报表...")
            
        # 触发后台 Worker 异步拉取数据
        QTimer.singleShot(0, lambda: self.logic.db_worker.fetch_stats(open_browser))

    def _on_stats_ready(self, rows, open_browser):
        """后台数据准备就绪后的渲染回调"""
        # 恢复状态显示（如果是正常状态）
        if self.logic.current_state == "stopped":
            self.status_label.setText("沉浸式学习\n右键单击开始")
        elif self.logic.is_paused:
            self.status_label.setText("⏸️ 已暂停")
        
        html_path = resource_path("statistics.html")
        
        week_map = {
            'Monday': '星期一', 'Tuesday': '星期二', 'Wednesday': '星期三',
            'Thursday': '星期四', 'Friday': '星期五', 'Saturday': '星期六', 'Sunday': '星期日'
        }

        cards_html = ""
        daily_groups = {}
        for row in reversed(rows[-100:]):
            if len(row) >= 5:
                date_val = row[3]
                if date_val not in daily_groups:
                    daily_groups[date_val] = []
                daily_groups[date_val].append(row)

        for date_val, group_rows in daily_groups.items():
            day_zh = week_map.get(group_rows[0][4], group_rows[0][4])
            
            # 尝试计算当日总专注时长
            total_duration = 0.0
            for r in group_rows:
                try:
                    total_duration += float(r[2])
                except ValueError:
                    pass
            
            sessions_html = ""
            for row in group_rows:
                # 仅保留时间段的时分秒 (例如 '2026-03-27 10:46:12' -> '10:46:12')
                start_time = row[0].split(' ')[-1] if ' ' in row[0] else row[0]
                end_time = row[1].split(' ')[-1] if ' ' in row[1] else row[1]
                duration = row[2]
                
                pause_count = row[5] if len(row) >= 8 else "0"
                pause_reasons_raw = row[6] if len(row) >= 8 else "无"
                summary = row[7] if len(row) >= 8 else "无记录"
                
                reasons_html = ""
                if pause_reasons_raw and pause_reasons_raw != "无":
                    # 检测是否包含换行或列表符号，若是则按 Markdown 渲染，否则按传统标签渲染
                    if "\n" in pause_reasons_raw or any(pause_reasons_raw.startswith(s) for s in ["- ", "+ ", "* ", "1. "]):
                        # 移除 margin-top 以消除空行
                        reasons_html = f"<div class='markdown-content' style='margin-top:2px; font-size:0.9em;'>{self._render_markdown_lists(pause_reasons_raw)}</div>"
                    else:
                        r_list = [r.strip() for r in pause_reasons_raw.split("; ") if r.strip()]
                        reasons_tags_html = "".join([f"<span class='reason-tag'>{r}</span>" for r in r_list])
                        reasons_html = f"<div class='reason-tags' style='margin-top:6px;'>{reasons_tags_html}</div>"
                else:
                    reasons_html = "<span class='reason-tag-empty' style='margin-left:5px;'>无暂停记录</span>"
                
                sessions_html += f"""
                <div class="session-item">
                    <div class="session-header">
                        <span class="session-time">⏱️ {start_time} - {end_time}</span>
                        <span class="session-duration">专注 {duration} 分钟</span>
                    </div>
                    <div class="card-stats">⏸️ 主动暂停: {pause_count} 次</div>
                    <div class="card-reasons">
                        <strong>暂停明细:</strong>{reasons_html}
                    </div>
                    <div class="card-summary"><strong>专注总结:</strong><div class="markdown-content">{self._render_markdown_lists(summary)}</div></div>
                </div>
                """
                
            cards_html += f"""
            <div class="card">
                <div class="card-header">
                    <span class="date-badge">{date_val} {day_zh}</span>
                    <span class="duration-badge">今日专注 {total_duration:.1f} 分钟</span>
                </div>
                <div class="sessions-container">
                    {sessions_html}
                </div>
            </div>
            """
                
        content_html = cards_html if cards_html else "<div class='empty'>暂无大专注学习记录，快去开启第一次沉浸式学习吧！</div>"

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>MyTimeLogger 统计报表</title>
    <style>
        :root {{ --bg: #f3f4f6; --card-bg: #ffffff; --text: #1f2937; --text-light: #6b7280; --primary: #3b82f6; --accent: #10b981; --border: #e5e7eb; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 40px; line-height: 1.5; }}
        h1 {{ text-align: center; color: var(--primary); margin-bottom: 40px; font-weight: 700; letter-spacing: 1px; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .card {{ background: var(--card-bg); border-radius: 16px; padding: 24px; margin-bottom: 24px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03); border: 1px solid var(--border); transition: transform 0.2s, box-shadow 0.2s; }}
        .card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05); }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 2px solid var(--border); padding-bottom: 16px; }}
        .date-badge {{ font-weight: 700; color: var(--primary); font-size: 1.25em; }}
        .duration-badge {{ background: var(--accent); color: white; padding: 6px 14px; border-radius: 20px; font-size: 0.95em; font-weight: 600; box-shadow: 0 2px 4px rgba(16,185,129,0.2); }}
        .session-item {{ border-bottom: 1px dashed var(--border); padding-bottom: 20px; margin-bottom: 20px; }}
        .session-item:last-child {{ border-bottom: none; padding-bottom: 0; margin-bottom: 0; }}
        .session-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
        .session-time {{ color: var(--text-light); font-size: 0.95em; font-weight: 500; }}
        .session-duration {{ color: var(--accent); font-size: 0.85em; font-weight: 600; background: #d1fae5; padding: 4px 10px; border-radius: 12px; }}
        .card-stats {{ color: #eab308; font-size: 0.9em; margin-bottom: 10px; font-weight: 600; display: flex; align-items: center; gap: 6px; }}
        .card-reasons {{ background: #fafafa; padding: 12px 16px; border-radius: 10px; margin-bottom: 12px; font-size: 0.9em; color: var(--text); border-left: 4px solid #f59e0b; box-shadow: inset 0 2px 4px 0 rgba(0,0,0,0.02); }}
        .reason-tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .reason-tag {{ background: #fef3c7; color: #b45309; padding: 4px 10px; border-radius: 12px; font-size: 0.85em; font-weight: 600; border: 1px solid #fde68a; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
        .reason-tag-empty {{ color: #9ca3af; font-size: 0.9em; font-style: italic; }}
        .reason-tag-empty {{ color: #9ca3af; font-size: 0.9em; font-style: italic; }}
        .card-summary {{ background: #eff6ff; padding: 14px 16px; border-radius: 10px; font-size: 0.95em; color: #1e3a8a; border-left: 4px solid var(--primary); line-height: 1.5; }}
        .markdown-content {{ margin-top: 8px; }}
        .markdown-content ul, .markdown-content ol {{ padding-left: 20px; margin: 5px 0; }}
        .markdown-content li {{ margin-bottom: 4px; }}
        strong {{ color: var(--text); }}
        .empty {{ text-align: center; padding: 60px 40px; color: var(--text-light); font-size: 1.1em; background: var(--card-bg); border-radius: 16px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 深度专注统计报表</h1>
        {content_html}
    </div>
</body>
</html>"""
        try:
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            if open_browser:
                if sys.platform == 'win32':
                    os.startfile(html_path)
                elif sys.platform == 'darwin':
                    os.system(f'open "{html_path}"')
                else:
                    os.system(f'xdg-open "{html_path}"')
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法生成统计页面: {e}")
        
    def set_opacity(self, value):
        self.settings.setValue("ui/opacity", value)
        self.update_stylesheet()

    def save_settings(self):
        if self._init_failed: return
        self.settings.setValue("ui/geometry", self.saveGeometry())
        self.settings.setValue("ui/opacity", self.settings.value("ui/opacity", 0.8))
        self.settings.setValue("ui/alwaysOnTop", self.is_always_on_top)

    def load_settings(self):
        geometry = self.settings.value("ui/geometry")
        if geometry: self.restoreGeometry(geometry)
        else: self.resize(220, 120)
        self.update_total_time(self.logic.total_study_time)

# ==============================================================================
# 程序主入口
# ==============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # --- 单实例锁定检测 ---
    lock_path = resource_path("my_time_logger.lock")
    lock_file = QLockFile(lock_path)
    if not lock_file.tryLock(100): # 尝试锁定 100ms
        QMessageBox.warning(None, "程序已在运行", "MyTimeLogger 已经在后台运行中了，请检查系统托盘或任务栏。")
        sys.exit(0)
    
    if keyboard is None:
        show_pynput_error()
    
    app.setQuitOnLastWindowClosed(False)

    if not os.path.exists(resource_path(os.path.join('document', 'icon.ico'))):
        QMessageBox.critical(None, "资源错误", "关键文件 'document/icon.ico' 未找到！\n程序无法启动。")
        sys.exit(1)

    config = load_or_create_config()
    window = MyTimeLoggerGUI(config)
    
    if window._init_failed:
        sys.exit(1)

    window.setWindowTitle("MyTimeLogger v0.98")
    window.show()
    sys.exit(app.exec())
