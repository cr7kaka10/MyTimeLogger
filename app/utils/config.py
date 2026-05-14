# -*- coding: utf-8 -*-
"""
配置模块 (config.py)
===================
管理应用程序的配置:
- DEFAULT_CONFIG: 全部配置项的默认值定义
- load_or_create_config(): 加载 config.json，缺失时自动创建并补全字段
- save_config(): 将当前配置持久化到 config.json
"""

import json
import logging

from PyQt6.QtWidgets import QMessageBox

from .utils import resource_path

# ========== 默认配置 ==========
# 所有可配置项的默认值，首次运行时会以此生成 config.json
DEFAULT_CONFIG = {
    "study_time_min": 5 * 60,          # 单轮学习最短时长（秒）
    "study_time_max": 7 * 60,          # 单轮学习最长时长（秒）
    "short_break_duration": 10,        # 短休息时长（秒）
    "long_break_threshold": 90 * 60,   # 触发长休息的累计学习时长阈值（秒）
    "long_break_duration": 20 * 60,    # 长休息时长（秒）
    "music_folder": "assets/music",    # 音效资源文件夹
    "sound_files": {                   # 各场景音效文件名
        "start_short_break": "start_short_break.mp3",
        "start_long_break": "start_long_break.mp3",
        "end_long_break": "end_long_break.mp3",
        "victory": "victory.mp3",
        "start_study": "start_study.mp3"
    },
    "total_study_time": 0,             # 持久化的累计学习时长（秒）
    "reset_password": "111",           # 清空记录鉴权密码
    "hotkeys": {                       # 全局快捷键
        "toggle_pause": "<alt>+c",
        "toggle_activity_panel": "<alt>+z"
    },
    "db_type": "sqlite",               # 数据库类型: sqlite / mysql
    "mysql_config": {                  # MySQL 远程配置（// 前缀为注释状态，不启用）
        "//host": "127.0.0.1",
        "//user": "root",
        "//password": "your_password",
        "//database": "mytimelogger",
        "//port": 3306
    },
    "ticktick_config": {               # TickTick 日清单同步配置
        "enabled": False,
        "host": "ticktick.com",
        "client_id": "",
        "client_secret": "",
        "access_token": "",
        "username": "",
        "password": "",
        "sync_interval": 300
    },
    "ai_model_config": {               # AI 模型配置
        "vision_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "vision_api_key": "",
        "vision_model": "glm-4v-flash",
        
        "text_base_url": "https://open.bigmodel.cn/api/paas/v4",
        "text_api_key": "",
        "text_model": "glm-4-flash"
    },
    "cloud_sleep_sync": {              # 云端睡眠分析同步配置
        "enabled": False,
        "base_url": "",
        "auth_token": "",
        "sync_interval_sec": 300,
        "last_sync_at": ""
    }
}


def load_or_create_config():
    """
    加载配置文件，不存在则创建默认配置。

    特性:
    - 自动补全缺失的配置字段（向后兼容）
    - 兼容旧版快捷键字段名（start_resume → start, pause → toggle_pause）
    - 对 mysql_config 采用保守补充策略，避免覆盖用户手动填写的内容

    Returns:
        dict: 完整的配置字典
    """
    import os
    config_path = resource_path('config.json')

    if not os.path.exists(config_path):
        logging.info("未找到 config.json, 正在创建默认配置文件...")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            return DEFAULT_CONFIG
        except Exception as e:
            logging.error(f"创建默认配置文件失败: {e}")
            return DEFAULT_CONFIG

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            updated = False

            # 兼容旧版快捷键字段名
            if "hotkeys" in user_config:
                hk = user_config["hotkeys"]
                if "start_resume" in hk and "start" not in hk:
                    hk["start"] = hk.pop("start_resume")
                    updated = True
                if "pause" in hk and "toggle_pause" not in hk:
                    hk["toggle_pause"] = hk.pop("pause")
                    updated = True
                for k, v in DEFAULT_CONFIG["hotkeys"].items():
                    if k not in hk:
                        hk[k] = v
                        updated = True

            # 补全缺失的顶层字段
            for key, value in DEFAULT_CONFIG.items():
                if key not in user_config:
                    user_config[key] = value
                    updated = True
                elif isinstance(value, dict) and isinstance(user_config.get(key), dict):
                    is_mysql = (key == "mysql_config")
                    for sub_k, sub_v in value.items():
                        clean_sub_k = sub_k.lstrip("/")
                        user_has_keys = [k.lstrip("/") for k in user_config[key].keys()]
                        if clean_sub_k not in user_has_keys:
                            # mysql_config 且用户已有配置项时，不再补充默认的 // 模板项
                            if is_mysql and len(user_has_keys) > 0:
                                continue
                            user_config[key][sub_k] = sub_v
                            updated = True

            if updated:
                logging.info("配置文件已更新关键字段。")
                save_config(user_config)
            return user_config

    except (json.JSONDecodeError, TypeError) as e:
        QMessageBox.warning(
            None, "配置解析错误",
            f"读取 config.json 失败（很可能是您修改时的格式有误，如漏掉引号或逗号）:\n{e}\n\n程序已自动暂时重置为默认配置。"
        )
        return DEFAULT_CONFIG


def save_config(config_data):
    """
    将配置字典写入 config.json。

    Args:
        config_data: 要保存的配置字典
    """
    config_path = resource_path('config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logging.error(f"保存配置文件失败: {e}")
