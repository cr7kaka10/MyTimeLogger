# -*- coding: utf-8 -*-
"""Create a Docker .env file from local config.json without printing secrets."""

import json
import os
import secrets


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCAL_CONFIG = os.path.join(ROOT, "config.json")
SKILL_CONFIG = os.path.join(ROOT, "skills", "time-management", "config.json")
ENV_PATH = os.path.join(ROOT, ".env")


def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def line(key, value):
    value = "" if value is None else str(value)
    value = value.replace("\n", "").replace("\r", "")
    return f"{key}={value}"


def main():
    cfg = load_json(LOCAL_CONFIG)
    skill_cfg = load_json(SKILL_CONFIG)
    ai = cfg.get("ai_model_config", {})
    atm = skill_cfg.get("atimelogger", {})

    values = {
        "SLEEP_server_PORT": "8000",
        "SLEEP_AUTH_TOKEN": secrets.token_urlsafe(32),
        "server_SLEEP_DB_PATH": "/app/server_data/server_sleep_jobs.db",
        "VISION_BASE_URL": ai.get("vision_base_url", "https://open.bigmodel.cn/api/paas/v4"),
        "VISION_API_KEY": ai.get("vision_api_key", ""),
        "VISION_MODEL": ai.get("vision_model", "glm-4v-flash"),
        "TEXT_BASE_URL": ai.get("text_base_url", ai.get("vision_base_url", "https://open.bigmodel.cn/api/paas/v4")),
        "TEXT_API_KEY": ai.get("text_api_key", ai.get("vision_api_key", "")),
        "TEXT_MODEL": ai.get("text_model", "glm-4-flash"),
        "BACKUP_BASE_URL": ai.get("backup_base_url", ""),
        "BACKUP_API_KEY": ai.get("backup_api_key", ""),
        "BACKUP_MODEL": ai.get("backup_model", ""),
        "ATIMELOGGER_BASE_URL": atm.get("base_url", "https://app.atimelogger.pro"),
        "ATIMELOGGER_USERNAME": atm.get("username", ""),
        "ATIMELOGGER_PASSWORD": atm.get("password", ""),
        "HUAWEI_HEALTH_DATA_DIR": "/app/server_data/huawei_health_data",
        "WECHAT_WEBHOOK_URL": skill_cfg.get("wechat", {}).get("webhook_url", ""),
        "WECHAT_ENABLED": str(skill_cfg.get("wechat", {}).get("enabled", False)).lower(),
    }

    with open(ENV_PATH, "w", encoding="utf-8") as file:
        file.write("\n".join(line(k, v) for k, v in values.items()))
        file.write("\n")

    print(".env created. SLEEP_AUTH_TOKEN generated and local AI config copied.")


if __name__ == "__main__":
    main()
