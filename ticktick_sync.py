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
from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, Dict

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from database import StudyLogger

logger = logging.getLogger(__name__)
CST = timezone(timedelta(hours=8)) 

class OfficialTickTickClient:
    def __init__(self, access_token: str, host: str = "dida365.com"):
        self.access_token = access_token
        self.base_url = f"https://api.{host}/open/v1"
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

    async def get_task(self, project_id: str, task_id: str):
        """查询单个任务详情，返回 None 表示查不到"""
        url = f"{self.base_url}/project/{project_id}/task/{task_id}"
        resp = await self.client.get(url)
        if resp.status_code == 200 and resp.text.strip():
            return resp.json()
        return None

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

    # ==================== 习惯 API ====================
    async def get_habits(self) -> list:
        """获取所有习惯"""
        resp = await self.client.get(f"{self.base_url}/habit")
        resp.raise_for_status()
        return resp.json()

    async def checkin_habit(self, habit_id: str, stamp: str, status: int = 0, value: float = 1.0):
        """习惯打卡 stamp 格式: YYYYMMDD, status: 0=完成 2=未完成"""
        url = f"{self.base_url}/habit/{habit_id}/checkin"
        payload = {"stamp": int(stamp), "status": status, "value": value}
        resp = await self.client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json() if resp.text else {}

    async def get_habit_checkins(self, habit_ids: list, from_stamp: str, to_stamp: str) -> list:
        """获取习惯打卡记录 habit_ids: list, stamps: YYYYMMDD"""
        params = {
            "habitIds": ",".join(habit_ids),
            "from": from_stamp,
            "to": to_stamp
        }
        resp = await self.client.get(f"{self.base_url}/habit/checkins", params=params)
        resp.raise_for_status()
        return resp.json()

    async def close(self):
        await self.client.aclose()

class TickTickSyncWorker(QObject):
    tasks_ready = pyqtSignal(list)
    sync_error = pyqtSignal(str)
    task_completed_ok = pyqtSignal(str)
    task_complete_failed = pyqtSignal(str, str)
    
    # 习惯信号
    habits_ready = pyqtSignal(list, dict)  # habits_list, checkins_map
    habits_sync_error = pyqtSignal(str)

    def __init__(self, config, category_manager=None):
        super().__init__()
        self.config = config
        self.category_manager = category_manager
        self.db_logger = StudyLogger(config)
        self._host = config.get("ticktick_config", {}).get("host", "dida365.com")
        
        self._project_map = {}
        self._cached_tasks = []
        
        # 初始化读取本地数据库缓存的未完成任务
        self._raw_task_map = {}   # task_id -> 原始 API 返回的全量数据
        try:
            for t in self.db_logger.get_all_active_tasks():
                self._raw_task_map[t["id"]] = t
        except: pass
        
        self._locally_completed: Set[str] = set()  # 本地已完成但 API 延迟未清除的 task_id
        self._client = None
        self._loop = None
        self._last_task_refresh_started_at: Optional[datetime] = None

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
            self.habits_sync_error.emit("未配置 TickTick access_token")
            return
        previous_refresh_started_at = self._last_task_refresh_started_at
        refresh_started_at = datetime.now(timezone.utc)
        try:
            tasks = self._run(self._fetch_all_tasks(token, previous_refresh_started_at))
            
            # 过滤掉本地已完成但 TickTick 端由于延迟还没清除的任务
            tasks = [t for t in tasks if t["id"] not in self._locally_completed]
            
            # 自动映射分类 ID 并持久化落盘
            self._persist_and_link_tasks(tasks)
            
            self._cached_tasks = tasks
            self.tasks_ready.emit(list(tasks))
            self._last_task_refresh_started_at = refresh_started_at
        except Exception as e:
            logger.error(f"TickTick 同步失败: {e}")
            self.sync_error.emit(f"同步失败: {e}")
        finally:
            self._refresh_habits_internal(token)

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

    async def _fetch_all_tasks(self, token: str, refresh_started_at: Optional[datetime] = None):
        client = OfficialTickTickClient(token, self._host)
        try:
            projects = await client.get_projects()
            self._project_map = {p["id"]: p["name"] for p in projects}
            tasks_data = await asyncio.gather(*[
                client.get_project_data(p["id"]) for p in projects
            ])

            result = []
            today_cst = datetime.now(CST).date()

            previous_map = getattr(self, '_raw_task_map', {})
            self._raw_task_map = {}

            for data in tasks_data:
                p_id = data.get("project", {}).get("id")
                p_name = self._project_map.get(p_id, "收集箱")
                for t in data.get("tasks", []):
                    if t.get("status", 0) != 0: continue  # 跳过已完成
                    due_date_str = t.get("dueDate")
                    if not due_date_str: continue  # 跳过无截止日期
                    try:
                        clean_date = due_date_str.replace("+0000", "Z")
                        due_dt = datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
                        due_cst = due_dt.astimezone(CST).date()
                    except:
                        continue
                    if due_cst <= today_cst:  # 今日及过期任务
                        task_id = t["id"]
                        self._raw_task_map[task_id] = t  # 缓存原始全量数据
                        result.append(self._task_to_dict(t, p_name))

            # 检查消失的任务，通过 API 二次确认是否真正完成
            if previous_map:
                current_ids = set(self._raw_task_map.keys())
                missing_ids = set(previous_map.keys()) - current_ids - self._locally_completed
                if missing_ids:
                    logger.info(f"[任务同步] 检测到 {len(missing_ids)} 个任务消失，开始逐个二次确认...")
                    await self._verify_missing_tasks(client, missing_ids, previous_map)

            return result
        finally:
            await client.close()

    async def _verify_missing_tasks(self, client: OfficialTickTickClient, missing_ids: set, previous_map: dict):
        """对消失的任务逐个调 API 二次确认，status=2 才发金币"""
        for task_id in missing_ids:
            old_task = previous_map.get(task_id, {})
            # 兼容原始 API 格式 (projectId) 和本地转换格式 (project_id)
            project_id = old_task.get("projectId") or old_task.get("project_id", "")
            title = old_task.get("title", "未知任务")

            if not project_id:
                logger.info(f"[任务确认] 跳过 {task_id}，无 projectId 缓存")
                continue

            try:
                task_detail = await client.get_task(project_id, task_id)
                if task_detail and task_detail.get("status") == 2:
                    # 确认是真正完成，写入 external_rewards 待领取
                    coins = self.db_logger.get_item_reward('task', task_id, 0.1)
                    ext_id = f"task_{task_id}"
                    self.db_logger.add_external_reward(ext_id, 'task', title, coins, status=0)
                    # 同时更新本地任务状态为已完成，防止下次启动再次扫描
                    self.db_logger.update_task_status(task_id, 2)
                    logger.info(f"[任务确认] ✅ 外部完成确认: {title} +{coins}🪙")
                else:
                    logger.info(f"[任务确认] ❌ 任务 {title} 非完成状态（可能被删除/推迟），不发金币")
                    # 更新本地状态为 4 (已忽略/验证失败)，避免下次启动重复检查
                    self.db_logger.update_task_status(task_id, 4)
            except Exception as e:
                logger.error(f"[任务确认] 查询任务 {task_id} 失败: {e}")

    def _task_to_dict(self, t, project_name) -> dict:
        today_cst = datetime.now(CST).date()
        due_str = "全天"
        due_date_full = ""
        is_overdue = False

        due_date_str = t.get("dueDate")
        if due_date_str:
            try:
                clean_date = due_date_str.replace("+0000", "Z")
                due_dt = datetime.fromisoformat(clean_date.replace("Z", "+00:00"))
                due_cst = due_dt.astimezone(CST)
                due_day = due_cst.date()
                is_overdue = due_day < today_cst

                if t.get("isAllDay"):
                    if due_day == today_cst:
                        due_date_full = "今天 全天"
                    else:
                        due_date_full = due_cst.strftime("%-m/%-d 全天") if hasattr(due_cst, 'strftime') else due_cst.strftime("%m/%d 全天")
                else:
                    time_str = due_cst.strftime("%H:%M")
                    due_str = time_str
                    if due_day == today_cst:
                        due_date_full = f"今天 {time_str}"
                    else:
                        # Windows strftime 不支持 %-m，用 lstrip('0') 模拟
                        m = str(due_cst.month)
                        d = str(due_cst.day)
                        due_date_full = f"{m}/{d} {time_str}"
            except:
                pass

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
            "due_date_full": due_date_full,
            "is_overdue": is_overdue,
            "is_completed": False,
        }

    @pyqtSlot(str, str)
    def complete_task(self, task_id, project_id):
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        try:
            # 加入本地已完成集合，防止刷新时因 API 延迟又把它拉回来
            self._locally_completed.add(task_id)
            
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
            self._locally_completed.discard(task_id)  # 失败时移出集合
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
        client = OfficialTickTickClient(token, self._host)
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
        client = OfficialTickTickClient(token, self._host)
        try:
            # 优先使用缓存的原始全量数据，避免多一次 GET 请求
            target_task = self._raw_task_map.get(task_id)
            
            if not target_task:
                # 缓存没有，从 API 拉取
                project_data = await client.get_project_data(project_id)
                tasks = project_data.get("tasks", [])
                target_task = next((t for t in tasks if t["id"] == task_id), None)
            
            if target_task:
                # 必须提供全量数据 + status=2 + completedTime
                # TickTick API 只传部分字段会静默忽略更新
                payload = dict(target_task)
                payload["status"] = 2
                payload["completedTime"] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000+0000')
                logger.info(f"[完成] 任务 '{payload.get('title', task_id)}' -> status=2")
                await client.update_task(project_id, task_id, payload)
            else:
                logger.warning(f"任务 {task_id} 在活动列表未找到，直接调用 complete 接口兜底")
                await client.complete_task(project_id, task_id)
        finally:
            await client.close()

    def cleanup(self):
        if self._loop and not self._loop.is_closed():
            self._loop.close()
            self._loop = None
        logger.info("TickTick Worker 资源已清理")

    # ==================== 习惯同步 ====================
    def _refresh_habits_internal(self, token):
        try:
            habits = self._run(self._do_fetch_habits(token))
            self._log_habit_status_distribution(habits)
            habits = [h for h in habits if self._is_visible_habit(h)]
            habits.sort(key=lambda h: h.get('sortOrder', 0))
            
            from datetime import datetime, timedelta
            # 使用 CST 时区确保日期计算与任务同步一致
            now_cst = datetime.now(CST)
            # to 参数通常是不包含结束日期的，为了获取今天的打卡记录，需传明天的日期
            tomorrow_stamp = (now_cst + timedelta(days=1)).strftime('%Y%m%d')
            start_of_week = now_cst - timedelta(days=now_cst.weekday())
            week_start_stamp = start_of_week.strftime('%Y%m%d')

            habit_ids = [h['id'] for h in habits]
            checkins_raw = self._run(self._do_fetch_checkins(token, habit_ids, week_start_stamp, tomorrow_stamp)) if habit_ids else []
            
            checkins_map = {}
            for block in checkins_raw:
                hid = block.get('habitId', '')
                if hid not in checkins_map:
                    checkins_map[hid] = {}
                
                # 获取习惯名称和奖励金币
                habit_name = next((h.get('name', '未知习惯') for h in habits if h['id'] == hid), '未知习惯')
                coins = self.db_logger.get_item_reward('habit', hid, 0.1)
                
                for ci in block.get('checkins', []):
                    stamp = str(ci.get('stamp', ''))
                    status = ci.get('status', -1)
                    checkins_map[hid][stamp] = status
                    
                    if status == 2:
                        # 写入 external_rewards（防重复逻辑在 SQL 层，如果本地点击过打卡，早已存为 status=1）
                        ext_id = f"habit_{hid}_{stamp}"
                        self.db_logger.add_external_reward(ext_id, 'habit', habit_name, coins, status=0)
                    
            self.habits_ready.emit(habits, checkins_map)
        except Exception as e:
            logger.error(f"后台拉取习惯数据失败: {e}")
            self.habits_sync_error.emit(f"习惯同步失败: {e}")

    def _log_habit_status_distribution(self, habits: list):
        status_counter = Counter(h.get("status", "missing") for h in habits)
        logger.info(f"[习惯同步] status 分布: {dict(status_counter)}")

    def _is_visible_habit(self, habit: dict) -> bool:
        status = habit.get("status", 0)
        if status in {0, 1}:
            return True
        logger.info(f"[习惯同步] 跳过非活跃习惯 {habit.get('id')} status={status} name={habit.get('name', '')}")
        return False

    def fetch_remote_habits(self) -> list:
        """同步获取远端习惯列表"""
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        if not token:
            return []
        try:
            return self._run(self._do_fetch_habits(token))
        except Exception as e:
            logger.error(f"获取远端习惯失败: {e}")
            return []

    async def _do_fetch_habits(self, token):
        client = OfficialTickTickClient(token, self._host)
        try:
            return await client.get_habits()
        finally:
            await client.close()

    @pyqtSlot(str, str, int)
    def sync_habit_checkin(self, habit_id: str, stamp: str, status: int = 0):
        """同步打卡到远端 (stamp 格式: YYYYMMDD, status: 0=完成 2=失败)"""
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        if not token:
            return
        try:
            self._run(self._do_checkin(token, habit_id, stamp, status))
        except Exception as e:
            logger.error(f"远端习惯打卡失败: {e}")

    async def _do_checkin(self, token, habit_id, stamp, status):
        client = OfficialTickTickClient(token, self._host)
        try:
            await client.checkin_habit(habit_id, stamp, status)
            logger.info(f"[习惯] 打卡同步成功 habit={habit_id} stamp={stamp} status={status}")
        finally:
            await client.close()

    def fetch_habit_checkins(self, habit_ids: list, from_stamp: str, to_stamp: str) -> list:
        """同步获取远端习惯打卡记录"""
        tt_cfg = self.config.get("ticktick_config", {})
        token = tt_cfg.get("access_token")
        if not token or not habit_ids:
            return []
        try:
            return self._run(self._do_fetch_checkins(token, habit_ids, from_stamp, to_stamp))
        except Exception as e:
            logger.error(f"获取远端打卡记录失败: {e}")
            return []

    async def _do_fetch_checkins(self, token, habit_ids, from_stamp, to_stamp):
        client = OfficialTickTickClient(token, self._host)
        try:
            return await client.get_habit_checkins(habit_ids, from_stamp, to_stamp)
        finally:
            await client.close()
