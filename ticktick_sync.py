# -*- coding: utf-8 -*-
"""
TickTick 同步模块 (ticktick_sync.py)
====================================
将 ticktick-sdk 的异步 API 封装为 Qt 信号驱动的同步接口。
运行在独立 QThread 中，包含本地缓存，支持后台自动同步。

v2.0 改进：
- 持久化 TickTickClient 连接，复用 httpx session
- QThread 内常驻 asyncio event loop，避免反复创建/销毁
- 增量对比：任务列表无变化时不触发 UI 重渲染
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

    v2.0：持久化连接 + 增量对比
    - 首次 refresh 时建立连接并保持
    - 后续 refresh 复用同一个 client
    - 只在任务列表有变化时才发 tasks_ready 信号
    """

    # 信号
    tasks_ready = pyqtSignal(list)              # 任务列表就绪（有变化时）
    sync_error = pyqtSignal(str)                # 同步错误
    task_completed_ok = pyqtSignal(str)         # 任务完成推送成功 (task_id)
    task_complete_failed = pyqtSignal(str, str) # 任务完成推送失败 (task_id, error)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._project_map = {}   # project_id -> project_name 缓存
        self._cached_tasks = []  # 未完成今日任务缓存 list[dict]

        # 持久化连接相关
        self._client = None      # TickTickClient 实例
        self._loop = None        # 常驻 asyncio event loop
        self._connected = False  # 连接状态标记

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

    # ==================== Event Loop 管理 ====================

    def _ensure_loop(self):
        """确保有一个常驻的 event loop"""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    def _run(self, coro):
        """在常驻 event loop 中运行协程（不关闭 loop）"""
        self._ensure_loop()
        return self._loop.run_until_complete(coro)

    # ==================== 连接管理 ====================

    def _setup_env(self):
        """从 config 设置环境变量供 ticktick-sdk 使用"""
        tt_cfg = self.config.get("ticktick_config", {})
        os.environ["TICKTICK_CLIENT_ID"] = tt_cfg.get("client_id", "")
        os.environ["TICKTICK_CLIENT_SECRET"] = tt_cfg.get("client_secret", "")
        os.environ["TICKTICK_ACCESS_TOKEN"] = tt_cfg.get("access_token", "")
        os.environ["TICKTICK_USERNAME"] = tt_cfg.get("username", "")
        os.environ["TICKTICK_PASSWORD"] = tt_cfg.get("password", "")
        os.environ["TICKTICK_REDIRECT_URI"] = "http://127.0.0.1:9988"

    async def _ensure_connected(self):
        """确保 client 已连接，未连接则建立连接"""
        if self._client is not None and self._connected:
            return

        # 关闭旧连接（如果有）
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass

        self._setup_env()
        self._client = TickTickClient.from_settings()
        await self._client.connect()
        self._connected = True
        logger.info("TickTick 持久连接已建立")

    async def _disconnect(self):
        """断开连接"""
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None
            self._connected = False
            logger.info("TickTick 连接已断开")

    # ==================== 刷新 ====================

    @pyqtSlot()
    def refresh(self):
        """拉取今日未完成任务，增量对比后发信号"""
        if not HAS_TICKTICK_SDK:
            self.sync_error.emit("ticktick-sdk 未安装，请运行: pip install ticktick-sdk")
            return

        tt_cfg = self.config.get("ticktick_config", {})
        if not tt_cfg.get("access_token"):
            self.sync_error.emit("未配置 TickTick access_token，请先完成授权。")
            return

        try:
            tasks = self._run(self._fetch_today_uncompleted())
            # 增量对比：只有变化时才通知 UI
            if self._tasks_changed(tasks):
                self._cached_tasks = tasks
                self.tasks_ready.emit(list(tasks))
            else:
                logger.debug("TickTick 任务无变化，跳过 UI 刷新")
        except Exception as e:
            logger.error(f"TickTick 同步失败: {e}", exc_info=True)
            # 连接失效，标记断开以便下次重连
            self._connected = False
            self.sync_error.emit(f"同步失败: {e}")

    def _tasks_changed(self, new_tasks: list) -> bool:
        """对比新旧任务列表是否有变化"""
        if len(new_tasks) != len(self._cached_tasks):
            return True
        old_ids = {t["id"] for t in self._cached_tasks}
        new_ids = {t["id"] for t in new_tasks}
        if old_ids != new_ids:
            return True
        # ID 集合相同，检查内容是否变化（标题、优先级等）
        old_map = {t["id"]: t for t in self._cached_tasks}
        for t in new_tasks:
            old = old_map.get(t["id"])
            if old is None:
                return True
            if (old["title"] != t["title"] or
                old["priority"] != t["priority"] or
                old["due_date"] != t["due_date"] or
                old.get("tags") != t.get("tags")):
                return True
        return False

    async def _fetch_today_uncompleted(self):
        """异步拉取今日未完成任务（复用持久连接）。

        筛选规则：
        - status 不在 (2=completed, 3=abandoned)
        - due_date（转为 CST）<= 今天
        """
        await self._ensure_connected()

        # 项目映射
        projects = await self._client.get_all_projects()
        self._project_map = {p.id: p.name for p in projects}

        # 全部未完成任务
        all_tasks = await self._client.get_all_tasks()
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
        """推送完成任务到 TickTick（复用持久连接）"""
        if not HAS_TICKTICK_SDK:
            self.task_complete_failed.emit(task_id, "ticktick-sdk 未安装")
            return
        try:
            self._run(self._do_complete(task_id, project_id))
            self.task_completed_ok.emit(task_id)
        except Exception as e:
            logger.error(f"完成任务失败: {e}", exc_info=True)
            self._connected = False
            self.task_complete_failed.emit(task_id, str(e))

    async def _do_complete(self, task_id, project_id):
        await self._ensure_connected()
        await self._client.complete_task(task_id=task_id, project_id=project_id)

    # ==================== 清理 ====================

    def cleanup(self):
        """清理资源：断开连接、关闭 event loop"""
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.run_until_complete(self._disconnect())
            except Exception:
                pass
            self._loop.close()
            self._loop = None
        logger.info("TickTick Worker 资源已清理")
