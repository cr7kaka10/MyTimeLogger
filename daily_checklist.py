# -*- coding: utf-8 -*-
"""
日清单模块 (daily_checklist.py)
================================
独立浮动窗口，从 TickTick 拉取今日任务并显示。
支持勾选完成/取消、发起专注、完成后切换专注提示。
"""

import logging
from datetime import date

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QCheckBox, QPushButton, QFrame, QMessageBox, QDialog,
    QDialogButtonBox, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QIcon

from ticktick_sync import TickTickSyncWorker, HAS_TICKTICK_SDK

logger = logging.getLogger(__name__)

# ==================== 优先级配色 ====================

PRIORITY_MAP = {
    5: ("⏫ 高", "#BF616A", "rgba(191,97,106,0.2)"),
    3: ("🔶 中", "#D08770", "rgba(208,135,112,0.2)"),
    1: ("🔽 低", "#5E81AC", "rgba(94,129,172,0.2)"),
    0: ("── 无", "#4C566A", "rgba(76,86,106,0.3)"),
}

# 专注态颜色（蓝色风格）
FOCUS_COLOR = "#81A1C1"
FOCUS_BG = "rgba(129,161,193,0.15)"
FOCUS_BORDER = "rgba(129,161,193,0.5)"


class TaskItemWidget(QFrame):
    """单个任务项 Widget"""

    focus_clicked = pyqtSignal(dict)      # 点击专注按钮
    check_toggled = pyqtSignal(dict, bool)  # 勾选/取消

    def __init__(self, task_data: dict, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.is_focusing = False
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("taskItem")
        self.setStyleSheet(self._base_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # === 第一行：checkbox + 标题 + 专注按钮 ===
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(self.task_data["is_completed"])
        self.checkbox.setFixedSize(18, 18)
        self.checkbox.setStyleSheet(self._checkbox_style())
        self.checkbox.stateChanged.connect(self._on_check_changed)

        self.title_label = QLabel(self.task_data["title"])
        self.title_label.setWordWrap(True)
        self._update_title_style()

        self.focus_btn = QPushButton("▶ 专注")
        self.focus_btn.setFixedHeight(24)
        self.focus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.focus_btn.clicked.connect(lambda: self.focus_clicked.emit(self.task_data))
        self._update_focus_btn()

        row1.addWidget(self.checkbox)
        row1.addWidget(self.title_label, 1)
        row1.addWidget(self.focus_btn)

        layout.addLayout(row1)

        # === 第二行：优先级 + 项目 + 标签 + 截止时间 ===
        row2 = QHBoxLayout()
        row2.setContentsMargins(28, 0, 0, 0)
        row2.setSpacing(6)

        priority = self.task_data.get("priority", 0)
        p_text, p_color, p_bg = PRIORITY_MAP.get(priority, PRIORITY_MAP[0])
        priority_label = QLabel(p_text)
        priority_label.setStyleSheet(f"""
            QLabel {{ font-size: 11px; padding: 2px 8px; border-radius: 10px;
                     background: {p_bg}; color: {p_color}; font-weight: 600; }}
        """)
        row2.addWidget(priority_label)

        project_name = self.task_data.get("project_name", "")
        if project_name:
            proj_label = QLabel(f"📁 {project_name}")
            proj_label.setStyleSheet("""
                QLabel { font-size: 11px; padding: 2px 8px; border-radius: 10px;
                         background: rgba(136,192,208,0.15); color: #88C0D0; }
            """)
            row2.addWidget(proj_label)

        for tag in self.task_data.get("tags", []):
            tag_label = QLabel(f"🏷 {tag}")
            tag_label.setStyleSheet(f"""
                QLabel {{ font-size: 10px; padding: 1px 6px; border-radius: 8px;
                         background: {FOCUS_BG}; color: {FOCUS_COLOR}; }}
            """)
            row2.addWidget(tag_label)

        due = self.task_data.get("due_date", "")
        if due and due != "全天":
            due_label = QLabel(f"⏰ {due}")
            due_color = "#BF616A" if due else "#4C566A"
            due_label.setStyleSheet(f"QLabel {{ font-size: 11px; color: {due_color}; }}")
            row2.addWidget(due_label)

        row2.addStretch()
        layout.addLayout(row2)

    def _base_style(self):
        return """
            #taskItem {
                background: rgba(59, 66, 82, 0.6);
                border-radius: 8px;
                border: 1px solid transparent;
            }
            #taskItem:hover {
                border-color: rgba(136, 192, 208, 0.3);
                background: rgba(59, 66, 82, 0.9);
            }
        """

    def _checkbox_style(self):
        return f"""
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border-radius: 4px;
                border: 2px solid #88C0D0;
                background: transparent;
            }}
            QCheckBox::indicator:checked {{
                background: #88C0D0;
                border-color: #88C0D0;
                image: none;
            }}
        """

    def _update_title_style(self):
        if self.task_data["is_completed"]:
            self.title_label.setStyleSheet(
                "QLabel { color: #4C566A; font-size: 14px; text-decoration: line-through; }"
            )
        else:
            self.title_label.setStyleSheet(
                "QLabel { color: #ECEFF4; font-size: 14px; }"
            )

    def _update_focus_btn(self):
        if self.task_data["is_completed"]:
            self.focus_btn.setEnabled(False)
            self.focus_btn.setText("▶ 专注")
            self.focus_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 3px 10px; border-radius: 6px;
                    border: 1px solid #4C566A;
                    background: transparent; color: #4C566A;
                    font-size: 11px;
                }}
            """)
        elif self.is_focusing:
            self.focus_btn.setEnabled(False)
            self.focus_btn.setText("🎯 专注中")
            self.focus_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 3px 10px; border-radius: 6px;
                    border: 1px solid {FOCUS_COLOR};
                    background: {FOCUS_COLOR}; color: #2E3440;
                    font-size: 11px; font-weight: bold;
                }}
            """)
        else:
            self.focus_btn.setEnabled(True)
            self.focus_btn.setText("▶ 专注")
            self.focus_btn.setStyleSheet(f"""
                QPushButton {{
                    padding: 3px 10px; border-radius: 6px;
                    border: 1px solid {FOCUS_COLOR};
                    background: {FOCUS_BG}; color: {FOCUS_COLOR};
                    font-size: 11px;
                }}
                QPushButton:hover {{
                    background: rgba(129,161,193,0.35);
                }}
            """)

    def set_focusing(self, focusing: bool):
        self.is_focusing = focusing
        if focusing:
            self.setStyleSheet(f"""
                #taskItem {{
                    background: rgba(59, 66, 82, 0.8);
                    border-radius: 8px;
                    border: 1px solid {FOCUS_BORDER};
                }}
            """)
        else:
            self.setStyleSheet(self._base_style())
        self._update_focus_btn()

    def set_completed(self, completed: bool):
        self.task_data["is_completed"] = completed
        self.checkbox.blockSignals(True)
        self.checkbox.setChecked(completed)
        self.checkbox.blockSignals(False)
        self._update_title_style()
        self._update_focus_btn()
        if completed:
            self.setStyleSheet(self._base_style().replace("0.6", "0.3"))
        else:
            self.setStyleSheet(self._base_style())

    def _on_check_changed(self, state):
        is_checked = state == Qt.CheckState.Checked.value
        self.check_toggled.emit(self.task_data, is_checked)


class FocusSwitchDialog(QDialog):
    """完成专注任务后的切换对话框"""

    def __init__(self, remaining_tasks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("切换专注目标")
        self.setMinimumSize(350, 250)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.selected_task = None

        self.setStyleSheet("""
            QDialog { background: #2E3440; }
            QLabel { color: #ECEFF4; font-size: 13px; }
            QListWidget {
                background: #3B4252; color: #ECEFF4; border: 1px solid #4C566A;
                border-radius: 6px; font-size: 13px; padding: 4px;
            }
            QListWidget::item { padding: 8px; border-radius: 4px; }
            QListWidget::item:selected { background: #5E81AC; }
            QListWidget::item:hover { background: #434C5E; }
            QPushButton {
                background: #5E81AC; color: #ECEFF4; border: none;
                border-radius: 6px; padding: 8px 16px; font-size: 13px;
            }
            QPushButton:hover { background: #81A1C1; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("✅ 当前专注任务已完成！\n选择下一个专注目标："))

        self.task_list = QListWidget()
        for task in remaining_tasks:
            p = task.get("priority", 0)
            p_text = PRIORITY_MAP.get(p, PRIORITY_MAP[0])[0]
            item = QListWidgetItem(f"{p_text}  {task['title']}")
            item.setData(Qt.ItemDataRole.UserRole, task)
            self.task_list.addItem(item)
        self.task_list.itemDoubleClicked.connect(self._on_double_click)

        layout.addWidget(self.task_list)

        btn_layout = QHBoxLayout()
        skip_btn = QPushButton("跳过")
        skip_btn.setStyleSheet("QPushButton { background: #4C566A; } QPushButton:hover { background: #5E81AC; }")
        skip_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("开始专注")
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(skip_btn)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)

    def _on_ok(self):
        item = self.task_list.currentItem()
        if item:
            self.selected_task = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _on_double_click(self, item):
        self.selected_task = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


class DailyChecklistWindow(QWidget):
    """日清单独立浮动窗口"""

    def __init__(self, config, logic=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.logic = logic
        self.settings = QSettings("MyTimeLogger", "DailyChecklist")
        self.task_widgets = []
        self.current_focus_task_id = None
        self.tasks_data = []

        self.setWindowTitle("今日清单")
        self.setFixedSize(400, 520)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dragPos = None

        self._init_worker()
        self._build_ui()
        self._load_position()

        # 自动刷新定时器
        interval = self.config.get("ticktick_config", {}).get("sync_interval", 300)
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(interval * 1000)
        self.auto_refresh_timer.timeout.connect(self._do_refresh)

    def _init_worker(self):
        """初始化同步工作者和线程"""
        self.sync_thread = QThread()
        self.sync_worker = TickTickSyncWorker(self.config)
        self.sync_worker.moveToThread(self.sync_thread)

        self.sync_worker.tasks_ready.connect(self._on_tasks_ready)
        self.sync_worker.sync_error.connect(self._on_sync_error)
        self.sync_worker.task_updated.connect(self._on_task_updated)
        self.sync_worker.task_update_failed.connect(self._on_task_update_failed)

        self.sync_thread.start()

    def _build_ui(self):
        """构建 UI"""
        self.bg = QWidget(self)
        self.bg.setObjectName("checklistBg")
        self.bg.setGeometry(0, 0, 400, 520)
        self.bg.setStyleSheet("""
            #checklistBg {
                background-color: rgba(46, 52, 64, 0.95);
                border: 1px solid #88C0D0;
                border-radius: 12px;
            }
        """)

        main_layout = QVBoxLayout(self.bg)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === 标题栏 ===
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 10, 12, 6)

        title = QLabel("📋 <b>今日清单</b> <span style='color:#4C566A;font-size:11px;'>(Ctrl+X)</span>")
        title.setStyleSheet("QLabel { color: #ECEFF4; font-size: 16px; }")

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(24, 24)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(self._header_btn_style())
        self.refresh_btn.clicked.connect(self._do_refresh)

        min_btn = QPushButton("─")
        min_btn.setFixedSize(24, 24)
        min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        min_btn.setStyleSheet(self._header_btn_style())
        min_btn.clicked.connect(self.hide)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(self._header_btn_style())
        close_btn.clicked.connect(self.hide)

        header_layout.addWidget(title, 1)
        header_layout.addWidget(self.refresh_btn)
        header_layout.addWidget(min_btn)
        header_layout.addWidget(close_btn)
        main_layout.addWidget(header)

        # === 日期 ===
        today = date.today()
        week_map = {0: '一', 1: '二', 2: '三', 3: '四', 4: '五', 5: '六', 6: '日'}
        date_label = QLabel(f"  {today.isoformat()} 星期{week_map[today.weekday()]}")
        date_label.setStyleSheet("QLabel { color: #81A1C1; font-size: 12px; padding-left: 16px; }")
        date_label.setFixedHeight(22)
        main_layout.addWidget(date_label)

        # === 分隔线 ===
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: rgba(76, 86, 106, 0.5); max-height: 1px;")
        main_layout.addWidget(sep)

        # === 任务列表（可滚动） ===
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: #4C566A; border-radius: 2px; min-height: 20px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self.task_container = QWidget()
        self.task_container.setStyleSheet("background: transparent;")
        self.task_layout = QVBoxLayout(self.task_container)
        self.task_layout.setContentsMargins(12, 8, 12, 8)
        self.task_layout.setSpacing(8)
        self.task_layout.addStretch()

        self.scroll_area.setWidget(self.task_container)
        main_layout.addWidget(self.scroll_area, 1)

        # === 状态栏 ===
        self.status_bar = QLabel("⏱ 等待同步...")
        self.status_bar.setFixedHeight(32)
        self.status_bar.setStyleSheet("""
            QLabel {
                color: #4C566A; font-size: 11px;
                padding: 0 16px;
                border-top: 1px solid rgba(76, 86, 106, 0.5);
            }
        """)
        main_layout.addWidget(self.status_bar)

        # 外层布局
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.bg)

    def _header_btn_style(self):
        return """
            QPushButton {
                background: rgba(76, 86, 106, 0.4);
                color: #D8DEE9; font-size: 13px;
                border: none; border-radius: 6px;
            }
            QPushButton:hover { background: #5E81AC; }
        """

    # ==================== 数据刷新 ====================

    def show(self):
        """显示窗口并触发刷新"""
        super().show()
        self.activateWindow()
        self.raise_()
        self._do_refresh()
        self.auto_refresh_timer.start()

    def hide(self):
        """隐藏窗口，停止自动刷新"""
        self.auto_refresh_timer.stop()
        self._save_position()
        super().hide()

    def _do_refresh(self):
        """触发后台同步"""
        self.status_bar.setText("⏱ 同步中...")
        QTimer.singleShot(0, self.sync_worker.refresh)

    def _on_tasks_ready(self, tasks):
        """任务列表就绪回调"""
        self.tasks_data = tasks
        self._render_tasks(tasks)
        from datetime import datetime
        now = datetime.now().strftime("%H:%M:%S")
        total = len(tasks)
        done = sum(1 for t in tasks if t["is_completed"])
        self.status_bar.setText(f"⏱ {now} 同步  ·  {total} 项任务 · {done} 已完成")

    def _on_sync_error(self, msg):
        """同步错误回调"""
        self.status_bar.setText(f"❌ {msg}")
        logger.error(f"同步错误: {msg}")

    def _render_tasks(self, tasks):
        """渲染任务列表"""
        # 清空现有
        for w in self.task_widgets:
            w.setParent(None)
            w.deleteLater()
        self.task_widgets.clear()

        # 排除 stretch
        while self.task_layout.count():
            item = self.task_layout.takeAt(0)

        # 排序: 未完成在前 → 优先级降序 → 有截止时间优先
        sorted_tasks = sorted(tasks, key=lambda t: (
            t["is_completed"],
            -t.get("priority", 0),
            t.get("due_date", "") or "zzz",
        ))

        for task in sorted_tasks:
            widget = TaskItemWidget(task)
            widget.focus_clicked.connect(self._on_focus_clicked)
            widget.check_toggled.connect(self._on_check_toggled)

            if self.current_focus_task_id and task["id"] == self.current_focus_task_id:
                widget.set_focusing(True)

            self.task_widgets.append(widget)
            self.task_layout.addWidget(widget)

        self.task_layout.addStretch()

    # ==================== 勾选处理 ====================

    def _on_check_toggled(self, task_data, is_checked):
        """勾选/取消勾选任务"""
        task_id = task_data["id"]
        project_id = task_data["project_id"]

        # 乐观更新 UI
        for w in self.task_widgets:
            if w.task_data["id"] == task_id:
                w.set_completed(is_checked)
                break

        # 异步推送
        if is_checked:
            QTimer.singleShot(0, lambda: self.sync_worker.complete_task(task_id, project_id))
            # 如果勾选的是当前专注任务，弹出切换对话框
            if self.current_focus_task_id == task_id:
                QTimer.singleShot(300, self._prompt_switch_focus)
        else:
            QTimer.singleShot(0, lambda: self.sync_worker.uncomplete_task(task_id, project_id))

    def _on_task_updated(self, task_id, is_completed):
        """后台同步成功"""
        logger.info(f"任务 {task_id} 状态更新成功: completed={is_completed}")

    def _on_task_update_failed(self, task_id, original_state, error):
        """后台同步失败，回滚"""
        logger.error(f"任务 {task_id} 更新失败: {error}")
        for w in self.task_widgets:
            if w.task_data["id"] == task_id:
                w.set_completed(original_state)
                break
        self.status_bar.setText(f"❌ 操作失败: {error}")

    # ==================== 专注联动 ====================

    def _on_focus_clicked(self, task_data):
        """点击专注按钮"""
        task_id = task_data["id"]
        task_name = task_data["title"]

        # 更新高亮状态
        self.current_focus_task_id = task_id
        for w in self.task_widgets:
            w.set_focusing(w.task_data["id"] == task_id)

        # 联动 Logic 层
        if self.logic:
            self.logic.start_with_context(task_name)

        # 更新状态栏
        short_name = task_name[:15] + "..." if len(task_name) > 15 else task_name
        self.status_bar.setText(f"🎯 专注: {short_name}")
        self.status_bar.setStyleSheet(f"""
            QLabel {{
                color: {FOCUS_COLOR}; font-size: 11px;
                padding: 0 16px;
                border-top: 1px solid rgba(76, 86, 106, 0.5);
            }}
        """)

    def _prompt_switch_focus(self):
        """完成当前专注任务后，提示切换"""
        remaining = [t for t in self.tasks_data
                     if not t["is_completed"] and t["id"] != self.current_focus_task_id]

        if not remaining:
            self.current_focus_task_id = None
            for w in self.task_widgets:
                w.set_focusing(False)
            self.status_bar.setText("🎉 所有任务已完成！")
            self.status_bar.setStyleSheet("""
                QLabel { color: #A3BE8C; font-size: 11px; padding: 0 16px;
                         border-top: 1px solid rgba(76, 86, 106, 0.5); }
            """)
            return

        dialog = FocusSwitchDialog(remaining, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_task:
            self._on_focus_clicked(dialog.selected_task)
        else:
            # 用户跳过，清除专注状态
            self.current_focus_task_id = None
            for w in self.task_widgets:
                w.set_focusing(False)
            self.status_bar.setText(f"⏱ 专注已结束")
            self.status_bar.setStyleSheet("""
                QLabel { color: #4C566A; font-size: 11px; padding: 0 16px;
                         border-top: 1px solid rgba(76, 86, 106, 0.5); }
            """)

    # ==================== 窗口拖拽 ====================

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)

    def mouseReleaseEvent(self, event):
        self.dragPos = None

    # ==================== 位置持久化 ====================

    def _save_position(self):
        self.settings.setValue("checklist/pos", self.pos())

    def _load_position(self):
        pos = self.settings.value("checklist/pos")
        if pos:
            self.move(pos)

    # ==================== 关闭 ====================

    def closeEvent(self, event):
        self._save_position()
        self.auto_refresh_timer.stop()
        event.accept()

    def cleanup(self):
        """程序退出时清理"""
        self.auto_refresh_timer.stop()
        self.sync_thread.quit()
        self.sync_thread.wait(3000)
