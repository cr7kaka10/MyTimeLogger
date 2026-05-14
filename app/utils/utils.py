# -*- coding: utf-8 -*-
"""
工具模块 (utils.py)
==================
提供全局辅助函数:
- resource_path(): 资源路径解析，适配开发环境与 PyInstaller 打包
- setup_logging(): 日志系统初始化（控制台 + 按日轮转文件）
"""

import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime


def resource_path(relative_path):
    """
    获取资源绝对路径，适配开发环境和 PyInstaller 单文件/文件夹打包模式。

    分类规则:
    - 用户数据（配置/数据库/报表）→ 可执行文件同级目录（可写、持久化）
    - 内置资源（音频/图标）→ PyInstaller 临时解压目录（只读）

    Args:
        relative_path: 相对路径字符串，如 'config.json' 或 'study_music/start.mp3'

    Returns:
        拼接后的绝对路径
    """
    # 用户可写/持久化的数据文件列表
    user_data_files = [
        'config.json', 'study_log.db', 'study_log.json',
        'statistics.html', 'study_log.csv'
    ]

    if relative_path in user_data_files or relative_path.endswith('.db') or relative_path.endswith('.json'):
        # 用户数据：始终使用可执行文件所在的真实目录
        try:
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
            else:
                base_path = os.path.abspath(".")
        except Exception:
            base_path = os.path.abspath(".")
    else:
        # 只读资源：优先使用 PyInstaller 的临时解压目录
        try:
            base_path = sys._MEIPASS
        except Exception:
            base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def setup_logging():
    """
    初始化日志系统。

    - 控制台输出 + 文件输出（按天轮转，保留 30 天）
    - 日志目录为程序运行目录下的 log/ 子目录
    - 防止重复添加 Handler
    """
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    log_dir = os.path.join(base_dir, "log")

    try:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")

        logger = logging.getLogger()
        logger.setLevel(logging.INFO)

        # 防止重复添加 Handler
        if not logger.handlers:
            # 终端处理器
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(console_handler)

            # 文件处理器 (按天轮转，保留最近 30 天)
            file_handler = TimedRotatingFileHandler(
                log_file, when="midnight", interval=1, backupCount=30, encoding='utf-8'
            )
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            logger.addHandler(file_handler)

        logging.info("MyTimeLogger 日志系统初始化完成。")
    except Exception as e:
        print(f"日志初始化失败: {e}")
