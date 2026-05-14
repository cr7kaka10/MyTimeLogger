# -*- coding: utf-8 -*-
"""PC-side client for pulling completed server sleep analyses."""

import logging
from datetime import datetime

import os
import time
import httpx

from app.utils.config import save_config


logger = logging.getLogger(__name__)


def _parse_dt(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(value).split(".")[0], fmt)
        except ValueError:
            continue
    return None


class ServerSleepClient:
    def __init__(self, config):
        self.config = config
        self.sync_cfg = config.get("server_sleep_sync", {})
        self.base_url = (self.sync_cfg.get("base_url") or "").rstrip("/")
        self.auth_token = self.sync_cfg.get("auth_token") or ""
        self.timeout = httpx.Timeout(30.0, connect=10.0)

    def enabled(self):
        return bool(self.sync_cfg.get("enabled") and self.base_url and self.auth_token)

    def _headers(self):
        return {"X-Auth-Token": self.auth_token}

    def fetch_sync_data(self, since=None):
        if not self.enabled():
            return []
        params = {}
        if since:
            params["since"] = since
        with httpx.Client(timeout=self.timeout, verify=False) as client:
            resp = client.get(f"{self.base_url}/sync_data", params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json().get("data", [])

    def ack_sync(self, request_ids):
        if not request_ids or not self.enabled():
            return 0
        with httpx.Client(timeout=self.timeout, verify=False) as client:
            resp = client.post(
                f"{self.base_url}/ack_sync",
                json={"request_ids": request_ids},
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json().get("acked", 0)

    def upload_and_analyze(self, image_path, progress_callback=None):
        """上传图片并轮询结果"""
        if not self.enabled():
            raise Exception("server sync is not enabled or configured")

        with httpx.Client(timeout=self.timeout, verify=False) as client:
            # 1. 上传
            if progress_callback: progress_callback("正在上传至服务端...")
            with open(image_path, "rb") as f:
                files = {"file": (os.path.basename(image_path), f, "image/jpeg")}
                resp = client.post(f"{self.base_url}/upload", files=files, headers=self._headers())
            
            resp.raise_for_status()
            rid = resp.json().get("request_id")
            if not rid:
                raise Exception("Upload failed: No request_id returned")

            # 2. 轮询
            import time
            if progress_callback: progress_callback("服务端分析中...")
            for _ in range(30): # 最多等待 2 分钟
                time.sleep(4)
                resp = client.get(f"{self.base_url}/status/{rid}", headers=self._headers())
                resp.raise_for_status()
                data = resp.json()
                status = data.get("status")
                
                if status == "done":
                    return data.get("result") or {}
                if status == "error":
                    raise Exception(data.get("error") or "server analysis failed")
                
                msg = data.get("msg")
                if msg and progress_callback:
                    progress_callback(f"服务端进度: {msg}")
            
            raise Exception("server analysis timed out")

    def sync_once(self, db):
        if not self.enabled():
            return {"status": "disabled", "synced": 0, "message": "服务端睡眠同步未启用"}

        since = self.sync_cfg.get("last_sync_at") or ""
        items = self.fetch_sync_data(since)
        synced_ids = []
        max_updated_at = since

        for item in items:
            date_str = item.get("date")
            request_id = item.get("request_id")
            updated_at = item.get("updated_at") or ""
            sleep_data = item.get("sleep_data") or {}
            analysis_report = item.get("analysis_report") or sleep_data.get("analysis_report") or ""
            if not date_str or not request_id or not sleep_data:
                continue

            local = db.get_huawei_sleep_data(date_str)
            should_write = local is None
            if local is not None:
                server_dt = _parse_dt(updated_at)
                local_dt = _parse_dt(local.get("updated_at"))
                should_write = server_dt is not None and (local_dt is None or server_dt > local_dt)

            if should_write:
                merged = dict(sleep_data)
                if analysis_report:
                    merged["analysis_report"] = analysis_report
                local_reflection = (local or {}).get("sleep_reflection") if local else ""
                server_reflection = merged.get("sleep_reflection")
                if local_reflection and not server_reflection:
                    merged["sleep_reflection"] = local_reflection
                db.save_huawei_sleep_data(date_str, merged)

            synced_ids.append(request_id)
            if updated_at and (not max_updated_at or updated_at > max_updated_at):
                max_updated_at = updated_at

        if synced_ids:
            self.ack_sync(synced_ids)
        if max_updated_at and max_updated_at != since:
            self.config.setdefault("server_sleep_sync", {})["last_sync_at"] = max_updated_at
            save_config(self.config)

        return {
            "status": "ok",
            "synced": len(synced_ids),
            "message": f"服务端睡眠同步完成：{len(synced_ids)} 条",
            "last_sync_at": max_updated_at,
        }
