# -*- coding: utf-8 -*-
"""
日清单模块 (daily_checklist.py) - 视觉对齐与逻辑修复版
===================================================
独立浮动窗口，支持与主面板实时的播放状态联动。
"""

import logging
from datetime import date

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QCheckBox, QPushButton, QFrame, QDialog, QListWidget, QListWidgetItem, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QPoint
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
    5: ("\uf024", "#FF5252", "rgba(255,82,82,0.1)"),   # 高 (红旗)
    3: ("\uf024", "#FF9800", "rgba(255,152,0,0.1)"),  # 中 (橙旗)
    1: ("\uf024", "#2196F3", "rgba(33,150,243,0.1)"), # 低 (蓝旗)
    0: ("\uf024", "#CBD2D9", "rgba(76,86,106,0.05)"), # 无 (灰旗 - 无色)
}

class TaskItemWidget(QFrame):
    """单个任务项 Widget（增强版：带状态联动的播放按钮）"""

    focus_clicked = pyqtSignal(dict)
    complete_clicked = pyqtSignal(dict)
    priority_changed = pyqtSignal(dict, int)

    def __init__(self, task_data: dict, parent=None):
        super().__init__(parent)
        self.task_data = task_data
        self.is_active = False   
        self.is_paused = False   
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

        # 播放/暂停按钮（1:1 复刻主面板 start_btn）
        self.play_btn = QPushButton("\uf04b") 
        self.play_btn.setFixedSize(24, 24) # 完美对齐 24x24
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
        p_icon, p_color, p_bg = PRIORITY_MAP.get(priority, PRIORITY_MAP[0])
        priority_label = QLabel(p_icon)
        priority_label.setStyleSheet(
            f"QLabel {{ font-family: 'Font Awesome 6 Free'; font-size: 14px; padding: 2px 4px; "
            f"color: {p_color}; background: transparent; border: none; }}"
        )
        row2.addWidget(priority_label)

        # 移除项目组信息（如收件箱），保持界面简洁

        # 奖励金币显示
        coins = self.task_data.get('reward_coins', 1.0)
        self.coin_label = QLabel(f"🪙{coins:g}")
        self.coin_label.setStyleSheet(f"QLabel {{ font-size: 10px; padding: 1px 4px; border-radius: 4px; background: rgba(235,203,139,0.15); color: #D08770; }}")
        row2.addWidget(self.coin_label)

        for tag in self.task_data.get("tags", []):
            tag_label = QLabel(f"🏷 {tag}")
            tag_label.setStyleSheet(f"QLabel {{ font-size: 10px; padding: 1px 6px; border-radius: 4px; background: #E5E9F0; color: {TEXT_SECONDARY}; }}")
            row2.addWidget(tag_label)

        due_full = self.task_data.get("due_date_full", "")
        is_overdue = self.task_data.get("is_overdue", False)
        if due_full:
            if is_overdue:
                due_label = QLabel(f"🔴 {due_full}")
                due_label.setStyleSheet("QLabel { font-size: 11px; color: #BF616A; font-weight: bold; }")
            else:
                due_label = QLabel(f"⏰ {due_full}")
                due_label.setStyleSheet(f"QLabel {{ font-size: 11px; color: {TEXT_SECONDARY}; }}")
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
        # 视觉 1:1 对齐 ActivityPanel 的样式
        if self.is_active and not self.is_paused:
            self.play_btn.setText("\uf04c") # Pause
            color = "#D08770" 
            padding = "0px"
        else:
            self.play_btn.setText("\uf04b") # Play
            color = "#5E81AC"
            padding = "2px" # 为播放图标加一点左偏置，使其感官居中
        
        self.play_btn.setStyleSheet(f"""
            QPushButton {{
                font-family: 'Font Awesome 6 Free'; font-weight: 900; font-size: 10px;
                background-color: {color}; color: white; border: none; border-radius: 4px; padding-left: {padding};
            }}
            QPushButton:hover {{ background-color: {SAPPHIRE_HOVER}; }}
        """)

    def set_sync_state(self, is_active: bool, is_paused: bool):
        self.is_active = is_active
        self.is_paused = is_paused
        self._update_style()
        self._update_play_btn_style()

    def _on_check_changed(self, state):
        if state == Qt.CheckState.Checked.value:
            self.complete_clicked.emit(self.task_data)

    def contextMenuEvent(self, event):
        """右键菜单切换优先级"""
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction
        
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 1px solid #D8DEE9; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 24px; color: #2E3440; font-size: 13px; }
            QMenu::item:selected { background-color: rgba(94, 129, 172, 0.1); color: #5E81AC; border-radius: 4px; }
        """)
        
        # 优先级映射：5-高, 3-中, 1-低, 0-无
        priorities = [
            (5, "高 (红色)", "#FF5252"),
            (3, "中 (橙色)", "#FF9800"),
            (1, "低 (蓝色)", "#2196F3"),
            (0, "无 (灰色)", "#CBD2D9"),
        ]
        
        current_p = self.task_data.get("priority", 0)
        
        for val, label, color in priorities:
            icon_txt = "\uf024"
            # 创建带彩色旗帜的 Action
            action = QAction(f"{label}", self)
            if val == current_p:
                action.setCheckable(True)
                action.setChecked(True)
                
            # 利用 lambda 捕获 val
            action.triggered.connect(lambda _, v=val: self.priority_changed.emit(self.task_data, v))
            menu.addAction(action)

        menu.addSeparator()
        # 设置奖励
        reward_action = QAction(f"🪙 设置奖励 (当前: {self.task_data.get('reward_coins', 1.0):g})", self)
        reward_action.triggered.connect(self._set_reward)
        menu.addAction(reward_action)
            
        menu.exec(event.globalPos())

    def _set_reward(self):
        from PyQt6.QtWidgets import QInputDialog
        from database import StudyLogger
        current = self.task_data.get('reward_coins', 1.0)
        val, ok = QInputDialog.getDouble(self, "设置奖励", f"完成此任务奖励金币数:", current, 0, 100, 1)
        if ok:
            db = StudyLogger({})
            db.set_item_reward('task', self.task_data['id'], val)
            self.task_data['reward_coins'] = val
            self.coin_label.setText(f"🪙{val:g}")

class FocusSwitchDialog(QDialog):
    """切换专注对话框（亮色版）"""
    def __init__(self, remaining_tasks, parent=None):
        super().__init__(parent)
        self.setWindowTitle("切换专注目标")
        self.setMinimumSize(350, 250)
        self.setStyleSheet(f"""
            QDialog {{ background: #FFFFFF; }}
            QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; font-family: 'Microsoft YaHei'; }}
            QListWidget {{ background: #F8F9FB; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_COLOR}; border-radius: 6px; padding: 4px; }}
            QListWidget::item {{ padding: 8px; border-bottom: 1px solid #F0F2F5; }}
            QListWidget::item:selected {{ background: {ITEM_HOVER_BG}; color: {SAPPHIRE_BLUE}; font-weight: bold; border-radius: 4px; }}
            QPushButton {{ background: {SAPPHIRE_BLUE}; color: white; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }}
            QPushButton:hover {{ background: {SAPPHIRE_HOVER}; }}
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(QLabel("<b>✅ 当前任务已完成！</b>\n接下来的任务是："))
        self.list = QListWidget()
        for t in remaining_tasks:
            p_text = PRIORITY_MAP.get(t.get('priority', 0), PRIORITY_MAP[0])[0]
            item = QListWidgetItem(f"{p_text} {t['title']}")
            item.setData(Qt.ItemDataRole.UserRole, t), self.list.addItem(item)
        layout.addWidget(self.list)
        btns = QHBoxLayout()
        skip = QPushButton("跳过")
        skip.setStyleSheet("QPushButton { background: #E5E9F0; color: #4C566A; }"), skip.clicked.connect(self.reject)
        ok = QPushButton("开始新专注"), ok.clicked.connect(self.accept)
        btns.addWidget(skip), btns.addWidget(ok), layout.addLayout(btns)
    def get_selected(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

class DailyChecklistWindow(QWidget):
    """日清单窗口（修复按钮激活逻辑）"""
    request_priority_update = pyqtSignal(str, str, int)

    def __init__(self, config, logic=None, category_manager=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.logic = logic
        self.category_manager = category_manager # 显式引用，不依赖 parent()
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

        if self.logic:
            self.logic.state_changed.connect(self._on_logic_state_changed)

        # 按用户要求：下线定时同步逻辑，改为按需同步（启动、操作、刷新时触发）
        # interval = self.config.get("ticktick_config", {}).get("sync_interval", 300)
        # self.auto_refresh_timer = QTimer(self)
        # self.auto_refresh_timer.setInterval(interval * 1000)
        # self.auto_refresh_timer.timeout.connect(self._do_refresh)
        # self.auto_refresh_timer.start()

        # 启动时确保同步一次（异步静默触发）
        QTimer.singleShot(500, self._do_refresh)

    def _init_worker(self):
        self.sync_thread = QThread()
        self.sync_worker = TickTickSyncWorker(self.config, self.category_manager)
        self.sync_worker.moveToThread(self.sync_thread)
        self.sync_worker.tasks_ready.connect(self._on_tasks_ready)
        self.sync_worker.sync_error.connect(self._on_sync_error)
        self.sync_worker.task_completed_ok.connect(self._on_task_completed_ok)
        self.sync_worker.task_complete_failed.connect(self._on_task_complete_failed)
        
        # 连接优先级更新信号 (UI Thread -> Sync Thread)
        self.request_priority_update.connect(self.sync_worker.update_priority)
        
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
        header_layout.addWidget(title_label), header_layout.addStretch()

        btn_style = f"QPushButton {{ color: {TEXT_SECONDARY}; background: transparent; font-size: 16px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {SAPPHIRE_BLUE}; }}"
        

        
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(30,30), self.refresh_btn.clicked.connect(self._do_refresh), self.refresh_btn.setStyleSheet(btn_style)
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30,30), close_btn.clicked.connect(self.hide), close_btn.setStyleSheet(btn_style)
        header_layout.addWidget(self.refresh_btn), header_layout.addWidget(close_btn), layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True), self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.task_layout = QVBoxLayout(self.container)
        self.task_layout.setContentsMargins(15, 10, 15, 10)
        self.task_layout.setSpacing(10), self.task_layout.addStretch()
        self.scroll.setWidget(self.container), layout.addWidget(self.scroll)

        # 底部状态栏（container 布局，确保 claim_btn 有父控件）
        status_container = QWidget()
        status_container.setFixedHeight(30)
        status_container.setStyleSheet("border-top: 1px solid #F0F2F5;")
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(16, 0, 16, 0)
        status_layout.setSpacing(8)

        self.status_bar = QLabel("⏱ 等待同步...")
        self.status_bar.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; border: none;")
        status_layout.addWidget(self.status_bar)

        status_layout.addStretch()

        self.claim_btn = QPushButton("🎁 待领取")
        self.claim_btn.setStyleSheet(f"QPushButton {{ color: #D08770; background: transparent; font-size: 11px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {SAPPHIRE_BLUE}; }}")
        self.claim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.claim_btn.clicked.connect(self._on_claim_clicked)
        self.claim_btn.hide()
        status_layout.addWidget(self.claim_btn)

        layout.addWidget(status_container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0,0,0,0), outer.addWidget(self.bg)

    def _do_refresh(self):
        self.status_bar.setText("⏱ 同步中...")
        QTimer.singleShot(0, self.sync_worker.refresh)

    def _on_tasks_ready(self, tasks):
        # 注入每个任务的自定义奖励值
        from database import StudyLogger
        db = StudyLogger(self.config)
        for t in tasks:
            t['reward_coins'] = db.get_item_reward('task', t['id'], 0.1)
        self._render_tasks(tasks)
        from datetime import datetime
        balance = db.get_balance()
        self.status_bar.setText(f"⏱ {datetime.now().strftime('%H:%M')} 已同步 · {len(tasks)} 条待办  |  💰 {balance}🪙")
        self._refresh_claim_button(db)

    def _refresh_claim_button(self, db=None):
        if db is None:
            from database import StudyLogger
            db = StudyLogger(self.config)
        unclaimed = db.get_unclaimed_rewards()
        if unclaimed:
            total_coins = sum(r.get('coins', 0) for r in unclaimed)
            self.claim_btn.setText(f"🎁 待领取({total_coins:g}🪙)")
            self.claim_btn.show()
        else:
            self.claim_btn.hide()

    def _on_claim_clicked(self):
        from database import StudyLogger
        db = StudyLogger(self.config)
        unclaimed = db.get_unclaimed_rewards()
        if not unclaimed:
            return
        ids = [i['id'] for i in unclaimed]
        claimed_coins = db.claim_rewards(ids)
        if claimed_coins > 0:
            db.add_ledger_entry(claimed_coins, 'external_claim', None, f"领取外部奖励: 共{len(ids)}项")
            self._do_refresh()
            from particle_effect import start_coin_explosion
            start_coin_explosion(self, self.claim_btn, len(ids))




    def _on_sync_error(self, msg): self.status_bar.setText(f"❌ {msg}")

    def _on_logic_state_changed(self, state_text, state_id):
        is_paused = self.logic.is_paused
        for tid, w in self.task_widgets.items():
            is_active = (tid == self.current_focus_task_id)
            w.set_sync_state(is_active, is_paused)
        if state_id == "stopped": self.status_bar.setText("⏱ 闲置中")
        else: self.status_bar.setText(f"🎯 {state_text.splitlines()[0]}")

    def _render_tasks(self, tasks):
        for w in self.task_widgets.values(): w.deleteLater()
        self.task_widgets.clear()
        
        # 清理布局项目
        while self.task_layout.count() > 1:
            item = self.task_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        # 显示所有任务（包括无优化的）
        sorted_tasks = sorted(tasks, key=lambda t: (-t.get("priority", 0), t.get("due_date", "") or "zzz"))
        for task in sorted_tasks:
            w = TaskItemWidget(task)
            w.focus_clicked.connect(self._on_focus_clicked)
            w.complete_clicked.connect(self._on_complete_clicked)
            w.priority_changed.connect(self._on_priority_changed)
            is_active = (self.current_focus_task_id == task['id'])
            w.set_sync_state(is_active, self.logic.is_paused if self.logic else False)
            self.task_widgets[task['id']] = w
            self.task_layout.insertWidget(self.task_layout.count()-1, w)

    def _on_priority_changed(self, task_data, new_priority):
        """处理优先级变更：立即更新本地并后台同步"""
        task_id = task_data["id"]
        project_id = task_data["project_id"]
        
        logger.info(f"修改任务 {task_id} 优先级为 {new_priority}")
        
        # 1. 立即更新当前的缓存数据（为了重新渲染）
        cached_tasks = self.sync_worker.get_cached_tasks()
        for t in cached_tasks:
            if t["id"] == task_id:
                t["priority"] = new_priority
                break
        
        # 2. 重新渲染列表（会自动触发重排）
        self._render_tasks(cached_tasks)
        
        # 3. 通过信号请求后台同步（确保在 SyncWorker 所在的线程中执行）
        self.request_priority_update.emit(task_id, project_id, new_priority)

    def _on_focus_clicked(self, task_data):
        task_id = task_data["id"]
        task_name = task_data["title"]
        group_tag = task_data.get("group_name") 
        logger.info(f"[DEBUG] 日清单按钮点击: {task_name} (ID: {task_id})")

        if self.current_focus_task_id == task_id and self.logic and self.logic.current_state != "stopped":
            logger.info("[DEBUG] 切换当前任务播放/暂停")
            self.logic.toggle_pause()
            return

        # 自动化匹配逻辑：标签即分类名 (直接秒开，跳过弹窗)
        tags = task_data.get("tags", [])
        if tags:
            all_cats = self.category_manager.get_all_active()
            # 查找名称与标签一致的分类
            matched_cat = next((c for c in all_cats if c['name'] in tags), None)
            if matched_cat:
                logger.info(f"[AUTO] 自动匹配分类名: {matched_cat['name']}，跳过弹窗")
                self.current_focus_task_id = task_id
                self.logic.start_with_context(task_name, matched_cat['id'], matched_cat['group_name'], category_name=matched_cat['name'])
                return

        # 降级处理：仅在没有匹配到任何标签时才弹框
        if self.logic and self.category_manager:
            from category_dialog import CategorySelectDialog
            from PyQt6.QtWidgets import QDialog
            dialog = CategorySelectDialog(self.category_manager, task_name, self)
            if group_tag:
                if hasattr(dialog, "set_initial_group"): dialog.set_initial_group(group_tag)
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                cat_id = dialog.selected_category_id
                cat_group = dialog.selected_group_name
                logger.info(f"[DEBUG] 分类已选: {cat_group}, ID: {cat_id}")
                self.current_focus_task_id = task_id
                self.logic.start_with_context(task_name, cat_id, cat_group)
            else:
                logger.info("[DEBUG] 用户取消选择")
        else:
            logger.error(f"[ERROR] 逻辑层或分类管理器缺失: Logic={bool(self.logic)}, CM={bool(self.category_manager)}")

    def _on_complete_clicked(self, task_data):
        tid = task_data["id"]
        title = task_data.get("title", "")
        priority = task_data.get("priority", 0)
        
        # 积分入账及本地标记（防止被判定为外部完成）
        try:
            from database import StudyLogger
            db = StudyLogger(self.config)
            coins = task_data.get('reward_coins', db.get_item_reward('task', tid, 0.1))
            db.add_external_reward(f"task_{tid}", 'task', title, coins, status=1)
            db.add_ledger_entry(coins, 'task_complete', None, f'任务完成: {title}')
            logger.info(f"任务完成积分入账: +{coins} ({title})")
        except Exception as e:
            logger.error(f"任务积分入账失败: {e}")
        
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
        super().show(), self._do_refresh()
        self._on_logic_state_changed("", self.logic.current_state if self.logic else "stopped")
    def hide(self): self.settings.setValue("pos", self.pos()), super().hide()
    def _load_position(self):
        p = self.settings.value("pos")
        if p: self.move(p)
    def start_background_sync(self):
        self.sync_worker.refresh()
    def cleanup(self):
        self.sync_thread.quit(), self.sync_thread.wait()
