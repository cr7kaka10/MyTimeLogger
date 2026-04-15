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
        self.icon_label.setStyleSheet("font-family: 'Font Awesome 6 Free', 'Microsoft YaHei'; font-weight: 900; font-size: 28px; background: transparent; border: none;")

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
        self.icon_label.setStyleSheet(f"font-family: 'Font Awesome 6 Free', 'Microsoft YaHei'; font-weight: 900; font-size: 28px; color: {color}; background: transparent; border: none;")
        
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

    def __init__(self, logic, category_manager):
        super().__init__()
        self.logic = logic
        self.category_manager = category_manager
        
        self.setWindowFlags(
            Qt.WindowType.Tool | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setObjectName("ActivityPanel")

        self.buttons = []
        self._drag_pos = None

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
        title_label = QLabel("📊 柳比歇夫时间管理面板")
        title_label.setStyleSheet("color: #3B4252; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none;")
        
        manage_btn = QPushButton("⚙️ 管理")
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.setStyleSheet("""
            QPushButton { color: #5E81AC; background: transparent; font-size: 12px; border: none; }
            QPushButton:hover { color: #81A1C1; }
        """)
        manage_btn.clicked.connect(self._open_category_manager)

        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet("""
            QPushButton { color: #5E81AC; background: transparent; font-size: 12px; border: none; }
            QPushButton:hover { color: #81A1C1; }
        """)
        refresh_btn.clicked.connect(self.refresh_categories)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { color: #4C566A; background: transparent; font-size: 16px; border: none; font-weight: bold; }
            QPushButton:hover { color: #BF616A; }
        """)
        close_btn.clicked.connect(self.hide)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(refresh_btn)
        title_layout.addWidget(manage_btn)
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
        self.status_label.setStyleSheet("color: #5E81AC; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        bottom_layout.addWidget(self.status_label)
        
        bottom_layout.addStretch()
        
        self.start_btn = QPushButton("▶")
        self.start_btn.setFixedSize(24, 24)
        self.start_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_btn.clicked.connect(self._on_play_pause_clicked)
        self.start_btn.setStyleSheet("""
            QPushButton { background-color: transparent; color: #5E81AC; border: none; font-size: 18px; }
            QPushButton:hover { color: #81A1C1; }
        """)
        bottom_layout.addWidget(self.start_btn)
        
        self.end_break_btn = QPushButton("结束")
        self.end_break_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.end_break_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF5252; color: #FFFFFF; border: none;
                border-radius: 4px; padding: 2px 6px; font-size: 11px;
                font-family: 'Microsoft YaHei', 'Segoe UI', sans-serif; font-weight: bold;
            }
            QPushButton:hover { background-color: #FF1744; }
        """)
        self.end_break_btn.clicked.connect(self._on_end_break_clicked)
        self.end_break_btn.hide()
        bottom_layout.addWidget(self.end_break_btn)
        
        bg_layout.addLayout(bottom_layout)
        self._update_btn_visibility()

    def _open_category_manager(self):
        """打开分类管理弹窗"""
        dialog = CategoryManagerDialog(self.category_manager, self)
        if dialog.exec():
            # 用户修改了分类，刷新网格
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
        self.logic.start_with_context(cat_name, cat_id, group_name)
        self._update_button_states()

    def _on_logic_state_changed(self, text, state):
        self._update_button_states()
        self._update_btn_visibility()

    def _update_btn_visibility(self):
        state_name = self.logic.current_state
        if state_name in ["stopped", "long_break_finished"]:
            self.start_btn.setText("▶")
            self.start_btn.show()
            self.end_break_btn.hide()
        elif state_name in ["countup_studying", "long_breaking", "studying", "short_breaking"]:
            self.start_btn.setText("⏸")
            self.start_btn.show()
            self.end_break_btn.show()
        else:
            self.start_btn.hide()
            self.end_break_btn.hide()
            
        if self.logic.is_paused:
            self.start_btn.setText("▶")
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
        """每秒更新状态显示"""
        if not self.isVisible():
            return
            
        # 更新当前计时
        curr_id = self.logic.current_category_id
        if self.logic.current_state in ["studying", "countup_studying"] and not self.logic.is_paused:
            cat_name = "未分类"
            if curr_id:
                for btn in self.buttons:
                    if btn.category_data.get("id") == curr_id:
                        cat_name = btn.category_data.get("name")
                        break
            
            # 计算已进行或剩余时间
            if self.logic.current_state == "studying":
                remaining_ms = self.logic.timer.remainingTime()
                elapsed_sec = remaining_ms // 1000
                icon = "🔥倒计时"
            else:
                if self.logic.current_session_start_time:
                    elapsed_sec = int((datetime.now() - self.logic.current_session_start_time).total_seconds())
                else:
                    elapsed_sec = 0
                icon = "⏳已计"
                
            mins, secs = divmod(elapsed_sec, 60)
            self.status_label.setText(f"{icon} {cat_name} ⏱ {mins:02d}:{secs:02d}")
        elif self.logic.is_paused:
            self.status_label.setText("⏸️ 已暂停")
        else:
            self.status_label.setText("当前: 闲置 ⏱ 00:00")

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

    def showEvent(self, event):
        self.refresh_categories()
        super().showEvent(event)
