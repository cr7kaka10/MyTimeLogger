# -*- coding: utf-8 -*-
"""
快捷键模块 (hotkeys.py)
======================
全局快捷键管理:
- HotkeyManager: 基于 pynput 的全局热键监听器
  - 支持开始、暂停/恢复、重置轮次三个快捷键
  - 通过 Qt 信号与业务逻辑解耦
"""

import logging

from PyQt6.QtCore import QObject, pyqtSignal

# pynput 是可选依赖
try:
    from pynput import keyboard
except ImportError:
    keyboard = None


class HotkeyManager(QObject):
    """
    全局快捷键管理器。

    通过 pynput 监听系统级热键，触发时发射 Qt 信号。
    pynput 未安装时自动降级为无操作模式。

    Signals:
        start_triggered: 开始/恢复快捷键触发
        toggle_pause_triggered: 暂停/恢复切换快捷键触发
        reset_cycle_triggered: 重置轮次快捷键触发
    """
    start_triggered = pyqtSignal()
    toggle_pause_triggered = pyqtSignal()
    reset_cycle_triggered = pyqtSignal()
    toggle_checklist_triggered = pyqtSignal()
    toggle_activity_panel_triggered = pyqtSignal()

    def __init__(self, hotkey_config, parent=None):
        super().__init__(parent)
        if not keyboard:
            logging.warning("HotkeyManager: pynput 未安装，全局快捷键功能已禁用。")
            self.listener = None
            return

        self.hotkey_config = hotkey_config
        self.listener = None
        self.hotkey_map = {
            'start': self.start_triggered.emit,
            'toggle_pause': self.toggle_pause_triggered.emit,
            'reset_cycle': self.reset_cycle_triggered.emit,
            'toggle_checklist': self.toggle_checklist_triggered.emit,
            'toggle_activity_panel': self.toggle_activity_panel_triggered.emit,
        }

    def start(self):
        """启动快捷键监听器"""
        if not self.listener:
            try:
                pynput_map = {
                    self.hotkey_config[action]: callback
                    for action, callback in self.hotkey_map.items()
                    if action in self.hotkey_config and self.hotkey_config[action]
                }
                if not pynput_map:
                    print("未配置任何有效的快捷键。")
                    return

                self.listener = keyboard.GlobalHotKeys(pynput_map)
                self.listener.start()
                print(f"快捷键监听器已启动: {pynput_map.keys()}")
            except Exception as e:
                print(f"启动快捷键监听器失败: {e}. 请检查 config.json 中的快捷键格式。")
                self.listener = None

    def stop(self):
        """停止快捷键监听器"""
        if self.listener:
            self.listener.stop()
            self.listener = None
            print("快捷键监听器已停止。")
