# --- START OF FILE study_timer_gui.py ---

import time
import random
import os
import sys
import json
import pygame
import csv # <--- NEW: For writing log files
from datetime import datetime # <--- NEW: For timestamps

# --- PyQt6 Imports ---
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QSystemTrayIcon, QMessageBox, QSizeGrip, QInputDialog, QLineEdit, QPushButton
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QSettings
from PyQt6.QtGui import QIcon, QAction

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
        "victory": "victory.mp3"
    },
    "total_study_time": 0,
    "reset_password": "130130131",
    "hotkeys": {
        "start": "<alt>+z",
        "toggle_pause": "<alt>+c",
        "reset_cycle": "<ctrl>+<alt>+r"
    }
}

# --- 配置文件加载/创建函数 ---
def load_or_create_config():
    config_path = resource_path('config.json')
    if not os.path.exists(config_path):
        print("未找到 config.json, 正在创建默认配置文件...")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            return DEFAULT_CONFIG
        except Exception as e:
            print(f"创建默认配置文件失败: {e}")
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
                    for sub_k, sub_v in value.items():
                        if sub_k not in user_config[key]:
                            user_config[key][sub_k] = sub_v
                            updated = True
            if updated:
                print("配置文件已更新，添加了新字段。")
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
        print(f"错误: 保存配置文件失败: {e}")

# ==============================================================================
# 新增: 学习日志记录器
# ==============================================================================
class StudyLogger:
    def __init__(self, filename="study_log.csv"):
        self.log_path = resource_path(filename)
        self.header = [
            'start_time', 'end_time', 'net_duration_minutes', 'date', 'day_of_week', 
            'pause_count', 'pause_reasons', 'session_summary'
        ]
        self._initialize_file()

    def _initialize_file(self):
        """如果日志文件不存在，则创建并写入表头"""
        if not os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                print(f"日志文件已创建: {self.log_path}")
            except IOError as e:
                print(f"错误: 无法创建日志文件: {e}")

    def log_session(self, start_time: datetime, end_time: datetime, net_duration_seconds: int, pause_count: int = 0, pause_reasons: str = "", session_summary: str = ""):
        """记录一个完整的学习会话"""
        if not all([start_time, end_time, net_duration_seconds > 0]):
            return

        date_str = start_time.strftime('%Y-%m-%d')
        day_of_week = start_time.strftime('%A')
        net_duration_minutes = round(net_duration_seconds / 60, 2)

        row = [
            start_time.strftime('%Y-%m-%d %H:%M:%S'),
            end_time.strftime('%Y-%m-%d %H:%M:%S'),
            net_duration_minutes,
            date_str,
            day_of_week,
            pause_count,
            pause_reasons,
            session_summary
        ]

        try:
            with open(self.log_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except IOError as e:
            print(f"错误: 无法写入日志: {e}")


# ==============================================================================
# 核心逻辑层 (已修改)
# ==============================================================================
class StudyTimerLogic(QObject):
    state_changed = pyqtSignal(str, str)
    time_updated = pyqtSignal(int)
    notification_requested = pyqtSignal(str, str)
    input_reason_requested = pyqtSignal()
    input_summary_requested = pyqtSignal()
    session_logged = pyqtSignal()

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = StudyLogger()

        self.is_paused = False
        self.time_remaining_on_pause = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timer_timeout)

        pygame.mixer.init()
        self.sound_paths = self._validate_and_get_sound_paths()
        
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
            self.logger.log_session(
                start_time=self.large_session_start_time,
                end_time=end_time,
                net_duration_seconds=self.large_session_net_duration,
                pause_count=self.large_session_pause_count,
                pause_reasons=pause_reasons_str,
                session_summary=summary if summary else "无总结"
            )
            self.session_logged.emit()
        self._clear_large_session()
        self._run_long_break_cycle()
        
    def add_pause_reason(self, reason):
        if reason:
            self.pending_pause_reason = reason
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

    def _play_sound(self, sound_key):
        sound_path = self.sound_paths.get(sound_key)
        if not sound_path: return
        try:
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
        except pygame.error as e: print(f"播放音频时出错: {e}")

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
            print("警告: pynput 未安装，快捷键功能已禁用。")
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
class StudyTimerGUI(QWidget):
    def __init__(self, config):
        super().__init__()
        
        self.config = config
        
        try:
            self.logic = StudyTimerLogic(self.config)
        except FileNotFoundError as e:
            QMessageBox.critical(None, "资源错误", f"{e}\n\n请确保所有资源文件都在正确的位置，然后重启程序。")
            self._init_failed = True
            return
        self._init_failed = False
        
        self.dragPos = None
        self.is_locked = False
        
        self.settings = QSettings("MyStudyTimer", "App")
        
        self.is_always_on_top = self.settings.value("ui/alwaysOnTop", True, type=bool)

        self.create_tray_icon()
        
        self.hotkey_manager = HotkeyManager(self.config.get('hotkeys', {}))
        self.hotkey_manager.start_triggered.connect(self.logic.start_only)
        self.hotkey_manager.toggle_pause_triggered.connect(self.logic.toggle_pause)
        self.hotkey_manager.reset_cycle_triggered.connect(self.logic.reset_cycle)
        self.hotkey_manager.start()

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

        bg_layout = QVBoxLayout(self.background_widget)
        bg_layout.setContentsMargins(10, 10, 10, 0)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        
        self.total_time_label = QLabel()
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_time_label.setObjectName("total_time_label")
        
        bg_layout.addWidget(self.status_label)
        bg_layout.addWidget(self.total_time_label)
        bg_layout.addStretch()


        grip_layout = QHBoxLayout()
        grip_layout.setContentsMargins(0, 0, 0, 0)
        grip_layout.addStretch()
        self.size_grip = QSizeGrip(self.background_widget)
        grip_layout.addWidget(self.size_grip)
        bg_layout.addLayout(grip_layout)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.background_widget)

        self.load_settings()
        self.update_stylesheet()

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
        dialog = QInputDialog(self)
        dialog.setWindowTitle("暂停提醒")
        dialog.setLabelText("请输入本次暂停的原因: (直接回车代表无)")
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        def _focus():
            self._activate_dialog(dialog)
            le = dialog.findChild(QLineEdit)
            if le:
                le.setFocus()
        QTimer.singleShot(100, _focus)

        ok = dialog.exec()
        reason = dialog.textValue()
        self.logic.add_pause_reason(reason.strip() if ok and reason.strip() else "无")

    def prompt_for_session_summary(self):
        dialog = QInputDialog(self)
        dialog.setOption(QInputDialog.InputDialogOption.UsePlainTextEditForTextInput, True)
        dialog.setWindowTitle("大专注完成！")
        dialog.setLabelText("恭喜完成一段深度专注！请简单总结你做了哪些事：")
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)

        QTimer.singleShot(100, lambda: self._activate_dialog(dialog))

        ok = dialog.exec()
        summary = dialog.textValue()
        final_summary = summary.strip() if ok and summary.strip() else "未填写总结"
        self.logic.commit_large_session(final_summary)

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
            
            correct_pwd = "130130131"
            try:
                with open(resource_path('config.json'), 'r', encoding='utf-8') as f:
                    correct_pwd = json.load(f).get("reset_password", "130130131")
            except Exception:
                correct_pwd = self.config.get("reset_password", "130130131")
                
            if ok and pwd == correct_pwd:
                self.logic.reset_all()
                csv_path = self.logic.logger.log_path
                if os.path.exists(csv_path):
                    try:
                        os.remove(csv_path)
                    except Exception as e:
                        print(f"删除失败: {e}")
                self.logic.logger._initialize_file()
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
            
        config_menu.addMenu(interval_menu)
        config_menu.addMenu(duration_menu)
        config_menu.addMenu(hotkey_menu)

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
        self.background_widget.setStyleSheet(f"""
            #background {{ background-color: rgba(46, 52, 64, {opacity}); border-radius: 10px; {border_style} }}
            QLabel {{ background-color: transparent; color: #D8DEE9; font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif; font-size: 15px; }}
            #total_time_label {{ font-size: 26px; font-weight: bold; color: #00CED1; padding-top: 5px; letter-spacing: 2px; }}
            QSizeGrip {{ background-color: transparent; width: 15px; height: 15px; }}
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
                padding: 5px 14px;
                font-size: 13px;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif;
                font-weight: bold;
            }
            QPushButton#end_break_btn:hover {
                background-color: #D08770;
            }
        """)
        self.end_break_btn.clicked.connect(self.logic.end_break_now)
        # 插入到 total_time_label 下方
        bg_layout = self.background_widget.layout()
        bg_layout.insertWidget(2, self.end_break_btn, 0, Qt.AlignmentFlag.AlignCenter)
        self.end_break_btn.hide()

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
        self.tray_icon = QIcon(resource_path('icon.ico'))
        self.tray = QSystemTrayIcon(self.tray_icon, self)
        self.tray.setToolTip("沉浸式学习计时器")
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
        self.size_grip.setVisible(not self.is_locked)
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

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.toggle_mouse_penetration()

    def mousePressEvent(self, event):
        if not self.is_locked and event.button() == Qt.MouseButton.LeftButton:
            if self.size_grip.geometry().contains(event.pos()): return
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

    def generate_statistics_html(self, open_browser=False, *args):
        log_path = resource_path("study_log.csv")
        html_path = resource_path("statistics.html")
        
        rows = []
        if os.path.exists(log_path):
            try:
                with open(log_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    header = next(reader, None)
                    rows = list(reader)
            except Exception:
                pass
        
        week_map = {
            'Monday': '星期一', 'Tuesday': '星期二', 'Wednesday': '星期三',
            'Thursday': '星期四', 'Friday': '星期五', 'Saturday': '星期六', 'Sunday': '星期日'
        }

        cards_html = ""
        for row in reversed(rows[-100:]):
            if len(row) >= 5:
                start_time = row[0]
                end_time = row[1]
                duration = row[2]
                date_val = row[3]
                day_zh = week_map.get(row[4], row[4])
                
                pause_count = row[5] if len(row) >= 8 else "0"
                pause_reasons_raw = row[6] if len(row) >= 8 else "无"
                summary = row[7] if len(row) >= 8 else "无记录"
                
                reasons_html = ""
                if pause_reasons_raw and pause_reasons_raw != "无":
                    r_list = [r.strip() for r in pause_reasons_raw.split("; ") if r.strip()]
                    for r in r_list:
                        reasons_html += f"<span class='reason-tag'>{r}</span>"
                else:
                    reasons_html = "<span class='reason-tag-empty'>无暂停记录</span>"
                
                cards_html += f"""
                <div class="card">
                    <div class="card-header">
                        <span class="date-badge">{date_val} {day_zh}</span>
                        <span class="duration-badge">专注 {duration} 分钟</span>
                    </div>
                    <div class="card-time">⏱️ {start_time} - {end_time}</div>
                    <div class="card-stats">⏸️ 主动暂停: {pause_count} 次</div>
                    <div class="card-reasons">
                        <div style="margin-bottom:6px;"><strong>暂停明细:</strong></div>
                        <div class="reason-tags">{reasons_html}</div>
                    </div>
                    <div class="card-summary"><strong>专注总结:</strong> {summary}</div>
                </div>
                """
                
        content_html = cards_html if cards_html else "<div class='empty'>暂无大专注学习记录，快去开启第一次沉浸式学习吧！</div>"

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>StudyTimer 统计数据</title>
    <style>
        :root {{ --bg: #f3f4f6; --card-bg: #ffffff; --text: #1f2937; --text-light: #6b7280; --primary: #3b82f6; --accent: #10b981; --border: #e5e7eb; }}
        body {{ font-family: 'Segoe UI', system-ui, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 40px; line-height: 1.5; }}
        h1 {{ text-align: center; color: var(--primary); margin-bottom: 40px; font-weight: 700; letter-spacing: 1px; }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .card {{ background: var(--card-bg); border-radius: 16px; padding: 24px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -1px rgba(0,0,0,0.03); border: 1px solid var(--border); transition: transform 0.2s, box-shadow 0.2s; }}
        .card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05); }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 12px; }}
        .date-badge {{ font-weight: 600; color: var(--primary); font-size: 1.1em; }}
        .duration-badge {{ background: var(--accent); color: white; padding: 6px 12px; border-radius: 20px; font-size: 0.9em; font-weight: 600; box-shadow: 0 2px 4px rgba(16,185,129,0.2); }}
        .card-time {{ color: var(--text-light); font-size: 0.95em; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }}
        .card-stats {{ color: #eab308; font-size: 0.95em; margin-bottom: 12px; font-weight: 500; display: flex; align-items: center; gap: 6px; }}
        .card-reasons {{ background: var(--bg); padding: 16px; border-radius: 12px; margin-bottom: 12px; font-size: 0.95em; color: var(--text); border-left: 4px solid #f59e0b; box-shadow: inset 0 2px 4px 0 rgba(0,0,0,0.03); }}
        .reason-tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
        .reason-tag {{ background: #fef3c7; color: #b45309; padding: 4px 12px; border-radius: 16px; font-size: 0.85em; font-weight: 500; border: 1px solid #fde68a; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }}
        .reason-tag-empty {{ color: #9ca3af; font-size: 0.9em; font-style: italic; }}
        .card-summary {{ background: #eff6ff; padding: 16px; border-radius: 8px; font-size: 1em; color: #1e3a8a; border-left: 4px solid var(--primary); line-height: 1.6; }}
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
    if keyboard is None:
        error_app = QApplication(sys.argv)
        show_pynput_error()
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not os.path.exists(resource_path('icon.ico')):
        QMessageBox.critical(None, "资源错误", "关键文件 'icon.ico' 未找到！\n程序无法启动。")
        sys.exit(1)

    config = load_or_create_config()
    window = StudyTimerGUI(config)
    
    if window._init_failed:
        sys.exit(1)

    window.show()
    sys.exit(app.exec())
