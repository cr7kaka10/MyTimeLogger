# -*- coding: utf-8 -*-
"""
MyTimeLogger - 沉浸式学习计时器
===============================
程序主入口。负责:
- 初始化日志系统
- 单实例锁定检测
- 依赖检查（pynput）
- 加载配置并启动 GUI

模块结构:
  app/utils/utils.py    - 资源路径解析 + 日志初始化
  app/utils/config.py   - 配置加载/保存
  app/models/database.py - 数据库存储层 (SQLite/MySQL)
  app/ui/dialogs.py  - 自定义对话框组件
  app/core/logic.py    - 核心状态机与业务逻辑
  app/core/hotkeys.py  - 全局快捷键管理
  app/ui/gui.py      - 图形界面层
"""

import os
import sys

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QLockFile
from PyQt6.QtGui import QFontDatabase

from app.utils.utils import resource_path, setup_logging
from app.utils.config import load_or_create_config
from app.ui.gui import MyTimeLoggerGUI

# pynput 缺失时的友好提示
try:
    from pynput import keyboard
except ImportError:
    keyboard = None

def show_pynput_error():
    """显示 pynput 缺失的错误提示"""
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setText("缺少关键组件: pynput")
    msg_box.setInformativeText("快捷键功能无法使用。\n请在命令行中运行 'pip install pynput' 来安装它。")
    msg_box.setWindowTitle("依赖缺失")
    msg_box.exec()

# 初始化日志
setup_logging()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    from PyQt6.QtGui import QFont
    app.setFont(QFont("Microsoft YaHei", 9))

    # 单实例锁定检测
    lock_path = resource_path("my_time_logger.lock")
    lock_file = QLockFile(lock_path)
    if not lock_file.tryLock(100):
        QMessageBox.warning(None, "程序已在运行", "MyTimeLogger 已经在后台运行中了，请检查系统托盘或任务栏。")
        sys.exit(0)

    if keyboard is None:
        show_pynput_error()

    app.setQuitOnLastWindowClosed(False)

    # 注册内置矢量图标
    fa_path = resource_path(os.path.join("assets", "fonts", "fa-solid-900.ttf"))
    if os.path.exists(fa_path):
        QFontDatabase.addApplicationFont(fa_path)

    if not os.path.exists(resource_path(os.path.join('assets', 'icons', 'icon.ico'))):
        QMessageBox.critical(None, "资源错误", "关键文件 'assets/icons/icon.ico' 未找到！\n程序无法启动。")
        sys.exit(1)

    config = load_or_create_config()
    window = MyTimeLoggerGUI(config)

    if window._init_failed:
        sys.exit(1)

    window.setWindowTitle("MyTimeLogger v0.98")
    window.switch_ui_mode(to_mini=False)
    sys.exit(app.exec())
