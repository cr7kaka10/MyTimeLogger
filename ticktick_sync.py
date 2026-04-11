# -*- coding: utf-8 -*-
"""
TickTick 同步模块 (ticktick_sync.py)
====================================
将 ticktick-sdk 的异步 API 封装为 Qt 信号驱动的同步接口，
运行在独立 QThread 中，支持拉取今日任务和完成/取消完成操作。
"""

import os
import asyncio
import logging
from datetime import date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))  # 中国标准时间

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)

try:
    from ticktick_sdk import TickTickClient
    HAS_TICKTICK_SDK = True
except ImportError:
    HAS_TICKTICK_SDK = False


class TickTickSyncWorker(QObject):
    """TickTick 同步工作者，运行在 QThread 中"""

    # 信号
    tasks_ready = pyqtSignal(list)          # 任务列表就绪
    sync_error = pyqtSignal(str)            # 错误消息
    task_updated = pyqtSignal(str, bool)    # (task_id, is_completed)
    task_update_failed = pyqtSignal(str, bool, str)  # (task_id, original_state, error)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._project_map = {}  # project_id -> project_name 缓存

    def _setup_env(self):
        """从 config 设置环境变量供 ticktick-sdk 使用"""
        tt_cfg = self.config.get("ticktick_config", {})
        os.environ["TICKTICK_CLIENT_ID"] = tt_cfg.get("client_id", "")
        os.environ["TICKTICK_CLIENT_SECRET"] = tt_cfg.get("client_secret", "")
        os.environ["TICKTICK_ACCESS_TOKEN"] = tt_cfg.get("access_token", "")
        os.environ["TICKTICK_USERNAME"] = tt_cfg.get("username", "")
        os.environ["TICKTICK_PASSWORD"] = tt_cfg.get("password", "")
        os.environ["TICKTICK_REDIRECT_URI"] = "http://127.0.0.1:8080/callback"

    def _run_async(self, coro):
        """在当前线程中运行异步协程"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    @pyqtSlot()
    def refresh(self):
        """拉取今日任务列表"""
        if not HAS_TICKTICK_SDK:
            self.sync_error.emit("ticktick-sdk 未安装，请运行: pip install ticktick-sdk")
            return

        tt_cfg = self.config.get("ticktick_config", {})
        if not tt_cfg.get("access_token"):
            self.sync_error.emit("未配置 TickTick access_token，请先完成授权。")
            return

        try:
            self._setup_env()
            tasks = self._run_async(self._fetch_today_tasks())
            self.tasks_ready.emit(tasks)
        except Exception as e:
            logger.error(f"TickTick 同步失败: {e}", exc_info=True)
            self.sync_error.emit(f"同步失败: {e}")

    async def _fetch_today_tasks(self):
        """异步获取今日任务。

        与 TickTick「今天」视图一致的规则：
        - 未完成任务中：due_date（CST）<= 今天
        - 已完成任务中：今天完成的
        TickTick 存储时区为 UTC，is_all_day=True 时实际代表北京时间当天 00:00，
        存为前一天 16:00 UTC，所以必须先转 CST 再比日期。
        """
        async with TickTickClient.from_settings() as client:
            # 获取项目映射
            projects = await client.get_all_projects()
            self._project_map = {p.id: p.name for p in projects}

            # 获取全部未完成任务
            all_tasks = await client.get_all_tasks()
            today_cst = datetime.now(CST).date()

            # 过滤：未完成 + due_date（CST）<= 今天
            uncompleted_today = []
            for t in all_tasks:
                if getattr(t, 'status', 0) in (2, 3):  # 2=completed, 3=abandoned
                    continue
                due = getattr(t, 'due_date', None)
                if due is None:
                    continue
                # 转为 CST 日期
                if hasattr(due, 'tzinfo') and due.tzinfo:
                    due_cst_date = due.astimezone(CST).date()
                else:
                    due_cst_date = due.date()
                if due_cst_date <= today_cst:
                    uncompleted_today.append(t)

            # 获取今日已完成的任务
            completed_tasks = []
            try:
                recent_completed = await client.get_completed_tasks(days=1, limit=200)
                for t in recent_completed:
                    due = getattr(t, 'due_date', None)
                    if not due:
                        continue
                    if hasattr(due, 'tzinfo') and due.tzinfo:
                        due_cst_date = due.astimezone(CST).date()
                    else:
                        due_cst_date = due.date()
                    if due_cst_date <= today_cst:
                        completed_tasks.append(t)
            except Exception as e:
                logger.warning(f"获取已完成任务失败: {e}")

            result = []
            seen_ids = set()

            for task in uncompleted_today:
                if task.id in seen_ids:
                    continue
                seen_ids.add(task.id)
                result.append(self._task_to_dict(task, is_completed=False))

            for task in completed_tasks:
                if task.id in seen_ids:
                    continue
                seen_ids.add(task.id)
                result.append(self._task_to_dict(task, is_completed=True))

            return result

    def _task_to_dict(self, task, is_completed=False):
        """将 Task 对象转为标准字典"""
        due_str = ""
        due_date = getattr(task, 'due_date', None)
        is_all_day = getattr(task, 'is_all_day', True)
        if due_date and isinstance(due_date, datetime):
            # 转为 CST 再判断是否是全天任务
            due_cst = due_date.astimezone(CST) if due_date.tzinfo else due_date
            if is_all_day:
                due_str = "全天"
            else:
                # 非全天才显示时间
                due_str = due_cst.strftime("%H:%M")
        elif isinstance(due_date, str):
            due_str = due_date

        return {
            "id": task.id,
            "project_id": task.project_id or "",
            "title": task.title or "",
            "priority": getattr(task, 'priority', 0) or 0,
            "tags": list(getattr(task, 'tags', []) or []),
            "project_name": self._project_map.get(task.project_id, "收集箱"),
            "due_date": due_str,
            "is_completed": is_completed or getattr(task, 'status', 0) == 2,
        }

    @pyqtSlot(str, str)
    def complete_task(self, task_id, project_id):
        """完成任务"""
        if not HAS_TICKTICK_SDK:
            self.task_update_failed.emit(task_id, False, "ticktick-sdk 未安装")
            return
        try:
            self._setup_env()
            self._run_async(self._do_complete(task_id, project_id))
            self.task_updated.emit(task_id, True)
        except Exception as e:
            logger.error(f"完成任务失败: {e}", exc_info=True)
            self.task_update_failed.emit(task_id, False, str(e))

    async def _do_complete(self, task_id, project_id):
        async with TickTickClient.from_settings() as client:
            await client.complete_task(task_id=task_id, project_id=project_id)

    @pyqtSlot(str, str)
    def uncomplete_task(self, task_id, project_id):
        """取消完成（恢复任务）"""
        if not HAS_TICKTICK_SDK:
            self.task_update_failed.emit(task_id, True, "ticktick-sdk 未安装")
            return
        try:
            self._setup_env()
            self._run_async(self._do_uncomplete(task_id, project_id))
            self.task_updated.emit(task_id, False)
        except Exception as e:
            logger.error(f"取消完成失败: {e}", exc_info=True)
            self.task_update_failed.emit(task_id, True, str(e))

    async def _do_uncomplete(self, task_id, project_id):
        async with TickTickClient.from_settings() as client:
            task = await client.get_task(task_id=task_id)
            task.status = 0
            await client.update_task(task)
