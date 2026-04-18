# -*- coding: utf-8 -*-
"""
图形界面模块 (gui.py)
====================
应用程序的 GUI 层:
- MyTimeLoggerGUI: 主窗口，包含状态显示、右键菜单、系统托盘、
  设置管理、统计报表生成等全部界面交互逻辑
"""

import os
import re
import sys
import json
import sqlite3
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu,
    QSystemTrayIcon, QMessageBox, QInputDialog, QLineEdit,
    QPushButton, QDialog, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QSize
from PyQt6.QtGui import QIcon, QAction

from utils import resource_path
from config import save_config
from logic import MyTimeLoggerLogic
from hotkeys import HotkeyManager
from dialogs import MarkdownInputDialog
from category_manager import CategoryManager
from activity_panel import ActivityPanel


class MyTimeLoggerGUI(QWidget):
    """主窗口 GUI，桥接核心逻辑与用户交互"""

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
        self.is_mini_mode = True # 强制 Mini 模式

        self.create_tray_icon()

        self.hotkey_manager = HotkeyManager(self.config.get('hotkeys', {}))
        self.hotkey_manager.start_triggered.connect(self.logic.start_only)
        self.hotkey_manager.toggle_pause_triggered.connect(self.logic.toggle_pause)
        self.hotkey_manager.reset_cycle_triggered.connect(self.logic.reset_cycle)
        self.hotkey_manager.toggle_checklist_triggered.connect(self.toggle_daily_checklist)
        self.hotkey_manager.toggle_activity_panel_triggered.connect(self.toggle_activity_panel)
        QTimer.singleShot(1000, self.hotkey_manager.start)

        self._checklist_window = None  # 日清单窗口（首次访问时创建）
        self._activity_panel_window = None  # 活动面板窗口
        self._habit_tracker_window = None  # 习惯打卡窗口
        self.category_manager = CategoryManager()

        # 软件启动后延迟 100 毫秒，自动在后台同步今日清单（不打开窗口）
        tt_cfg = self.config.get("ticktick_config", {})
        if tt_cfg.get("enabled") and tt_cfg.get("access_token"):
            QTimer.singleShot(100, self._init_checklist_background_sync)


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

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(False)

        self.total_time_label = QLabel()
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_time_label.setObjectName("total_time_label")

        self._build_start_button()
        self.rebuild_layout()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.background_widget)

        self.load_settings()
        self.update_stylesheet()

        self.logic.db_worker.stats_ready.connect(self._on_stats_ready)
        self.logic.db_worker.error_occurred.connect(self._on_db_error)

        self.logic.state_changed.connect(self.update_status)
        self.logic.time_updated.connect(self.update_total_time)
        self.logic.notification_requested.connect(self.show_notification)
        self.logic.input_reason_requested.connect(self.prompt_for_pause_reason)
        self.logic.input_summary_requested.connect(self.prompt_for_session_summary)
        self.logic.session_logged.connect(self.generate_statistics_html)

        self._build_end_break_button()
        self.generate_statistics_html()
        self.logic.reset_cycle()
        
        # 启动即开启大面板模式
        QTimer.singleShot(300, self._on_expand_clicked)

    # ======================== 通知与对话框 ========================

    def show_notification(self, title, message):
        """通过系统托盘显示通知"""
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
        """确保弹窗获得前台焦点（Windows AttachThreadInput 组合拳）"""
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
        """弹出暂停原因输入对话框"""
        dialog = MarkdownInputDialog("暂停提醒", "请输入本次暂停的原因（支持 markdown 语法）：", self)
        QTimer.singleShot(100, lambda: self._activate_dialog(dialog))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            reason = dialog.textValue()
            self.logic.add_pause_reason(reason.strip() if reason.strip() else "无")
        else:
            self.logic.add_pause_reason("无")

    def prompt_for_session_summary(self, is_success=True):
        """弹出专注总结输入对话框"""
        title = "大专注完成！" if is_success else "专注失败"
        prompt = "恭喜完成一段深度专注！请总结你做了哪些事（支持 markdown 语法）：" if is_success else "专注被提前终止，请记录失败原因或简述进度（支持 markdown 语法）："
        init_text = "" if is_success else "专注失败：\n"
        dialog = MarkdownInputDialog(title, prompt, self, initial_text=init_text)
        QTimer.singleShot(100, lambda: self._activate_dialog(dialog))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            summary = dialog.textValue()
            final_summary = summary.strip() if summary.strip() else "未填写总结"
            self.logic.commit_large_session(final_summary)
        else:
            self.logic.commit_large_session("未填写总结")

    # ======================== 布局管理 ========================

    def rebuild_layout(self):
        """重建布局，仅保留 Mini 模式"""
        if self.background_widget.layout():
            old_layout = self.background_widget.layout()
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget() and item.widget() not in [self.status_label, self.total_time_label, self.end_break_btn if hasattr(self, 'end_break_btn') else None, self.start_btn if hasattr(self, 'start_btn') else None, self.expand_btn if hasattr(self, 'expand_btn') else None]:
                    item.widget().deleteLater()
            from PyQt6 import sip
            sip.delete(old_layout)

        # 强制 Mini 横向布局
        self.setFixedSize(280, 42)
        self.background_widget.setFixedSize(280, 42)
        self.status_label.setWordWrap(False)
        
        new_layout = QHBoxLayout(self.background_widget)
        new_layout.setContentsMargins(6, 0, 10, 0)
        new_layout.setSpacing(6)
        
        # 最左边添加放大按钮
        if not hasattr(self, 'expand_btn'):
            self.expand_btn = QPushButton(self.background_widget)
            self.expand_btn.setIcon(QIcon(resource_path("document/expand.svg")))
            self.expand_btn.setFixedSize(26, 26)
            self.expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.expand_btn.setStyleSheet("QPushButton { background-color: rgba(255, 255, 255, 0.25); border: none; border-radius: 5px; } QPushButton:hover { background-color: rgba(255, 255, 255, 0.45); }")
            self.expand_btn.clicked.connect(self._on_expand_clicked)
        new_layout.addWidget(self.expand_btn)
        
        new_layout.addWidget(self.expand_btn)
        new_layout.addWidget(self.status_label)
        new_layout.addWidget(self.total_time_label)
        new_layout.addStretch()
        
        if hasattr(self, 'start_btn'):
            new_layout.addWidget(self.start_btn)
        if hasattr(self, 'end_break_btn'):
            new_layout.addWidget(self.end_break_btn)

    # ======================== 日志与重置 ========================

    def open_log_folder(self):
        """打开日志文件所在目录"""
        log_dir = resource_path(".")
        try:
            if sys.platform == 'win32':
                os.startfile(log_dir)
            elif sys.platform == 'darwin':
                os.system(f'open "{log_dir}"')
            else:
                os.system(f'xdg-open "{log_dir}"')
        except Exception as e:
            print(f"无法打开文件夹: {e}")
            QMessageBox.warning(self, "操作失败", f"无法自动打开文件夹。\n请手动前往: {log_dir}")

    def confirm_and_reset_all(self):
        """确认后清空所有学习记录"""
        reply = QMessageBox.question(
            self, '安全提示',
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
                log_path = self.logic.local_logger.log_path
                if os.path.exists(log_path):
                    try:
                        conn = sqlite3.connect(log_path)
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM study_sessions")
                        conn.commit()
                        conn.close()
                        os.remove(log_path)
                    except Exception as e:
                        print(f"清理数据库失败: {e}")
                self.logic.local_logger._initialize_db()
                self.generate_statistics_html()
                QMessageBox.information(self, "清理成功", "所有记录及统计报表已彻底清空。")
            elif ok:
                QMessageBox.warning(self, "密码错误", "密码不正确，操作已取消。")

    # ======================== 右键菜单 ========================

    def populate_context_menu(self, menu):
        """构建右键/托盘菜单"""
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
            info_action = QAction(status_text, self)
            info_action.setDisabled(True)
            menu.addAction(info_action)

        if self.logic.current_state != 'stopped':
            long_break_threshold = self.config.get("long_break_threshold", 90 * 60)
            current_study_time = self.logic.total_study_time
            if current_study_time < long_break_threshold:
                remaining_seconds = long_break_threshold - current_study_time
                mins, secs = divmod(remaining_seconds, 60)
                if self.logic.current_state == "studying" and self.logic.timer.isActive():
                    timer_remaining_secs = self.logic.timer.remainingTime() // 1000
                    remaining_seconds -= timer_remaining_secs
                    mins, secs = divmod(remaining_seconds, 60)
                long_break_status_text = f"🎯 距长休息约: {int(mins)}分"
            else:
                long_break_status_text = "🎉 已可进入长休息"
            long_break_action = QAction(long_break_status_text, self)
            long_break_action.setDisabled(True)
            menu.addAction(long_break_action)
        menu.addSeparator()

        is_running = self.logic.timer.isActive()
        is_paused = self.logic.is_paused

        start_hotkey = hotkey_config.get('start', '')
        start_text = "▶️ 开 始" + (f"  ({start_hotkey})" if start_hotkey else "")
        start_action = QAction(start_text, self)
        start_action.triggered.connect(self.logic.start_only)
        if is_running or is_paused:
            start_action.setDisabled(True)

        pause_hotkey = hotkey_config.get('toggle_pause', '')
        pause_text = "⏯️ 暂停 / 继续" + (f"  ({pause_hotkey})" if pause_hotkey else "")
        pause_action = QAction(pause_text, self)
        pause_action.triggered.connect(self.logic.toggle_pause)
        if not is_running and not is_paused:
            pause_action.setDisabled(True)

        lock_text = "🔓 解锁 (可交互)" if self.is_locked else "🔒 锁定 (鼠标穿透)"
        lock_action = QAction(lock_text, self)
        lock_action.triggered.connect(self.toggle_mouse_penetration)

        always_on_top_text = f"{'✅' if self.is_always_on_top else '🔲'} 总在最前"
        always_on_top_action = QAction(always_on_top_text, self)
        always_on_top_action.triggered.connect(self.toggle_always_on_top)

        config_menu = QMenu("⚙️ 设置", self)

        hotkey_menu = QMenu("快捷键设置", self)
        set_pause_action = QAction(f"设置暂停/恢复键 (当前: {self.config.get('hotkeys', {}).get('toggle_pause', '<alt>+c')})", self)
        set_pause_action.triggered.connect(lambda: self.configure_hotkey('toggle_pause', '暂停/恢复键'))
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
        if self.config.get("db_type", "sqlite") == "sqlite":
            sqlite_action.setChecked(True)
        sqlite_action.triggered.connect(lambda: self.switch_database("sqlite"))
        mysql_action = QAction("MySQL (远程同步)", self)
        mysql_action.setCheckable(True)
        if self.config.get("db_type") == "mysql":
            mysql_action.setChecked(True)
        mysql_action.triggered.connect(lambda: self.switch_database("mysql"))
        db_menu.addAction(sqlite_action)
        db_menu.addAction(mysql_action)

        config_menu.addMenu(interval_menu)
        config_menu.addMenu(duration_menu)
        config_menu.addMenu(hotkey_menu)
        config_menu.addMenu(db_menu)

        opacity_menu = QMenu("💧 透明度", self)
        for val in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.01]:
            op_action = QAction(f"{int(val*100)}%", self)
            op_action.triggered.connect(lambda _, v=val: self.set_opacity(v))
            opacity_menu.addAction(op_action)

        reset_menu = QMenu("🔄 重置", self)
        reset_cycle_hotkey = hotkey_config.get('reset_cycle', '')
        reset_cycle_text = "重置当前轮次" + (f"  ({reset_cycle_hotkey})" if reset_cycle_hotkey else "")
        reset_cycle_action = QAction(reset_cycle_text, self)
        reset_cycle_action.triggered.connect(self.logic.reset_cycle)
        clear_all_action = QAction("🗑️ 清空所有记录", self)
        clear_all_action.triggered.connect(self.confirm_and_reset_all)
        reset_menu.addAction(reset_cycle_action)
        reset_menu.addAction(clear_all_action)

        open_log_action = QAction("📂 打开日志文件夹", self)
        open_log_action.triggered.connect(self.open_log_folder)
        checklist_action = QAction("📋 日清单  (Alt+X)", self)
        checklist_action.triggered.connect(self.toggle_daily_checklist)
        activity_panel_action = QAction("📊 柳比歇夫时间管理  (Alt+Z)", self)
        activity_panel_action.triggered.connect(self.toggle_activity_panel)
        habit_action = QAction("✅ 习惯打卡", self)
        habit_action.triggered.connect(self.toggle_habit_tracker)
        stat_action = QAction("📊 查看统计 (网页版)", self)
        stat_action.triggered.connect(lambda: self.generate_statistics_html(open_browser=True))
        quit_action = QAction("❌ 退 出", self)
        quit_action.triggered.connect(self.close)

        menu.addAction(start_action)
        menu.addAction(pause_action)
        menu.addSeparator()
        menu.addAction(lock_action)
        menu.addAction(always_on_top_action)
        menu.addMenu(config_menu)
        menu.addMenu(opacity_menu)
        menu.addMenu(reset_menu)
        menu.addAction(open_log_action)
        menu.addAction(activity_panel_action)
        menu.addAction(checklist_action)
        menu.addAction(habit_action)
        menu.addAction(stat_action)
        menu.addSeparator()
        menu.addAction(quit_action)

    # ======================== 样式与显示 ========================

    def update_stylesheet(self):
        """根据模式和设置更新样式"""
        opacity = self.settings.value("ui/opacity", 0.8, type=float)
        border_style = "border: none;" if self.is_locked else "border: 1px solid #E5E9F0;"
        label_font = 13
        total_time_font = 20
        self.background_widget.setStyleSheet(f"""
            #background {{ background-color: rgba(240, 242, 245, {opacity}); border-radius: 10px; {border_style} }}
            QLabel {{ background-color: transparent; color: #2E3440; font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif; font-size: {label_font}px; }}
            #status_label {{ font-family: 'Font Awesome 6 Free', 'Microsoft YaHei'; }}
            #total_time_label {{ font-size: {total_time_font}px; font-weight: bold; color: #5E81AC; padding-top: 2px; letter-spacing: 1px; }}
        """)

    def _build_start_button(self):
        """创建播放/暂停切换按钮"""
        self.start_btn = QPushButton(self.background_widget)
        self.start_btn.setObjectName("start_btn")
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.setFixedSize(24, 24)
        self.start_btn.clicked.connect(self._on_play_pause_clicked)
        self._set_play_btn_state("play")

    def _build_end_break_button(self):
        """创建结束休息按钮，初始隐藏"""
        self.end_break_btn = QPushButton("\uf04d", self.background_widget)
        self.end_break_btn.setObjectName("end_break_btn")
        self.end_break_btn.setFixedSize(24, 24)
        self.end_break_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end_break_btn.setStyleSheet("""
            QPushButton#end_break_btn {
                font-family: 'Font Awesome 6 Free'; font-weight: 900;
                background-color: #FF5252; color: white; border: none;
                border-radius: 4px; font-size: 10px;
            }
            QPushButton#end_break_btn:hover { background-color: #FF1744; }
        """)
        self.end_break_btn.clicked.connect(self._on_end_break_clicked)
        self.end_break_btn.hide()
        self.rebuild_layout()

    def _on_end_break_clicked(self):
        """点击结束按钮（根据状态区分为结束休息或结束正计时）"""
        if self.logic.current_state == "countup_studying":
            self.logic.end_countup_now()
        elif self.logic.current_state == "studying":
            self.logic.end_study_now()
        else:
            self.logic.end_break_now()

    def _set_play_btn_state(self, mode):
        """设置播放/暂停按钮的外观。mode: 'play' | 'pause'"""
        self._play_btn_mode = mode
        if mode == "play":
            self.start_btn.setText("\uf04b")
            self.start_btn.setStyleSheet("""
                QPushButton#start_btn {
                    font-family: 'Font Awesome 6 Free'; font-weight: 900;
                    background-color: #5E81AC; color: white; border: none; border-radius: 4px; font-size: 10px; padding-left: 2px;
                }
                QPushButton#start_btn:hover { background-color: #81A1C1; }
            """)
        else:
            self.start_btn.setText("\uf04c")
            self.start_btn.setStyleSheet("""
                QPushButton#start_btn {
                    font-family: 'Font Awesome 6 Free'; font-weight: 900;
                    background-color: #D08770; color: white; border: none; border-radius: 4px; font-size: 10px;
                }
                QPushButton#start_btn:hover { background-color: #BF616A; }
            """)

    def _on_play_pause_clicked(self):
        """播放/暂停按钮点击：根据当前状态路由"""
        state = self.logic.current_state
        if state in ["stopped", "long_break_finished"]:
            self.logic.start_only()
        elif self.logic.is_paused:
            self.logic.toggle_pause()
        elif state in ["studying", "countup_studying", "short_breaking", "long_breaking"]:
            self.logic.toggle_pause()

    def _update_btn_visibility(self, state_name):
        """根据状态控制播放/暂停 + 结束休息按钮"""
        if state_name in ["stopped", "long_break_finished"]:
            self._set_play_btn_state("play")
            self.start_btn.show()
            self.end_break_btn.hide()
        elif state_name == "countup_studying":
            self._set_play_btn_state("pause")
            self.start_btn.show()
            self.end_break_btn.show()
        elif state_name == "long_breaking":
            self._set_play_btn_state("pause")
            self.start_btn.show()
            self.end_break_btn.show()
        elif state_name == "studying":
            self._set_play_btn_state("pause")
            self.start_btn.show()
            self.end_break_btn.show()
        elif state_name == "short_breaking":
            self._set_play_btn_state("pause")
            self.start_btn.show()
            self.end_break_btn.show()
        else:
            self.start_btn.hide()
            self.end_break_btn.hide()
        # 暂停态特殊处理
        if self.logic.is_paused:
            self._set_play_btn_state("play")
            self.start_btn.show()

    def update_status(self, status_text, state_name):
        """更新状态显示文本"""
        self.current_state_text = status_text
        
        # 缓存当前选中分类的图标名称和颜色
        self._cached_cat_icon = "⏳"
        self._cached_cat_name = "正计时"
        self._cached_cat_color = "#5E81AC"
        if self.logic.current_category_id:
            for cat in self.category_manager.get_all_active():
                if cat['id'] == self.logic.current_category_id:
                    self._cached_cat_icon = cat.get('icon', '⏳')
                    self._cached_cat_name = cat.get('name', '正计时')
                    self._cached_cat_color = cat.get('color', '#5E81AC')
                    break
                    
        self._update_btn_visibility(state_name)
        if state_name not in ["stopped", "long_break_finished"]:
            self.countdown_timer.start()
            self.update_countdown_display()
        else:
            self.countdown_timer.stop()
            self.status_label.setText(status_text)
        self.update_stylesheet()

    def update_countdown_display(self):
        """更新倒计时显示"""
        if self.logic.is_paused:
            self.status_label.setText("⏸️ 已暂停")
            return

        if self.logic.timer.isActive() or self.logic.current_state == "countup_studying":
            remaining_ms = self.logic.timer.remainingTime() if self.logic.timer.isActive() else 0
            mins, secs = divmod(remaining_ms // 1000, 60)
            state = self.logic.current_state
            
            if state == "countup_studying":
                elapsed = (datetime.now() - self.logic.current_session_start_time).total_seconds()
                m, s = divmod(int(elapsed), 60)
                icon = getattr(self, '_cached_cat_icon', '⏳')
                name = getattr(self, '_cached_cat_name', '正计时')
                color = getattr(self, '_cached_cat_color', '#5E81AC')
                self.status_label.setText(f'<span style="color: {color};">{icon}</span> {name}<br/>⏱ {int(m):02}:{int(s):02}')
                self.total_time_label.setText("")
            elif state == "studying":
                session_elapsed = self.logic.current_session_duration - (remaining_ms // 1000)
                active_cycle_time = self.logic.current_cycle_study_time + session_elapsed
                
                icon = getattr(self, '_cached_cat_icon', '📚')
                name = getattr(self, '_cached_cat_name', '专注中')
                color = getattr(self, '_cached_cat_color', '#5E81AC')
                up_m, up_s = divmod(int(active_cycle_time), 60)
                # 正计时放到 status_label
                self.status_label.setText(f'<span style="color: {color};">{icon}</span> {name}<br/>⏱ {int(up_m):02}:{int(up_s):02}')
                
                # 总的倒计时放到 total_time_label
                threshold = self.config.get("long_break_threshold", 90 * 60)
                remaining_total = max(0, threshold - active_cycle_time)
                down_m, down_s = divmod(int(remaining_total), 60)
                self.total_time_label.setText(f"🎯 {int(down_m):02}:{int(down_s):02}")
            elif state == "long_breaking":
                self.status_label.setText(f"🧘 长休息\n{int(mins):02}:{int(secs):02}")
            elif state == "short_breaking":
                self.status_label.setText(f"☕ 短暂休息中...\n{int(mins):02}:{int(secs):02}")
            else:
                self.status_label.setText(f"{int(mins):02}:{int(secs):02}")

    # ======================== 系统托盘 ========================

    def create_tray_icon(self):
        """创建系统托盘图标和菜单"""
        self.tray_icon = QIcon(resource_path(os.path.join('document', 'icon.ico')))
        self.tray = QSystemTrayIcon(self.tray_icon, self)
        self.tray.setToolTip("MyTimeLogger - 保持专注")
        self.tray_menu = QMenu(self)
        self.tray_menu.aboutToShow.connect(self.update_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()
        self.tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason):
        """托盘图标点击事件处理"""
        if reason in [QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick]:
            # 分类管理面板与状态条显隐互斥绑定
            win = self._ensure_activity_panel_window()
            if win.isVisible():
                self.switch_ui_mode(to_mini=True)
            else:
                self.switch_ui_mode(to_mini=False)
        
        # 始终置顶逻辑（右键托盘菜单触发 Context 信号）
        elif self.is_always_on_top and reason == QSystemTrayIcon.ActivationReason.Context:
            if not (self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint):
                self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            # 移除这里的 self.show()，避免右键菜单弹出时 Mini 栏意外出现
            self.activateWindow()
            self.raise_()

    def update_tray_menu(self):
        self.populate_context_menu(self.tray_menu)

    def contextMenuEvent(self, event):
        if self.is_locked:
            return
        context_menu = QMenu(self)
        self.populate_context_menu(context_menu)
        context_menu.exec(event.globalPos())

    # ======================== 窗口交互 ========================

    def toggle_mouse_penetration(self):
        """切换鼠标穿透锁定状态"""
        self.is_locked = not self.is_locked
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, self.is_locked)
        self.show()
        if not self.is_locked:
            self.activateWindow()
        self.update_stylesheet()

    def toggle_always_on_top(self):
        """切换始终置顶"""
        self.is_always_on_top = not self.is_always_on_top
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.is_always_on_top)
        self.show()

    def set_interval_config(self, min_m, max_m):
        """设置学习间隔配置"""
        self.config["study_time_min"] = int(min_m * 60)
        self.config["study_time_max"] = int(max_m * 60)
        save_config(self.config)
        self.logic.config = self.config

    def set_duration_config(self, mins):
        """设置大专注时长配置"""
        self.config["long_break_threshold"] = mins * 60
        save_config(self.config)
        self.logic.config = self.config
        self.update_total_time()

    def configure_hotkey(self, action_key, label_name):
        """配置快捷键"""
        current = self.config.get("hotkeys", {}).get(action_key, "")
        new_key, ok = QInputDialog.getText(self, f"修改{label_name}", f"请输入组合键：\n(例如 <alt>+z 或 <ctrl>+<alt>+p)", QLineEdit.EchoMode.Normal, current)
        if ok and new_key.strip():
            if "hotkeys" not in self.config:
                self.config["hotkeys"] = {}
            self.config["hotkeys"][action_key] = new_key.strip()
            save_config(self.config)
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
        """切换数据库类型"""
        curr_db = self.config.get("db_type", "sqlite")
        if db_type == curr_db:
            return
        self.config["db_type"] = db_type
        if db_type == "mysql":
            m_cfg = self.config.get("mysql_config", {})
            new_m_cfg = {}
            for k, v in m_cfg.items():
                new_key = k.lstrip("//")
                new_m_cfg[new_key] = v
            self.config["mysql_config"] = new_m_cfg
            save_config(self.config)
            msg = "数据库已切换为 MySQL。\n\n程序将自动打开 config.json，请填写 host/user/password 等配置。\n填完后请【重启软件】以确认连接。"
            try:
                import pymysql as _pm
            except ImportError:
                msg += "\n\n检测到未安装依赖，请在终端运行：\npip install pymysql"
            QMessageBox.information(self, "数据库设置已变更", msg)
            os.startfile(resource_path('config.json'))
        else:
            save_config(self.config)
            QMessageBox.information(self, "数据库设置", "已切回本地 SQLite。请重启软件生效。")

    # ======================== 鼠标事件 ========================

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_mouse_penetration()

    def mousePressEvent(self, event):
        if not self.is_locked and event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if not self.is_locked and event.buttons() == Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)

    def mouseReleaseEvent(self, event):
        self.dragPos = None

    # ======================== 关闭与持久化 ========================

    def closeEvent(self, event):
        """程序关闭时保存状态"""
        self.logic._clear_current_session()
        self.save_settings()
        if self._checklist_window:
            self._checklist_window.cleanup()
            self._checklist_window.close()
        if not self._init_failed:
            try:
                with open(resource_path('config.json'), 'r', encoding='utf-8') as f:
                    final_config = json.load(f)
            except Exception:
                final_config = self.config
            changed = False
            for k, v in [
                ('total_study_time', self.logic.total_study_time),
                ('hotkeys', self.config.get('hotkeys', {})),
                ('study_time_min', self.config.get('study_time_min')),
                ('study_time_max', self.config.get('study_time_max')),
                ('long_break_threshold', self.config.get('long_break_threshold'))
            ]:
                if final_config.get(k) != v:
                    final_config[k] = v
                    changed = True
            if changed:
                save_config(final_config)
            self.logic.stop()
            self.hotkey_manager.stop()
            self.tray.hide()
        event.accept()
        QApplication.quit()

    def _ensure_checklist_window(self):
        """确保日清单窗口已创建并返回"""
        if self._checklist_window is None:
            from daily_checklist import DailyChecklistWindow
            self._checklist_window = DailyChecklistWindow(
                config=self.config,
                logic=self.logic,
                category_manager=self.category_manager
            )
        return self._checklist_window

    def _init_checklist_background_sync(self):
        """启动时后台静默同步（不打开窗口）"""
        win = self._ensure_checklist_window()
        win.start_background_sync()

    def toggle_daily_checklist(self):
        """切换日清单窗口显隐"""
        win = self._ensure_checklist_window()
        if win.isVisible():
            win.hide()
        else:
            win.show()

    def switch_ui_mode(self, to_mini: bool):
        """
        统一切换 UI 模式：Mini 栏 ↔ 大面板 (完全互斥)
        """
        full_win = self._ensure_activity_panel_window()
        if to_mini:
            full_win.hide()
            self.show()
            self.is_mini_mode = True
        else:
            self.hide()
            full_win.show()
            self.is_mini_mode = False

    def _on_expand_clicked(self):
        """切换为大面板模式"""
        self.switch_ui_mode(to_mini=False)

    def _ensure_activity_panel_window(self):
        """确保活动面板窗口已创建并返回"""
        if self._activity_panel_window is None:
            self._activity_panel_window = ActivityPanel(
                logic=self.logic,
                category_manager=self.category_manager,
                main_window=self
            )
        return self._activity_panel_window

    def toggle_activity_panel(self):
        """切换活动面板 (集成互斥逻辑)"""
        full_win = self._ensure_activity_panel_window()
        if full_win.isVisible():
            self.switch_ui_mode(to_mini=True)
        else:
            self.switch_ui_mode(to_mini=False)

    def _ensure_habit_window(self):
        """确保习惯打卡窗口已创建并返回"""
        if self._habit_tracker_window is None:
            from habit_tracker import HabitTrackerWindow
            self._habit_tracker_window = HabitTrackerWindow(config=self.config)
        return self._habit_tracker_window

    def toggle_habit_tracker(self):
        """切换习惯打卡窗口显隐"""
        win = self._ensure_habit_window()
        if win.isVisible():
            win.hide()
        else:
            win.show()

    def update_total_time(self, active_cycle_time_or_total=None, realtime=False):
        """更新累计时间显示"""
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
        """将 Markdown 列表转为 HTML"""
        if not text or text == "无" or text == "未填写总结":
            return text
        lines = text.split('\n')
        result = []
        in_ul = False
        in_ol = False
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                if in_ul:
                    result.append("</ul>")
                    in_ul = False
                if in_ol:
                    result.append("</ol>")
                    in_ol = False
                continue
            ul_match = re.match(r'^[\-\+\*]\s+(.*)', trimmed)
            ol_match = re.match(r'^(\d+)\.\s+(.*)', trimmed)
            if ul_match:
                if in_ol:
                    result.append("</ol>")
                    in_ol = False
                if not in_ul:
                    result.append("<ul>")
                    in_ul = True
                result.append(f"<li>{ul_match.group(1)}</li>")
            elif ol_match:
                if in_ul:
                    result.append("</ul>")
                    in_ul = False
                if not in_ol:
                    result.append("<ol>")
                    in_ol = True
                result.append(f"<li>{ol_match.group(2)}</li>")
            else:
                if in_ul:
                    result.append("</ul>")
                    in_ul = False
                if in_ol:
                    result.append("</ol>")
                    in_ol = False
                result.append(trimmed + "<br>")
        if in_ul:
            result.append("</ul>")
        if in_ol:
            result.append("</ol>")
        return "".join(result)

    # ======================== 统计报表 ========================

    def generate_statistics_html(self, open_browser=False, *args):
        """发起异步报表生成请求"""
        if open_browser:
            self.status_label.setText("正在加载报表...")
        QTimer.singleShot(0, lambda: self.logic.db_worker.fetch_stats(open_browser))

    def _on_stats_ready(self, rows, open_browser):
        """后台数据准备就绪后的渲染回调"""
        if self.logic.current_state == "stopped":
            self.status_label.setText("沉浸式学习")
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
            total_duration = 0.0
            for r in group_rows:
                try:
                    total_duration += float(r[2])
                except ValueError:
                    pass
            # 获取分类详情映射，用于区分显示风格
            cat_map = {cat['id']: cat for cat in self.category_manager.get_all_active()}
            
            sessions_html = ""
            for row in group_rows:
                start_time = row[0].split(' ')[-1] if ' ' in row[0] else row[0]
                end_time = row[1].split(' ')[-1] if ' ' in row[1] else row[1]
                duration = row[2]
                pause_count = row[5] if len(row) >= 8 else "0"
                pause_reasons_raw = row[6] if len(row) >= 8 else "无"
                summary = row[7] if len(row) >= 8 else "无记录"
                cat_id = row[8] if len(row) >= 9 else None
                
                # 判断是否为专注类（Pomodoro 模式）: 按组名或名称判断均有效
                cat_info = cat_map.get(cat_id, {})
                cat_name = cat_info.get("name", "")
                group_name = cat_info.get("group_name", "")
                is_pomodoro = group_name in ["输入", "输出"] or cat_name in ["输入", "输出"]
                
                if is_pomodoro:
                    # 专注类设计：保持原有明细布局（不使用 simplified 逻辑）
                    reasons_html = ""
                    if pause_reasons_raw and pause_reasons_raw != "无":
                        if "\n" in pause_reasons_raw or any(pause_reasons_raw.startswith(s) for s in ["- ", "+ ", "* ", "1. "]):
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
                else:
                    # 非专注类设计：极致简化布局
                    # 移除“总结”字样，如果是自动生成的摘要，直接展示
                    display_summary = summary
                    if "日常静默记录" in summary:
                        display_summary = summary.replace("日常静默记录", "").strip()
                    
                    remark_html = ""
                    if display_summary:
                        remark_html = f"<div class='card-remark'><strong>备注:</strong> {display_summary}</div>"
                    
                    sessions_html += f"""
                    <div class="session-item lifestyle">
                        <div class="session-header">
                            <span class="session-time">⏱️ {start_time} - {end_time}</span>
                            <span class="session-task">{summary.split('】')[0] + '】' if '】' in summary else ''}</span>
                            <span class="session-duration lifestyle-dur">{duration} 分钟</span>
                        </div>
                        {remark_html}
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
        html_content = self._build_stats_html(content_html)
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

    @staticmethod
    def _build_stats_html(content_html):
        """生成统计报表的完整 HTML"""
        return f"""<!DOCTYPE html>
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

    # ======================== 设置持久化 ========================

    def set_opacity(self, value):
        """设置窗口透明度"""
        self.settings.setValue("ui/opacity", value)
        self.update_stylesheet()

    def save_settings(self):
        """保存 UI 设置"""
        if self._init_failed:
            return
        self.settings.setValue("ui/geometry", self.saveGeometry())
        self.settings.setValue("ui/opacity", self.settings.value("ui/opacity", 0.8))
        self.settings.setValue("ui/alwaysOnTop", self.is_always_on_top)

    def load_settings(self):
        """加载 UI 设置"""
        geometry = self.settings.value("ui/geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self.resize(220, 120)
        self.update_total_time(self.logic.total_study_time)
