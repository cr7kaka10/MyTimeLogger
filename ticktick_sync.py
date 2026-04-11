# -*- coding: utf-8 -*-
"""
TickTick 同步模块 (ticktick_sync.py)
====================================
将 ticktick-sdk 的异步 API 封装为 Qt 信号驱动的同步接口。
运行在独立 QThread 中，包含本地缓存，支持后台自动同步。

缓存策略：
- 只缓存未完成的今日任务
- 本地操作（完成）直接更新缓存，后台异步推送
- 推送失败时发信号让 UI 回滚
"""

import os
import asyncio
import logging
from datetime import date, datetime, timezone, timedelta

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))  # 中国标准时间

try:
    from ticktick_sdk import TickTickClient
    HAS_TICKTICK_SDK = True
except ImportError:
    HAS_TICKTICK_SDK = False


class TickTickSyncWorker(QObject):
    """TickTick 同步工作者，运行在 QThread 中。

    包含本地缓存：只存未完成的今日任务。
    本地操作直接更新缓存，后台异步推送到 TickTick。
    """

    # 信号
    tasks_ready = pyqtSignal(list)              # 任务列表就绪（完整刷新）
    sync_error = pyqtSignal(str)                # 同步错误
    task_completed_ok = pyqtSignal(str)         # 任务完成推送成功 (task_id)
    task_complete_failed = pyqtSignal(str, str) # 任务完成推送失败 (task_id, error)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._project_map = {}   # project_id -> project_name 缓存
        self._cached_tasks = []  # 未完成今日任务缓存 list[dict]

    # ==================== 缓存操作 ====================

    def get_cached_tasks(self) -> list:
        """返回当前缓存的任务列表（副本）"""
        return list(self._cached_tasks)

    def remove_from_cache(self, task_id: str):
        """从缓存中移除指定任务（乐观更新时调用）"""
        self._cached_tasks = [t for t in self._cached_tasks if t["id"] != task_id]

    def add_to_cache(self, task_dict: dict):
        """将任务加回缓存（推送失败回滚时调用）"""
        if not any(t["id"] == task_dict["id"] for t in self._cached_tasks):
            self._cached_tasks.append(task_dict)

    # ==================== 环境 / 工具 ====================

    def _setup_env(self):
        """从 config 设置环境变量供 ticktick-sdk 使用"""
        tt_cfg = self.config.get("ticktick_config", {})
        os.environ["TICKTICK_CLIENT_ID"] = tt_cfg.get("client_id", "")
        os.environ["TICKTICK_CLIENT_SECRET"] = tt_cfg.get("client_secret", "")
        os.environ["TICKTICK_ACCESS_TOKEN"] = tt_cfg.get("access_token", "")
        os.environ["TICKTICK_USERNAME"] = tt_cfg.get("username", "")
        os.environ["TICKTICK_PASSWORD"] = tt_cfg.get("password", "")
        os.environ["TICKTICK_REDIRECT_URI"] = "http://127.0.0.1:9988"

    def _run_async(self, coro):
        """在当前线程中运行异步协程"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    # ==================== 刷新 ====================

    @pyqtSlot()
    def refresh(self):
        """拉取今日未完成任务，更新缓存并发出 tasks_ready 信号"""
        if not HAS_TICKTICK_SDK:
            self.sync_error.emit("ticktick-sdk 未安装，请运行: pip install ticktick-sdk")
            return

        tt_cfg = self.config.get("ticktick_config", {})
        if not tt_cfg.get("access_token"):
            self.sync_error.emit("未配置 TickTick access_token，请先完成授权。")
            return

        try:
            self._setup_env()
            tasks = self._run_async(self._fetch_today_uncompleted())
            self._cached_tasks = tasks
            self.tasks_ready.emit(list(tasks))
        except Exception as e:
            logger.error(f"TickTick 同步失败: {e}", exc_info=True)
            self.sync_error.emit(f"同步失败: {e}")

    async def _fetch_today_uncompleted(self):
        """异步拉取今日未完成任务（不含已完成）。

        筛选规则：
        - status 不在 (2=completed, 3=abandoned)
        - due_date（转为 CST）<= 今天
        """
        async with TickTickClient.from_settings() as client:
            # 项目映射
            projects = await client.get_all_projects()
            self._project_map = {p.id: p.name for p in projects}

            # 全部未完成任务
            all_tasks = await client.get_all_tasks()
            today_cst = datetime.now(CST).date()

            result = []
            for t in all_tasks:
                if getattr(t, 'status', 0) in (2, 3):  # 跳过已完成 / 已放弃
                    continue
                due = getattr(t, 'due_date', None)
                if due is None:
                    continue
                # 时区转换后比较日期
                if hasattr(due, 'tzinfo') and due.tzinfo:
                    due_cst = due.astimezone(CST).date()
                else:
                    due_cst = due.date()
                if due_cst <= today_cst:
                    result.append(self._task_to_dict(t))

            return result

    def _task_to_dict(self, task) -> dict:
        """将 Task 对象转为标准字典"""
        due_str = ""
        due_date = getattr(task, 'due_date', None)
        is_all_day = getattr(task, 'is_all_day', True)
        if due_date and isinstance(due_date, datetime):
            due_cst = due_date.astimezone(CST) if due_date.tzinfo else due_date
            due_str = "全天" if is_all_day else due_cst.strftime("%H:%M")
        elif isinstance(due_date, str):
            due_str = due_date

        return {
            "id": task.id,
            "project_id": task.project_id or "",
            "title": (task.title or "").strip(),
            "priority": getattr(task, 'priority', 0) or 0,
            "tags": list(getattr(task, 'tags', []) or []),
            "project_name": self._project_map.get(task.project_id, "收集箱"),
            "due_date": due_str,
            "is_completed": False,
        }

    # ==================== 完成任务 ====================

    @pyqtSlot(str, str)
    def complete_task(self, task_id, project_id):
        """推送完成任务到 TickTick（缓存已在调用侧乐观更新）"""
        if not HAS_TICKTICK_SDK:
            self.task_complete_failed.emit(task_id, "ticktick-sdk 未安装")
            return
        try:
            self._setup_env()
            self._run_async(self._do_complete(task_id, project_id))
            self.task_completed_ok.emit(task_id)
        except Exception as e:
            logger.error(f"完成任务失败: {e}", exc_info=True)
            self.task_complete_failed.emit(task_id, str(e))

    async def _do_complete(self, task_id, project_id):
        async with TickTickClient.from_settings() as client:
            await client.complete_task(task_id=task_id, project_id=project_id)
