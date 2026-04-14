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
        self.icon_label.setStyleSheet("font-size: 20px; background: transparent;")

        self.name_label = QLabel(self.category_data.get("name", "未命名"))
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #D8DEE9; background: transparent;")

        layout.addWidget(self.icon_label)
        layout.addWidget(self.name_label)

        self.clicked.connect(lambda: self.category_clicked.emit(self.category_data))
        self.update_style()

    def set_active(self, active: bool):
        self.is_active_category = active
        self.update_style()

    def update_style(self):
        color = self.category_data.get("color", "#5E81AC")
        if self.is_active_category:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(59, 66, 82, 0.9);
                    border: 2px solid {color};
                    border-radius: 12px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(59, 66, 82, 0.6);
                    border: 1px solid rgba(76, 86, 106, 0.5);
                    border-radius: 12px;
                }}
                QPushButton:hover {{
                    background-color: rgba(67, 76, 94, 0.8);
                    border: 1px solid {color};
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
                background-color: rgba(46, 52, 64, 0.95);
                border: 1px solid #4C566A;
                border-radius: 10px;
            }
        """)
        self.main_layout.addWidget(self.bg_frame)
        
        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setSpacing(10)

        # 标题栏
        title_layout = QHBoxLayout()
        title_label = QLabel("📊 柳比歇夫时间管理面板")
        title_label.setStyleSheet("color: #ECEFF4; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none;")
        
        manage_btn = QPushButton("⚙️ 管理")
        manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        manage_btn.setStyleSheet("""
            QPushButton { color: #88C0D0; background: transparent; font-size: 12px; border: none; }
            QPushButton:hover { color: #EBCB8B; }
        """)
        manage_btn.clicked.connect(self._open_category_manager)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { color: #D8DEE9; background: transparent; font-size: 16px; border: none; font-weight: bold; }
            QPushButton:hover { color: #BF616A; }
        """)
        close_btn.clicked.connect(self.hide)
        
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        title_layout.addWidget(manage_btn)
        title_layout.addWidget(close_btn)
        bg_layout.addLayout(title_layout)

        # 分类网格区域
        self.grid_layout = QVBoxLayout()
        bg_layout.addLayout(self.grid_layout)
        self.refresh_categories()

        # 底部状态栏
        self.status_label = QLabel("当前: 无 ⏱ 00:00")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #A3BE8C; font-size: 13px; font-weight: bold; background: transparent; border: none; margin-top: 5px;")
        bg_layout.addWidget(self.status_label)

    def _open_category_manager(self):
        """打开分类管理弹窗"""
        dialog = CategoryManagerDialog(self.category_manager, self)
        if dialog.exec():
            # 用户修改了分类，刷新网格
            self.refresh_categories()

    def refresh_categories(self):
        """重新渲染分类网格"""
        # 清空旧布局
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # 嵌套的布局也需要清空，不过简单处理直接重新构建即可
                pass
        
        self.buttons.clear()
        grouped_cats = self.category_manager.get_grouped()
        
        for group_name, cats in grouped_cats.items():
            if not cats:
                continue
                
            # 分组标题
            grp_label = QLabel(f"── {group_name} ──")
            grp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grp_label.setStyleSheet("color: #4C566A; font-size: 11px; background: transparent; border: none;")
            self.grid_layout.addWidget(grp_label)
            
            # 分组网格 (每行5个)
            grid = QGridLayout()
            grid.setSpacing(8)
            
            # 由于子项可能不够5个，导致列不平均，强制设置5列拉伸策略
            for j in range(5):
                grid.setColumnStretch(j, 1)
                grid.setColumnMinimumWidth(j, 68)
                
            for i, cat in enumerate(cats):
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
            
            # 计算已进行时间
            if self.logic.current_state == "studying":
                remaining_ms = self.logic.timer.remainingTime()
                elapsed_sec = self.logic.current_session_duration - (remaining_ms // 1000)
                icon = "🔥"
            else:
                if self.logic.current_session_start_time:
                    elapsed_sec = int((datetime.now() - self.logic.current_session_start_time).total_seconds())
                else:
                    elapsed_sec = 0
                icon = "⏳"
                
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
