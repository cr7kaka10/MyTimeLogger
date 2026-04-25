# -*- coding: utf-8 -*-
"""
TickTick 同步模块 (ticktick_sync.py) - 增强持久化版
======================================================
1. 直接通过 TickTick 官方 Open API (v1) 进行同步。
2. 将同步到的任务落盘存入本地数据库 tasks 表。
3. 利用 CategoryManager 缓存实现标签到分类 ID 的自动映射。
"""

import asyncio
import logging
import httpx
import json
from datetime import datetime, timezone, timedelta

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from database import StudyLogger

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8)) 

class OfficialTickTickClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.ticktick.com/open/v1"
        self.headers = {"Authorization": f"Bearer {access_token}"}
        self.client = httpx.AsyncClient(
            headers=self.headers, 
            timeout=15.0,
            follow_redirects=True,
            verify=False 
        )

    async def get_projects(self) -> list:
        resp = await self.client.get(f"{self.base_url}/project")
        resp.raise_for_status()
        return resp.json()

    async def get_project_data(self, project_id: str) -> dict:
        resp = await self.client.get(f"{self.base_url}/project/{project_id}/data")
        resp.raise_for_status()
        return resp.json()

    async def complete_task(self, project_id: str, task_id: str):
        url = f"{self.base_url}/project/{project_id}/task/{task_id}/complete"
        resp = await self.client.post(url)
        resp.raise_for_status()

    async def update_task(self, project_id: str, task_id: str, data: dict):
        # 官方推荐路径，必须使用 POST /task/{task_id}
        url = f"{self.base_url}/task/{task_id}"
        logger.info(f"[API] 正在更新任务: {task_id}, 项目: {project_id}, Payload keys: {list(data.keys())}")
        resp = await self.client.post(url, json=data)
        
        if resp.status_code != 200:
            logger.error(f"[API] 更新失败! 状态码: {resp.status_code}, 内容: {resp.text}")
        
        resp.raise_for_status()
        logger.info(f"[API] 任务 {task_id} 更新成功")

    async def close(self):
        await self.client.aclose()

class TickTickSyncWorker(QObject):
    tasks_ready = pyqtSignal(list)
    sync_error = pyqtSignal(str)
    task_completed_ok = pyqtSignal(str)
    task_complete_failed = pyqtSignal(str, str)

    def __init__(self, config, category_manager=None):
        super().__init__()
        self.config = config
        self.category_manager = category_manager
        self.db_logger = StudyLogger(config)
        
        self._project_map = {}
        self._cached_tasks = []
        self._client = None
        self._loop = None

    def _ensure_loop(self):
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

    def _run(self, coro):
        self._ensure_loop()
        return self._loop.run_until_complete(coro)

    def get_cached_tasks(self) -> list:
        return list(self._cached_tasks)

    def remove_from_cache(self, task_id: str):
        self._cached_tasks = [t for t in self._cached_tasks if t["id"] != task_id]

    @pyqtSlot()
    def refresh(self):
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        if not token:
            self.sync_error.emit("未配置 TickTick access_token")
            return
        try:
            tasks = self._run(self._fetch_all_tasks(token))
            
            # 自动映射分类 ID 并持久化落盘
            self._persist_and_link_tasks(tasks)
            
            self._cached_tasks = tasks
            self.tasks_ready.emit(list(tasks))
        except Exception as e:
            logger.error(f"TickTick 同步失败: {e}")
            self.sync_error.emit(f"同步失败: {e}")

    def _persist_and_link_tasks(self, tasks: list):
        """将获取到的任务映射 ID 并存入数据库"""
        if not self.category_manager:
            return
            
        all_active = self.category_manager.get_all_active()
        for t in tasks:
            # 自动查找匹配的分类 ID
            tags = t.get("tags", [])
            matched_id = None
            for tag in tags:
                matched_id = self.category_manager.get_id_by_name(tag)
                if matched_id: break
            
            t["category_id"] = matched_id
            # 写入本地数据库
            self.db_logger.upsert_task(t)

    async def _fetch_all_tasks(self, token: str):
        client = OfficialTickTickClient(token)
        try:
            projects = await client.get_projects()
            self._project_map = {p["id"]: p["name"] for p in projects}
            tasks_data = await asyncio.gather(*[
                client.get_project_data(p["id"]) for p in projects
            ])

            result = []
            today_cst = datetime.now(CST).date()

            for data in tasks_data:
                p_id = data.get("project", {}).get("id")
                p_name = self._project_map.get(p_id, "收集箱")
                for t in data.get("tasks", []):
                    if t.get("status", 0) != 0: continue
                    due_date_str = t.get("dueDate")
                    if not due_date_str: continue
                    try:
                        clean_date = due_date_str.replace("+0000", "Z")
                        due_dt = datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
                        due_cst = due_dt.astimezone(CST).date()
                    except:
                        continue
                    if due_cst <= today_cst:
                        result.append(self._task_to_dict(t, p_name))
            return result
        finally:
            await client.close()

    def _task_to_dict(self, t, project_name) -> dict:
        due_str = "全天"
        if not t.get("isAllDay"):
            due_date_str = t.get("dueDate")
            if due_date_str:
                try:
                    clean_date = due_date_str.replace("+0000", "Z")
                    due_dt = datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
                    due_str = due_dt.astimezone(CST).strftime("%H:%M")
                except: pass
        tags = t.get("tags", [])
        return {
            "id": t["id"],
            "project_id": t["projectId"],
            "title": t["title"],
            "priority": t.get("priority", 0),
            "status": t.get("status", 0),
            "tags": tags,
            "project_name": project_name,
            "due_date": due_str,
            "is_completed": False,
        }

    @pyqtSlot(str, str)
    def complete_task(self, task_id, project_id):
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        try:
            self._run(self._do_complete(token, project_id, task_id))
            
            # 更新本地数据库状态
            try:
                for t in self._cached_tasks:
                    if t["id"] == task_id:
                        t["status"] = 2
                        self.db_logger.upsert_task(t)
                        break
            except Exception as dbe:
                logger.error(f"更新本地数据库完成状态失败: {dbe}")

            self.task_completed_ok.emit(task_id)
        except Exception as e:
            logger.error(f"完成任务失败: {e}")
            self.task_complete_failed.emit(task_id, str(e))

    @pyqtSlot(str, str, int)
    def update_priority(self, task_id, project_id, priority):
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        try:
            # 强制转换为 int 类型，防止数据类型混叠导致 API 500 错误
            priority_val = int(priority)
            
            # 1. 更新本地缓存
            for t in self._cached_tasks:
                if t["id"] == task_id:
                    t["priority"] = priority_val
                    break
            
            # 2. 更新云端 (使用更鲁棒的 payload)
            self._run(self._do_update(token, project_id, task_id, {"priority": priority_val}))
            
            # 3. 更新数据库
            for t in self._cached_tasks:
                if t["id"] == task_id:
                    self.db_logger.upsert_task(t)
                    break
                    
            logger.info(f"任务 {task_id} 优先级本地更新已就绪，正在同步云端")
            # 成功后重新触发一次局部刷新，确保 UI 完全同步
            self.tasks_ready.emit(list(self._cached_tasks))
        except Exception as e:
            logger.error(f"更新优先级失败: {e}")
            self.sync_error.emit(f"更新失败: {e}")

    async def _do_update(self, token, project_id, task_id, data):
        client = OfficialTickTickClient(token)
        try:
            project_data = await client.get_project_data(project_id)
            tasks = project_data.get("tasks", [])
            target_task = next((t for t in tasks if t["id"] == task_id), None)
            if not target_task:
                raise ValueError(f"未在项目 {project_id} 中找到任务 {task_id}")
            
            for k, v in data.items():
                target_task[k] = v
                
            await client.update_task(project_id, task_id, target_task)
        finally:
            await client.close()

    async def _do_complete(self, token, project_id, task_id):
        client = OfficialTickTickClient(token)
        try:
            project_data = await client.get_project_data(project_id)
            tasks = project_data.get("tasks", [])
            target_task = next((t for t in tasks if t["id"] == task_id), None)
            
            if target_task:
                target_task["status"] = 2
                await client.update_task(project_id, task_id, target_task)
            else:
                logger.warning(f"任务 {task_id} 在活动列表未找到，直接调用 complete 兜底")
                await client.complete_task(project_id, task_id)
        finally:
            await client.close()

    def cleanup(self):
        if self._loop and not self._loop.is_closed():
            self._loop.close()
            self._loop = None
        logger.info("TickTick Worker 资源已清理")
