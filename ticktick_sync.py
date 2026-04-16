# -*- coding: utf-8 -*-
"""
TickTick 同步模块 (ticktick_sync.py) - 官方 Open API 版
======================================================
直接通过 TickTick 官方 Open API (v1) 进行同步，彻底移除非官方 SDK。
"""

import asyncio
import logging
import httpx
from datetime import datetime, timezone, timedelta

HAS_TICKTICK_SDK = True # 保持兼容性

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))  # 中国标准时间

class OfficialTickTickClient:
    """封装官方 Open API (v1) 的极简客户端"""
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.ticktick.com/open/v1"
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.client = httpx.AsyncClient(
            headers=self.headers, 
            timeout=15.0,
            follow_redirects=True,
            verify=False  # 绕过 Windows 下的 SSL 证书校验问题
        )

    async def get_projects(self) -> list:
        """获取所有项目"""
        resp = await self.client.get(f"{self.base_url}/project")
        resp.raise_for_status()
        return resp.json()

    async def get_project_data(self, project_id: str) -> dict:
        """获取指定项目的任务数据"""
        resp = await self.client.get(f"{self.base_url}/project/{project_id}/data")
        resp.raise_for_status()
        return resp.json()

    async def complete_task(self, project_id: str, task_id: str):
        """标记任务为完成"""
        url = f"{self.base_url}/project/{project_id}/task/{task_id}/complete"
        resp = await self.client.post(url)
        resp.raise_for_status()

    async def close(self):
        await self.client.aclose()

class TickTickSyncWorker(QObject):
    """TickTick 同步工作者，运行在 QThread 中。"""

    # 信号
    tasks_ready = pyqtSignal(list)              # 任务列表就绪
    sync_error = pyqtSignal(str)                # 同步错误
    task_completed_ok = pyqtSignal(str)         # 任务完成推送成功 (task_id)
    task_complete_failed = pyqtSignal(str, str) # 任务完成推送失败 (task_id, error)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self._project_map = {}   # project_id -> project_name
        self._cached_tasks = []  # 未完成今日任务缓存
        
        self._client = None
        self._loop = None

    # ==================== 缓存操作 ====================

    def get_cached_tasks(self) -> list:
        return list(self._cached_tasks)

    def remove_from_cache(self, task_id: str):
        self._cached_tasks = [t for t in self._cached_tasks if t["id"] != task_id]

    def add_to_cache(self, task_dict: dict):
        if not any(t["id"] == task_dict["id"] for t in self._cached_tasks):
            self._cached_tasks.append(task_dict)

    # ==================== Event Loop 管理 ====================

    def _ensure_loop(self):
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    def _run(self, coro):
        self._ensure_loop()
        return self._loop.run_until_complete(coro)

    # ==================== 刷新 ====================

    @pyqtSlot()
    def refresh(self):
        """拉取今日未完成任务"""
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        if not token:
            self.sync_error.emit("未配置 TickTick access_token")
            return

        try:
            tasks = self._run(self._fetch_all_tasks(token))
            # 增量对比
            if self._tasks_changed(tasks):
                self._cached_tasks = tasks
                self.tasks_ready.emit(list(tasks))
            else:
                logger.debug("TickTick 任务无变化")
        except Exception as e:
            logger.error(f"TickTick 同步失败: {e}")
            self.sync_error.emit(f"同步失败: {e}")

    async def _fetch_all_tasks(self, token: str):
        client = OfficialTickTickClient(token)
        try:
            projects = await client.get_projects()
            self._project_map = {p["id"]: p["name"] for p in projects}

            # 并发拉取各个项目的任务
            tasks_data = await asyncio.gather(*[
                client.get_project_data(p["id"]) for p in projects
            ])

            result = []
            today_cst = datetime.now(CST).date()

            for data in tasks_data:
                p_id = data.get("project", {}).get("id")
                p_name = self._project_map.get(p_id, "收集箱")
                
                for t in data.get("tasks", []):
                    # 过滤：未完成 (status=0)
                    if t.get("status", 0) != 0:
                        continue
                    
                    due_date_str = t.get("dueDate")
                    if not due_date_str:
                        continue
                    
                    # 转换时间（Open API 返回 ISO 格式字符串）
                    # 格式通常为: "2026-04-15T16:00:00.000+0000"
                    try:
                        # 兼容处理 TickTick 各种时间字符串
                        clean_date = due_date_str.replace("+0000", "Z")
                        due_dt = datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
                        due_cst = due_dt.astimezone(CST).date()
                    except Exception as ve:
                        logger.warning(f"解析时间失败: {due_date_str}, {ve}")
                        continue

                    if due_cst <= today_cst:
                        result.append(self._task_to_dict(t, p_name))

            return result
        finally:
            await client.close()

    def _task_to_dict(self, t, project_name) -> dict:
        """将 API 原始任务转为本地标准字典"""
        due_str = "全天"
        if not t.get("isAllDay"):
            due_date_str = t.get("dueDate")
            if due_date_str:
                try:
                    clean_date = due_date_str.replace("+0000", "Z")
                    due_dt = datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
                    due_str = due_dt.astimezone(CST).strftime("%H:%M")
                except:
                    pass

        return {
            "id": t["id"],
            "project_id": t["projectId"],
            "title": t["title"],
            "priority": t.get("priority", 0),
            "tags": t.get("tags", []),
            "project_name": project_name,
            "due_date": due_str,
            "is_completed": False,
        }

    def _tasks_changed(self, new_tasks: list) -> bool:
        if len(new_tasks) != len(self._cached_tasks):
            return True
        old_ids = {t["id"] for t in self._cached_tasks}
        new_ids = {t["id"] for t in new_tasks}
        return old_ids != new_ids

    # ==================== 完成任务 ====================

    @pyqtSlot(str, str)
    def complete_task(self, task_id, project_id):
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        try:
            self._run(self._do_complete(token, project_id, task_id))
            self.task_completed_ok.emit(task_id)
        except Exception as e:
            logger.error(f"完成任务失败: {e}")
            self.task_complete_failed.emit(task_id, str(e))

    async def _do_complete(self, token, project_id, task_id):
        client = OfficialTickTickClient(token)
        try:
            await client.complete_task(project_id, task_id)
        finally:
            await client.close()

    def cleanup(self):
        if self._loop and not self._loop.is_closed():
            self._loop.close()
            self._loop = None
        logger.info("TickTick Worker 资源已清理")
