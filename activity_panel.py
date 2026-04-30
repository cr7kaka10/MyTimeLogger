# -*- coding: utf-8 -*-
"""
活动面板 (activity_panel.py)
===========================
柳比歇夫分类计时的主界面，网格排列类别图标，点击后联动主程序的计时逻辑。
"""

import sys
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QPushButton, QLabel, QFrame, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor
from datetime import datetime
import sqlite3

# 将在需要时导入避免循环甚至提前导入
from category_dialog import CategoryManagerDialog

class CategoryButton(QPushButton):
    """单项分类按钮"""
    category_clicked = pyqtSignal(dict)

    def __init__(self, category_data, parent=None):
        super().__init__(parent)
        self.category_data = category_data
        self.setFixedSize(64, 64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.is_active_category = False

        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(2)

        self.icon_label = QLabel(self.category_data.get("icon", "📌"))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-family: 'Microsoft YaHei', 'Segoe UI Emoji'; font-size: 28px; background: transparent; border: none;")

        self.name_label = QLabel(self.category_data.get("name", "未命名"))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-family: 'Microsoft YaHei'; font-size: 12px; font-weight: bold; background: transparent; border: none;")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)

        self.clicked.connect(lambda: self.category_clicked.emit(self.category_data))
        self.update_style()

    def set_active(self, active: bool):
        self.is_active_category = active
        self.update_style()

    def update_style(self):
        color = self.category_data.get("color", "#5E81AC")
        if color and not color.startswith('#') and len(color) in [3, 4, 6, 8]:
            color = '#' + color
        elif not color:
            color = "#5E81AC"
            
        # 文本统一黑色雅黑，图标跟随设定的颜色
        self.name_label.setStyleSheet(f"font-family: 'Microsoft YaHei'; font-size: 12px; font-weight: bold; color: #2E3440; background: transparent; border: none;")
        self.icon_label.setStyleSheet(f"font-family: 'Microsoft YaHei', 'Segoe UI Emoji'; font-size: 28px; color: {color}; background: transparent; border: none;")
        
        if self.is_active_category:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(0, 0, 0, 0.05);
                    border: none;
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    background-color: rgba(0, 0, 0, 0.04);
                    border: none;
                }}
            """)

class ActivityPanel(QWidget):
    """柳比歇夫活动面板"""

    def __init__(self, logic, category_manager, main_window=None):
        super().__init__()
        self.logic = logic
        self.category_manager = category_manager
        self.main_window = main_window
        self.buttons = []
        self._drag_pos = None
        self._db = None  # 延迟初始化
        
        self.setWindowFlags(
            Qt.WindowType.Tool | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("ActivityPanel")

        self._build_ui()
        
        # 定时器更新当前计时和今日汇总
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self._on_timer_tick)
        self.update_timer.start(1000)

        self.logic.state_changed.connect(self._on_logic_state_changed)

    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.bg_frame = QFrame(self)
        self.bg_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #D8DEE9;
                border-radius: 10px;
            }
        """)
        self.main_layout.addWidget(self.bg_frame)
        
        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setSpacing(10)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("📊 沉浸式学习")
        title_label.setStyleSheet("color: #3B4252; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none;")
        
        goals_btn = QPushButton("🎯 目标")
        goals_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        goals_btn.setStyleSheet("""
            QPushButton { color: #5E81AC; background: transparent; font-size: 12px; border: none; padding: 0 5px; }
            QPushButton:hover { color: #81A1C1; }
        """)
        if self.main_window and hasattr(self.main_window, "toggle_goals_panel"):
            goals_btn.clicked.connect(self.main_window.toggle_goals_panel)

        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton { color: #5E81AC; background: transparent; font-size: 16px; border: none; }
            QPushButton:hover { color: #81A1C1; }
        """)
        refresh_btn.clicked.connect(self.refresh_categories)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { color: #4C566A; background: transparent; font-size: 20px; border: none; font-weight: bold; }
            QPushButton:hover { color: #BF616A; }
        """)
        close_btn.clicked.connect(self.hide)

        checklist_btn = QPushButton("📋 清单")
        checklist_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        checklist_btn.setStyleSheet("""
            QPushButton { color: #5E81AC; background: transparent; font-size: 12px; border: none; padding: 0 5px; }
            QPushButton:hover { color: #81A1C1; }
        """)
        if self.main_window and hasattr(self.main_window, "toggle_daily_checklist"):
            checklist_btn.clicked.connect(self.main_window.toggle_daily_checklist)

        habit_btn = QPushButton("✅ 习惯")
        habit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        habit_btn.setStyleSheet("""
            QPushButton { color: #A3BE8C; background: transparent; font-size: 12px; border: none; padding: 0 5px; }
            QPushButton:hover { color: #8FBF65; }
        """)
        if self.main_window and hasattr(self.main_window, "toggle_habit_tracker"):
            habit_btn.clicked.connect(self.main_window.toggle_habit_tracker)

        shop_btn = QPushButton("🎁 奖励")
        shop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        shop_btn.setStyleSheet("""
            QPushButton { color: #EBCB8B; background: transparent; font-size: 12px; border: none; padding: 0 5px; font-weight: bold; }
            QPushButton:hover { color: #D9B44A; background: rgba(235, 203, 139, 0.1); border-radius: 4px; }
        """)
        if self.main_window and hasattr(self.main_window, "toggle_reward_shop"):
            shop_btn.clicked.connect(self.main_window.toggle_reward_shop)

        sleep_btn = QPushButton("🌙 睡眠")
        sleep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sleep_btn.setStyleSheet("""
            QPushButton { color: #81A1C1; background: transparent; font-size: 12px; border: none; padding: 0 5px; }
            QPushButton:hover { color: #5E81AC; }
        """)
        if self.main_window and hasattr(self.main_window, "toggle_sleep_statistics"):
            sleep_btn.clicked.connect(self.main_window.toggle_sleep_statistics)

        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(goals_btn)
        title_layout.addWidget(shop_btn)
        title_layout.addWidget(habit_btn)
        title_layout.addWidget(sleep_btn)
        title_layout.addWidget(checklist_btn)
        title_layout.addSpacing(5)
        title_layout.addWidget(refresh_btn)
        title_layout.addWidget(close_btn)
        bg_layout.addLayout(title_layout)

        # 分类网格区域
        self.grid_layout = QVBoxLayout()
        bg_layout.addLayout(self.grid_layout)
        self.refresh_categories()

        # 底部状态栏及控制按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(10, 5, 10, 5)

        self.status_label = QLabel("当前: 无 ⏱ 00:00")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setStyleSheet("color: #5E81AC; font-family: 'Font Awesome 6 Free', 'Microsoft YaHei'; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        bottom_layout.addWidget(self.status_label)

        bottom_layout.addStretch()

        self.claim_btn = QPushButton("🎁 待领取(0)")
        self.claim_btn.setStyleSheet(f"QPushButton {{ color: #D08770; background: transparent; font-size: 12px; border: none; font-weight: bold; padding-right: 10px; }} QPushButton:hover {{ color: #A3BE8C; }}")
        self.claim_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.claim_btn.clicked.connect(self._on_claim_clicked)
        self.claim_btn.hide()
        bottom_layout.addWidget(self.claim_btn)

        self.start_btn = QPushButton("\uf04b")
        self.start_btn.setFixedSize(24, 24)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_play_pause_clicked)
        self.start_btn.setStyleSheet("""
            QPushButton { font-family: 'Font Awesome 6 Free'; font-weight: 900; background-color: #5E81AC; color: white; border: none; border-radius: 4px; font-size: 10px; padding-left: 2px; }
            QPushButton:hover { background-color: #81A1C1; }
        """)
        bottom_layout.addWidget(self.start_btn)
        
        self.end_break_btn = QPushButton("\uf04d")
        self.end_break_btn.setFixedSize(24, 24)
        self.end_break_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end_break_btn.setStyleSheet("""
            QPushButton { font-family: 'Font Awesome 6 Free'; font-weight: 900; background-color: #FF5252; color: white; border: none; border-radius: 4px; font-size: 10px; }
            QPushButton:hover { background-color: #FF1744; }
        """)
        self.end_break_btn.clicked.connect(self._on_end_break_clicked)
        self.end_break_btn.hide()
        bottom_layout.addWidget(self.end_break_btn)
        
        bg_layout.addLayout(bottom_layout)
        self._update_btn_visibility()

    def _open_category_manager(self):
        """此功能已移至主程序右键设置"""
        if self.main_window and hasattr(self.main_window, "_open_category_manager"):
            self.main_window._open_category_manager()
        else:
            # 回退逻辑
            dialog = CategoryManagerDialog(self.category_manager, self)
            if dialog.exec():
                self.refresh_categories()

    def _clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
                else:
                    sub_layout = item.layout()
                    if sub_layout is not None:
                        self._clear_layout(sub_layout)
                        sub_layout.deleteLater()

    def refresh_categories(self):
        """重新渲染分类网格"""
        # 清空旧布局，必须递归删除子控件防止重叠
        self._clear_layout(self.grid_layout)
        
        self.buttons.clear()
        all_cats = self.category_manager.get_all_active()
        if not all_cats:
            return
            
        grid = QGridLayout()
        grid.setSpacing(8)
        
        # 强制设置5列拉伸策略
        for j in range(5):
            grid.setColumnStretch(j, 1)
            grid.setColumnMinimumWidth(j, 68)
            
        for i, cat in enumerate(all_cats):
            btn = CategoryButton(cat)
            btn.category_clicked.connect(self._on_category_clicked)
            grid.addWidget(btn, i // 5, i % 5)
            self.buttons.append(btn)
            
        self.grid_layout.addLayout(grid)
            
        self._update_button_states()

    def _on_category_clicked(self, cat_data):
        cat_id = cat_data.get("id")
        cat_name = cat_data.get("name")
        group_name = cat_data.get("group_name")
        self.logic.start_with_context(cat_name, cat_id, group_name, category_name=cat_name)
        self._update_button_states()

    def _on_logic_state_changed(self, text, state):
        self._update_button_states()
        self._update_btn_visibility()

    def _update_btn_visibility(self):
        state_name = self.logic.current_state
        if state_name in ["stopped", "long_break_finished"]:
            self.start_btn.setText("\uf04b")
            self.start_btn.setStyleSheet("""
                QPushButton { font-family: 'Font Awesome 6 Free'; font-weight: 900; background-color: #5E81AC; color: white; border: none; border-radius: 4px; font-size: 10px; padding-left: 2px; }
                QPushButton:hover { background-color: #81A1C1; }
            """)
            self.start_btn.show()
            self.end_break_btn.hide()
        elif state_name in ["countup_studying", "long_breaking", "studying", "short_breaking"]:
            self.start_btn.setText("\uf04c")
            self.start_btn.setStyleSheet("""
                QPushButton { font-family: 'Font Awesome 6 Free'; font-weight: 900; background-color: #D08770; color: white; border: none; border-radius: 4px; font-size: 10px; padding-left: 1px; }
                QPushButton:hover { background-color: #BF616A; }
            """)
            self.start_btn.show()
            self.end_break_btn.show()
        else:
            self.start_btn.hide()
            self.end_break_btn.hide()
            
        if self.logic.is_paused:
            self.start_btn.setText("\uf04b")
            self.start_btn.setStyleSheet("""
                QPushButton { font-family: 'Font Awesome 6 Free'; font-weight: 900; background-color: #5E81AC; color: white; border: none; border-radius: 4px; font-size: 10px; padding-left: 2px; }
                QPushButton:hover { background-color: #81A1C1; }
            """)
            self.start_btn.show()

    def _on_play_pause_clicked(self):
        state = self.logic.current_state
        if state in ["stopped", "long_break_finished"]:
            self.logic.start_only()
        elif self.logic.is_paused:
            self.logic.toggle_pause()
        elif state in ["studying", "countup_studying", "short_breaking", "long_breaking"]:
            self.logic.toggle_pause()

    def _on_end_break_clicked(self):
        if self.logic.current_state == "countup_studying":
            self.logic.end_countup_now()
        elif self.logic.current_state == "studying":
            self.logic.end_study_now()
        else:
            self.logic.end_break_now()

    def _update_button_states(self):
        curr_id = self.logic.current_category_id
        for btn in self.buttons:
            is_active = (curr_id == btn.category_data.get("id")) and self.logic.current_state in ["studying", "countup_studying"]
            btn.set_active(is_active)

    def _on_timer_tick(self):
        """每秒更新状态显示 - 同步mini面板完整信息"""
        if not self.isVisible():
            return
        
        # 获取当前分类信息
        curr_id = self.logic.current_category_id
        cat_name = "未分类"
        cat_icon = "⏳"
        cat_color = "#5E81AC"
        if curr_id:
            for btn in self.buttons:
                if btn.category_data.get("id") == curr_id:
                    cat_name = btn.category_data.get("name")
                    cat_icon = btn.category_data.get("icon", "⏳")
                    cat_color = btn.category_data.get("color", "#5E81AC")
                    break
        
        # 计算周期剩余时间（距长休息）
        threshold = getattr(self.logic, 'config', {}).get("long_break_threshold", 90 * 60) if hasattr(self.logic, 'config') else 90 * 60
        active_cycle_time = getattr(self.logic, 'current_cycle_study_time', 0)
        if self.logic.current_state == "studying" and self.logic.timer.isActive():
            session_elapsed = getattr(self.logic, 'current_session_duration', 0) - (self.logic.timer.remainingTime() // 1000)
            active_cycle_time += session_elapsed
        remaining_cycle = max(0, threshold - active_cycle_time)
        cycle_mins, cycle_secs = divmod(int(remaining_cycle), 60)
        
        # 构建状态文本 - 只显示分类名称、计时、周期剩余
        if self.logic.current_state in ["studying", "countup_studying"] and not self.logic.is_paused:
            if self.logic.current_state == "studying":
                up_m, up_s = divmod(int(active_cycle_time), 60)
                status_text = f'<span style="color: {cat_color};">{cat_icon}</span> {cat_name}'
                timer_text = f"⏱ {up_m:02d}:{up_s:02d}"
            else:
                if self.logic.current_session_start_time:
                    elapsed_sec = int((datetime.now() - self.logic.current_session_start_time).total_seconds())
                else:
                    elapsed_sec = 0
                m, s = divmod(elapsed_sec, 60)
                status_text = f'<span style="color: {cat_color};">{cat_icon}</span> {cat_name}'
                timer_text = f"⏱ {m:02d}:{s:02d}"
            
            cycle_text = f"🎯 {cycle_mins:02d}:{cycle_secs:02d}"
            coin_text = self._coin_text()
            self.status_label.setText(f"{status_text}     {timer_text}     {cycle_text}     {coin_text}")
        elif self.logic.is_paused:
            coin_text = self._coin_text()
            self.status_label.setText(f"⏸️ 已暂停     🎯 {cycle_mins:02d}:{cycle_secs:02d}     {coin_text}")
        elif self.logic.current_state == "long_breaking":
            if self.logic.timer.isActive():
                remaining_ms = self.logic.timer.remainingTime()
                mins, secs = divmod(remaining_ms // 1000, 60)
                self.status_label.setText(f"🧘 长休息     ⏱ {mins:02d}:{secs:02d}")
            else:
                self.status_label.setText("🧘 长休息")
        elif self.logic.current_state == "short_breaking":
            if self.logic.timer.isActive():
                remaining_ms = self.logic.timer.remainingTime()
                mins, secs = divmod(remaining_ms // 1000, 60)
                self.status_label.setText(f"☕ 短暂休息     ⏱ {mins:02d}:{secs:02d}")
            else:
                self.status_label.setText("☕ 短暂休息")
        else:
            coin_text = self._coin_text()
            self.status_label.setText(f"闲置     🎯 {cycle_mins:02d}:{cycle_secs:02d}     {coin_text}")

    def _coin_text(self):
        """获取金币余额文本及更新待领取按钮"""
        try:
            if getattr(self, '_db', None) is None:
                from database import StudyLogger
                self._db = StudyLogger({})
            
            unclaimed = self._db.get_unclaimed_rewards()
            if unclaimed:
                total_coins = sum(r.get('coins', 0) for r in unclaimed)
                self.claim_btn.setText(f"🎁 待领取({total_coins:g}🪙)")
                self.claim_btn.show()
            else:
                self.claim_btn.hide()
            
            return f"💰 {self._db.get_balance()}🪙"
        except Exception as e:
            print(f"Error in _coin_text: {e}")
            return ""

    def _on_claim_clicked(self):
        if getattr(self, '_db', None) is None:
            from database import StudyLogger
            self._db = StudyLogger({})
        
        unclaimed = self._db.get_unclaimed_rewards()
        if not unclaimed:
            return

        ids = [i['id'] for i in unclaimed]
        names = [i.get('item_name', '未知项') for i in unclaimed]
        claimed_coins = self._db.claim_rewards(ids)
        if claimed_coins > 0:
            desc = "领取外部奖励: " + ", ".join(names)
            if len(desc) > 100:
                desc = desc[:97] + "..."
            self._db.add_ledger_entry(claimed_coins, 'external_claim', None, desc)
            self._show_coin_toast(claimed_coins)
            self._on_timer_tick()
            from particle_effect import start_coin_explosion, show_success_effect
            start_coin_explosion(self, self.claim_btn, len(ids))
            show_success_effect(self)

    def _show_coin_toast(self, coins):
        """积分变动 toast 动画"""
        from PyQt6.QtWidgets import QLabel, QGraphicsOpacityEffect
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, QPoint
        sign = '+' if coins > 0 else ''
        color = "#D08770" if coins > 0 else "#BF616A"
        toast = QLabel(f"{sign}{coins}🪙", self)
        toast.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold; background: transparent;")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setFixedSize(160, 40)
        toast.move(self.width() // 2 - 80, self.height() // 2 - 20)
        toast.show()

        effect = QGraphicsOpacityEffect(toast)
        toast.setGraphicsEffect(effect)

        anim = QPropertyAnimation(effect, b"opacity", toast)
        anim.setDuration(1200)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        move_anim = QPropertyAnimation(toast, b"pos", toast)
        move_anim.setDuration(1200)
        move_anim.setStartValue(toast.pos())
        move_anim.setEndValue(toast.pos() - QPoint(0, 60))
        move_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        if not hasattr(self, '_anims'):
            self._anims = []
        self._anims.extend([anim, move_anim])
        
        def on_finished():
            toast.deleteLater()
            if anim in getattr(self, '_anims', []): self._anims.remove(anim)
            if move_anim in getattr(self, '_anims', []): self._anims.remove(move_anim)

        anim.finished.connect(on_finished)
        anim.start()
        move_anim.start()

    def _update_summary(self):
        """计算今日各分组的时间汇总"""
        today_str = datetime.now().strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.category_manager.db_path)
        cursor = conn.cursor()
        
        # 关联分类表计算今日时间
        try:
            cursor.execute('''
                SELECT c.group_name, SUM(s.net_duration_minutes) 
                FROM study_sessions s
                LEFT JOIN categories c ON s.category_id = c.id
                WHERE s.date = ?
                GROUP BY c.group_name
            ''', (today_str,))
            rows = cursor.fetchall()
            conn.close()
            
            summary = {"输入": 0, "输出": 0, "生活": 0, "未分类": 0}
            for row in rows:
                grp = row[0] if row[0] else "未分类"
                mins = int(row[1]) if row[1] else 0
                if grp in summary:
                    summary[grp] = mins
                else:
                    summary["未分类"] += mins
            
            # 原有的汇总逻辑已禁用，保留方法体但不更新界面
            pass
        except Exception as e:
            pass

    # 拖拽支持
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def contextMenuEvent(self, event):
        """右键菜单 - 复用主窗口菜单"""
        if self.main_window and hasattr(self.main_window, 'populate_context_menu'):
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            self.main_window.populate_context_menu(menu)
            menu.exec(event.globalPos())

    def showEvent(self, event):
        self.refresh_categories()
        super().showEvent(event)
