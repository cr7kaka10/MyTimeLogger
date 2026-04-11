# -*- coding: utf-8 -*-
"""
核心逻辑模块 (logic.py)
======================
学习计时器的状态机与业务逻辑:
- MyTimeLoggerLogic: 管理学习/休息/暂停状态转换、音频播放、
  会话数据记录、异步数据库同步等核心功能
"""

import os
import copy
import random
import logging
from datetime import datetime

import pygame
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread

from utils import resource_path
from config import save_config
from database import StudyLogger, DatabaseWorker


class MyTimeLoggerLogic(QObject):
    """核心状态机，驱动学习计时器的所有业务流程。"""
    state_changed = pyqtSignal(str, str)
    time_updated = pyqtSignal(int)
    notification_requested = pyqtSignal(str, str)
    input_reason_requested = pyqtSignal()
    input_summary_requested = pyqtSignal()
    session_logged = pyqtSignal()
    _async_log_trigger = pyqtSignal(dict)
    _sync_trigger = pyqtSignal(dict)

    def __init__(self, config):
        super().__init__()
        self.config = config
        local_cfg = copy.deepcopy(config)
        local_cfg["db_type"] = "sqlite"
        self.local_logger = StudyLogger(local_cfg)

        self.db_thread = QThread()
        self.db_worker = DatabaseWorker(self.config)
        self.db_worker.moveToThread(self.db_thread)
        self._sync_trigger.connect(self.db_worker.sync_to_backup)
        self.db_thread.start()
        QTimer.singleShot(100, self.db_worker.init_db)

        self.is_paused = False
        self.time_remaining_on_pause = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timer_timeout)

        self._audio_initialized = False
        QTimer.singleShot(2000, self._async_init_audio)

        self.total_study_time = self.config.get("total_study_time", 0)
        self.current_cycle_study_time = 0
        self.large_session_start_time = None
        self.large_session_pause_count = 0
        self.large_session_pause_reasons = []
        self.large_session_net_duration = 0
        self.current_pause_start_time = None
        self.pending_pause_reason = "无"
        self.current_session_start_time = None
        self.current_session_duration = 0
        self.current_focus_task = ""  # 当前专注关联的任务名
        self.reset_cycle()

    def _clear_large_session(self):
        """清空大专注会话的所有状态"""
        self.large_session_start_time = None
        self.large_session_pause_count = 0
        self.large_session_pause_reasons = []
        self.large_session_net_duration = 0
        self.current_pause_start_time = None
        self.pending_pause_reason = "无"

    def _clear_current_session(self):
        """清空当前微轮次的临时记录"""
        self.current_session_start_time = None
        self.current_session_duration = 0

    def reset_cycle(self):
        """重置当前轮次"""
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
        """彻底重置全部数据"""
        self.total_study_time = 0
        self.reset_cycle()
        self.time_updated.emit(self.total_study_time)

    def on_timer_timeout(self):
        """计时器超时统一回调"""
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

    def _run_study_cycle(self):
        """启动一轮学习计时"""
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
        if self.current_cycle_study_time > 0:
            self._play_sound("start_study")
        self.timer.setProperty("duration", study_duration)
        self.timer.start(study_duration * 1000)

    def load_persistent_time(self, total_study_time):
        """从配置加载持久化的累计学习时长"""
        self.total_study_time = total_study_time
        self.time_updated.emit(self.total_study_time)

    def _validate_and_get_sound_paths(self):
        """校验音效文件是否齐全"""
        folder_path = resource_path(self.config["music_folder"])
        if not os.path.isdir(folder_path):
            raise FileNotFoundError(f"资源文件夹未找到: {folder_path}")
        paths = {}
        for key, filename in self.config["sound_files"].items():
            path = os.path.join(folder_path, filename)
            if not os.path.isfile(path):
                raise FileNotFoundError(f"音频文件未找到: {path}")
            paths[key] = path
        return paths

    def _async_init_audio(self):
        """异步初始化音频引擎"""
        try:
            pygame.mixer.init()
            self.sound_paths = self._validate_and_get_sound_paths()
            self._audio_initialized = True
        except Exception as e:
            logging.error(f"音频初始化失败: {e}")

    def _play_sound(self, sound_key):
        """播放指定音效"""
        if not self._audio_initialized:
            return
        sound_path = self.sound_paths.get(sound_key)
        if not sound_path:
            return
        try:
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
        except pygame.error as e:
            logging.error(f"播放音频时出错: {e}")

    def start_only(self):
        """仅在停止或长休息结束状态下启动"""
        if self.current_state in ["stopped", "long_break_finished"]:
            self.is_paused = False
            if self.current_state == "long_break_finished":
                self.reset_cycle()
            if self.current_cycle_study_time >= self.config["long_break_threshold"]:
                self._run_long_break_cycle()
            else:
                self._run_study_cycle()

    def start_with_context(self, task_name):
        """启动专注并关联任务名。

        如果已在专注中（studying），仅更新关联任务名，不重置周期。
        如果未在专注中，等同于 start_only() + 设置任务名。
        """
        self.current_focus_task = task_name or ""
        if self.current_state in ["stopped", "long_break_finished"]:
            self.start_only()
        logging.info(f"专注关联任务: {task_name}")

    def toggle_pause(self):
        """切换暂停/恢复状态"""
        if self.is_paused:
            self._resume()
        elif self.timer.isActive():
            self.pause()
            if self.current_state == "studying":
                self.input_reason_requested.emit()

    def start_or_resume(self):
        """启动或恢复"""
        self.start_only()

    def _run_short_break_cycle(self):
        """启动短休息"""
        self.current_state = "short_breaking"
        break_duration = self.config["short_break_duration"]
        self.state_changed.emit("☕ 短暂休息中...", self.current_state)
        self.time_updated.emit(self.total_study_time)
        self._play_sound("start_short_break")
        self.timer.setProperty("duration", 0)
        self.timer.start(break_duration * 1000)

    def _run_long_break_cycle(self):
        """启动长休息"""
        self.current_state = "long_breaking"
        break_duration = self.config["long_break_duration"]
        self.state_changed.emit("🧘 长时间休息...", self.current_state)
        self.time_updated.emit(self.total_study_time)
        self._play_sound("start_long_break")
        self.current_cycle_study_time = 0
        self.timer.setProperty("duration", 0)
        self.timer.start(break_duration * 1000)

    def pause(self):
        """暂停当前计时"""
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
        """恢复暂停的计时"""
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

    def _finish_long_break(self):
        """结束长休息"""
        self.timer.stop()
        self._play_sound("end_long_break")
        self.current_state = "long_break_finished"
        self.state_changed.emit("🎉 长休息结束\n右键开始新征程", self.current_state)
        self.notification_requested.emit("长休息结束", "精力恢复！可以开始下一轮学习了。")

    def end_break_now(self):
        """手动结束当前休息"""
        if self.current_state == "short_breaking":
            self.timer.stop()
            self._run_study_cycle()
        elif self.current_state == "long_breaking":
            self._finish_long_break()

    def commit_large_session(self, summary):
        """提交大专注会话数据"""
        if self.large_session_start_time and self.large_session_net_duration > 0:
            end_time = datetime.now()
            pause_reasons_str = "; ".join(self.large_session_pause_reasons) if self.large_session_pause_reasons else "无"
            # 如果有关联的专注任务，拼接为总结前缀
            final_summary = summary if summary else "无总结"
            if self.current_focus_task:
                final_summary = f"【{self.current_focus_task}】{final_summary}"
            log_data = {
                "start_time": self.large_session_start_time,
                "end_time": end_time,
                "net_duration_seconds": self.large_session_net_duration,
                "pause_count": self.large_session_pause_count,
                "pause_reasons": pause_reasons_str,
                "session_summary": final_summary
            }
            self.local_logger.log_session(**log_data)
            self._sync_trigger.emit(log_data)
            logging.info(f"大专注会话已提交! 纯时长: {self.large_session_net_duration}s, 暂停: {self.large_session_pause_count}次, 摘要: {summary[:50]}...")
            self.session_logged.emit()
        self._clear_large_session()
        self._run_long_break_cycle()

    def add_pause_reason(self, reason):
        """记录暂停原因"""
        if reason:
            self.pending_pause_reason = reason
            logging.info(f"记录暂停原因: {reason}")
        else:
            self.pending_pause_reason = "无"

    def stop(self):
        """停止计时器和音频引擎"""
        self.timer.stop()
        pygame.mixer.quit()
