# -*- coding: utf-8 -*-
"""
日清单模块 (daily_checklist.py) - 增强同步版
==========================================
独立浮动手持窗口，支持与主面板实时的播放状态联动。
"""

import logging
from datetime import date

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QCheckBox, QPushButton, QFrame, QDialog, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QFont, QColor

from ticktick_sync import TickTickSyncWorker

logger = logging.getLogger(__name__)

# ==================== 亮色主题配色 ====================
TEXT_PRIMARY = "#2E3440"   
TEXT_SECONDARY = "#4C566A" 
BORDER_COLOR = "#D8DEE9"   
SAPPHIRE_BLUE = "#5E81AC"  
SAPPHIRE_HOVER = "#81A1C1"
BG_LIGHT = "#FFFFFF"       
ITEM_HOVER_BG = "rgba(94, 129, 172, 0.05)"

PRIORITY_MAP = {
    5: ("⏫ 高", "#BF616A", "rgba(191,97,106,0.1)"),
    3: ("🔶 中", "#D08770", "rgba(208,135,112,0.1)"),
    1: ("🔽 低", "#5E81AC", "rgba(94,129,172,0.1)"),
    0: ("── 无", "#4C566A", "rgba(76,86,106,0.05)"),
}

class TaskItemWidget(QFrame):
    """单个任务项 Widget（增强版：带状态联功的播放按钮）"""

    focus_clicked = pyqtSignal(dict)
    complete_clicked = pyqtSignal(dict)

    def __init__(self, task_data: dict, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.is_active = False   # 是否是当前专注的任务
        self.is_paused = False   # 若是当前任务，是否处于暂停态
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("taskItem")
        self._update_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # 第一行
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(22, 22)
        self.checkbox.setStyleSheet(self._checkbox_style())
        self.checkbox.stateChanged.connect(self._on_check_changed)

        self.title_label = QLabel(self.task_data["title"])
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet(f"QLabel {{ color: {TEXT_PRIMARY}; font-size: 14px; font-weight: 500; }}")

        # 播放/暂停按钮（FA 图标）
        self.play_btn = QPushButton("\uf04b") # Default Play
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.clicked.connect(lambda: self.focus_clicked.emit(self.task_data))
        self._update_play_btn_style()

        row1.addWidget(self.checkbox)
        row1.addWidget(self.title_label, 1)
        row1.addWidget(self.play_btn)
        layout.addLayout(row1)

        # 第二行
        row2 = QHBoxLayout()
        row2.setContentsMargins(30, 0, 0, 0)
        row2.setSpacing(6)

        priority = self.task_data.get("priority", 0)
        p_text, p_color, p_bg = PRIORITY_MAP.get(priority, PRIORITY_MAP[0])
        priority_label = QLabel(p_text)
        priority_label.setStyleSheet(
            f"QLabel {{ font-size: 11px; padding: 1px 8px; border-radius: 4px; "
            f"background: {p_bg}; color: {p_color}; font-weight: bold; border: 1px solid {p_color}40; }}"
        )
        row2.addWidget(priority_label)

        project_name = self.task_data.get("project_name", "")
        if project_name and project_name != "收集箱":
            proj_label = QLabel(f"📁 {project_name}")
            proj_label.setStyleSheet(f"QLabel {{ font-size: 11px; padding: 1px 8px; border-radius: 4px; background: #F0F2F5; color: #5E81AC; border: 1px solid {BORDER_COLOR}; }}")
            row2.addWidget(proj_label)

        for tag in self.task_data.get("tags", []):
            tag_label = QLabel(f"🏷 {tag}")
            tag_label.setStyleSheet(f"QLabel {{ font-size: 10px; padding: 1px 6px; border-radius: 4px; background: #E5E9F0; color: {TEXT_SECONDARY}; }}")
            row2.addWidget(tag_label)

        due = self.task_data.get("due_date", "")
        if due and due != "全天":
            due_label = QLabel(f"⏰ {due}")
            due_label.setStyleSheet("QLabel { font-size: 11px; color: #BF616A; font-weight: bold; }")
            row2.addWidget(due_label)

        row2.addStretch()
        layout.addLayout(row2)

    def _update_style(self):
        border_c = SAPPHIRE_BLUE if self.is_active else BORDER_COLOR
        bg_c = ITEM_HOVER_BG if self.is_active else "transparent"
        self.setStyleSheet(f"#taskItem {{ background: {bg_c}; border-radius: 8px; border: 1px solid {border_c}; }} #taskItem:hover {{ background: #F8F9FB; }}")

    def _checkbox_style(self):
        return f"QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 3px; border: 2px solid {BORDER_COLOR}; background: white; }} QCheckBox::indicator:hover {{ border-color: {SAPPHIRE_BLUE}; }} QCheckBox::indicator:checked {{ background: {SAPPHIRE_BLUE}; border-color: {SAPPHIRE_BLUE}; }}"

    def _update_play_btn_style(self):
        # 根据状态显示图标
        if self.is_active and not self.is_paused:
            self.play_btn.setText("\uf04c") # Pause
            color = "#D08770" # 橙红色
        else:
            self.play_btn.setText("\uf04b") # Play
            color = SAPPHIRE_BLUE
        
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: 'Font Awesome 6 Free'; font-weight: 900; font-size: 16px;
                background: {color}15; color: {color}; border: 1px solid {color}40; border-radius: 16px;
            }}
            QPushButton:hover {{ background: {color}; color: white; }}
        """)

    def set_sync_state(self, is_active: bool, is_paused: bool):
        self.is_active = is_active
        self.is_paused = is_paused
        self._update_style()
        self._update_play_btn_style()

    def _on_check_changed(self, state):
        if state == Qt.CheckState.Checked.value:
            self.complete_clicked.emit(self.task_data)

class DailyChecklistWindow(QWidget):
    """日清单窗口（状态联动版）"""
    def __init__(self, config, logic=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.logic = logic
        self.settings = QSettings("MyTimeLogger", "DailyChecklist")
        self.task_widgets = {}
        self.current_focus_task_id = None
        
        self.setWindowTitle("今日清单")
        self.setFixedSize(400, 520)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dragPos = None

        self._init_worker()
        self._build_ui()
        self._load_position()

        # 连接逻辑信号，实现实时状态联动
        if self.logic:
            self.logic.state_changed.connect(self._on_logic_state_changed)

        interval = self.config.get("ticktick_config", {}).get("sync_interval", 300)
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(interval * 1000)
        self.auto_refresh_timer.timeout.connect(self._do_refresh)

    def _init_worker(self):
        self.sync_thread = QThread()
        self.sync_worker = TickTickSyncWorker(self.config)
        self.sync_worker.moveToThread(self.sync_thread)
        self.sync_worker.tasks_ready.connect(self._on_tasks_ready)
        self.sync_worker.sync_error.connect(self._on_sync_error)
        self.sync_worker.task_completed_ok.connect(self._on_task_completed_ok)
        self.sync_worker.task_complete_failed.connect(self._on_task_complete_failed)
        self.sync_thread.start()

    def _build_ui(self):
        self.bg = QFrame(self)
        self.bg.setObjectName("checklistBg")
        self.bg.setGeometry(0, 0, 400, 520)
        self.bg.setStyleSheet(f"#checklistBg {{ background-color: rgba(255, 255, 255, 0.98); border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}")

        layout = QVBoxLayout(self.bg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)
        title_label = QLabel("📋 <b>今日清单</b>")
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-family: 'Microsoft YaHei';")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        btn_style = f"QPushButton {{ color: {TEXT_SECONDARY}; background: transparent; font-size: 16px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {SAPPHIRE_BLUE}; }}"
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(30,30)
        self.refresh_btn.clicked.connect(self._do_refresh)
        self.refresh_btn.setStyleSheet(btn_style)
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.clicked.connect(self.hide)
        close_btn.setStyleSheet(btn_style)

        header_layout.addWidget(self.refresh_btn)
        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.task_layout = QVBoxLayout(self.container)
        self.task_layout.setContentsMargins(15, 10, 15, 10)
        self.task_layout.setSpacing(10)
        self.task_layout.addStretch()
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.status_bar = QLabel("⏱ 等待同步...")
        self.status_bar.setFixedHeight(30)
        self.status_bar.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 0 16px; border-top: 1px solid #F0F2F5;")
        layout.addWidget(self.status_bar)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0)
        outer.addWidget(self.bg)

    def _do_refresh(self):
        self.status_bar.setText("⏱ 同步中...")
        QTimer.singleShot(0, self.sync_worker.refresh)

    def _on_tasks_ready(self, tasks):
        self._render_tasks(tasks)
        from datetime import datetime
        self.status_bar.setText(f"⏱ {datetime.now().strftime('%H:%M')} 已同步 · {len(tasks)} 条待办")

    def _on_sync_error(self, msg):
        self.status_bar.setText(f"❌ {msg}")

    def _on_logic_state_changed(self, state_text, state_id):
        """核心逻辑层状态变化后的反馈"""
        is_paused = self.logic.is_paused
        # 更新所有 Widget 按钮态
        for tid, w in self.task_widgets.items():
            is_active = (tid == self.current_focus_task_id)
            w.set_sync_state(is_active, is_paused)
        
        # 状态栏同步
        if state_id == "stopped":
             self.status_bar.setText("⏱ 处理闲置状态")
        else:
             self.status_bar.setText(f"🎯 {state_text.splitlines()[0]}")

    def _render_tasks(self, tasks):
        for w in self.task_widgets.values(): w.deleteLater()
        self.task_widgets.clear()
        while self.task_layout.count() > 1:
            item = self.task_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        sorted_tasks = sorted(tasks, key=lambda t: (-t.get("priority", 0), t.get("due_date", "") or "zzz"))
        for task in sorted_tasks:
            w = TaskItemWidget(task)
            w.focus_clicked.connect(self._on_focus_clicked)
            w.complete_clicked.connect(self._on_complete_clicked)
            
            # 初始化状态
            is_active = (self.current_focus_task_id == task['id'])
            w.set_sync_state(is_active, self.logic.is_paused if self.logic else False)
            
            self.task_widgets[task['id']] = w
            self.task_layout.insertWidget(self.task_layout.count()-1, w)

    def _on_focus_clicked(self, task_data):
        task_id = task_data["id"]
        task_name = task_data["title"]
        group_tag = task_data.get("group_name") 

        # 如果点击的是当前正在专注的任务，则执行 播放/暂停 切换
        if self.current_focus_task_id == task_id and self.logic and self.logic.current_state != "stopped":
            self.logic.toggle_pause()
            return

        if self.logic and self.parent() and hasattr(self.parent(), "category_manager"):
            from category_dialog import CategorySelectDialog
            from PyQt6.QtWidgets import QDialog
            dialog = CategorySelectDialog(self.parent().category_manager, task_name, self)
            if group_tag:
                if hasattr(dialog, "set_initial_group"): dialog.set_initial_group(group_tag)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                cat_id = dialog.selected_category_id
                cat_group = dialog.selected_group_name
                self.current_focus_task_id = task_id
                # 显式重置 logic 状态确保启动
                self.logic.start_with_context(task_name, cat_id, cat_group)
            else:
                return

    def _on_complete_clicked(self, task_data):
        tid = task_data["id"]
        self.sync_worker.remove_from_cache(tid)
        if tid in self.task_widgets: self.task_widgets.pop(tid).deleteLater()
        if self.current_focus_task_id == tid:
            self.current_focus_task_id = None
            QTimer.singleShot(300, self._prompt_switch)
        self.sync_worker.complete_task(tid, task_data["project_id"])

    def _on_task_completed_ok(self, task_id): logger.info(f"任务 {task_id} 已同步到 TickTick")
    def _on_task_complete_failed(self, task_id, error): self.status_bar.setText(f"❌ 同步失败: {error}")

    def _prompt_switch(self):
        tasks = self.sync_worker.get_cached_tasks()
        if not tasks: return
        diag = FocusSwitchDialog(tasks, self)
        if diag.exec() == QDialog.DialogCode.Accepted:
            selected = diag.get_selected()
            if selected: self._on_focus_clicked(selected)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton: self.dragPos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and self.dragPos: self.move(e.globalPosition().toPoint() - self.dragPos)
    def mouseReleaseEvent(self, e): self.dragPos = None
    def show(self):
        super().show()
        self._do_refresh()
        self._on_logic_state_changed("", self.logic.current_state if self.logic else "stopped")
    def hide(self):
        self.settings.setValue("pos", self.pos())
        super().hide()
    def _load_position(self):
        p = self.settings.value("pos")
        if p: self.move(p)
    def cleanup(self):
        self.auto_refresh_timer.stop()
        self.sync_thread.quit()
        self.sync_thread.wait()
