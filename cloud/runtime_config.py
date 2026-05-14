# -*- coding: utf-8 -*-
"""Runtime config helpers for Docker/cloud sleep analysis mode."""

import json
import os
import secrets


def env(name, default=""):
    return os.getenv(name, default)


def build_root_config():
    return {
        "db_type": "sqlite",
        "ai_model_config": {
            "vision_base_url": env("VISION_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            "vision_api_key": env("VISION_API_KEY"),
            "vision_model": env("VISION_MODEL", "glm-4v-flash"),
            "text_base_url": env("TEXT_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            "text_api_key": env("TEXT_API_KEY"),
            "text_model": env("TEXT_MODEL", "glm-4-flash"),
            "backup_base_url": env("BACKUP_BASE_URL"),
            "backup_api_key": env("BACKUP_API_KEY"),
            "backup_model": env("BACKUP_MODEL"),
        },
    }


def build_skill_config():
    return {
        "atimelogger": {
            "base_url": env("ATIMELOGGER_BASE_URL", "https://app.atimelogger.pro"),
            "username": env("ATIMELOGGER_USERNAME"),
            "password": env("ATIMELOGGER_PASSWORD"),
        },
        "huawei_health": {
            "data_directory": env("HUAWEI_HEALTH_DATA_DIR", "/app/cloud_data/huawei_health_data"),
        },
        "wechat": {
            "webhook_url": env("WECHAT_WEBHOOK_URL"),
            "enabled": env("WECHAT_ENABLED", "false").lower() in ("1", "true", "yes"),
        },
    }


def write_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)


def ensure_cloud_runtime_config(base_dir=None):
    """Create minimal config files needed by generate_full_report in containers."""
    base_dir = base_dir or os.path.abspath(".")
    if os.getenv("MYTIMELOGGER_CLOUD_MODE", "").lower() not in ("1", "true", "yes"):
        return
    overwrite = os.getenv("CLOUD_RUNTIME_OVERWRITE", "").lower() in ("1", "true", "yes")

    root_config_path = os.path.join(base_dir, "config.json")
    skill_config_path = os.path.join(base_dir, "cloud", "skills", "time-management", "config.json")

    if overwrite or not os.path.exists(root_config_path):
        write_json(root_config_path, build_root_config())
    if overwrite or not os.path.exists(skill_config_path):
        write_json(skill_config_path, build_skill_config())


def generate_token():
    return secrets.token_urlsafe(32)
