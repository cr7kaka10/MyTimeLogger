# -*- coding: utf-8 -*-
"""
习惯打卡模块 (habit_tracker.py)
================================
独立浮动窗口，支持习惯的三态打卡、打卡时间段限制以及周视图切换。
"""

import logging
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QFrame, QDialog, QLineEdit, QComboBox,
    QFormLayout, QMessageBox, QGridLayout, QStackedWidget, QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, QSettings, QPropertyAnimation, QEasingCurve, QPoint, QTimer
from PyQt6.QtGui import QFont, QColor

from database import StudyLogger

logger = logging.getLogger(__name__)

# ==================== 配色 ====================
TEXT_PRIMARY = "#2E3440"
TEXT_SECONDARY = "#4C566A"
BORDER_COLOR = "#D8DEE9"
GREEN_ACCENT = "#A3BE8C"
GREEN_HOVER = "#8FBF65"
RED_ACCENT = "#BF616A"
RED_HOVER = "#A54C53"
BG_LIGHT = "#FFFFFF"
CHECKED_BG = "rgba(163, 190, 140, 0.12)"
MISSED_BG = "rgba(191, 97, 106, 0.08)"
UNCHECKED_BG = "transparent"
COIN_ICON = "🪙"

DIFFICULTY_OPTIONS = [
    ('trivial', '🟢 简单'),
    ('easy',    '🟢 普通'),
    ('medium',  '🟡 中等'),
    ('hard',    '🔴 困难'),
]
DIFFICULTY_COLORS = {'trivial': '#4CAF50', 'easy': '#2196F3', 'medium': '#FF9800', 'hard': '#FF5252'}


class HabitAddDialog(QDialog):
    """新增/编辑习惯弹窗（含时间范围限制）"""
    def __init__(self, parent=None, edit_data=None):
        super().__init__(parent)
        self.edit_data = edit_data
        self.selected_icon = edit_data.get('icon', '✅') if edit_data else '✅'
        self.setWindowTitle("编辑习惯" if edit_data else "新增习惯")
        self.setFixedSize(380, 380)
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_LIGHT}; font-family: 'Microsoft YaHei'; }}
            QLineEdit, QComboBox {{ border: 1px solid {BORDER_COLOR}; border-radius: 6px; padding: 6px 10px; background: #F8F9FB; font-size: 13px; }}
            QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如：每日阅读30分钟")
        if self.edit_data:
            self.name_input.setText(self.edit_data.get('title', ''))

        # 图标选择按钮
        icon_row = QHBoxLayout()
        self.icon_btn = QPushButton(self.selected_icon)
        self.icon_btn.setFixedSize(40, 40)
        self.icon_btn.setStyleSheet(f"""
            QPushButton {{ font-size: 22px; background: #F0F2F5; border: 1px solid {BORDER_COLOR}; border-radius: 8px; }}
            QPushButton:hover {{ background: #E0E8F0; border-color: {GREEN_ACCENT}; }}
        """)
        self.icon_btn.clicked.connect(self._pick_icon)
        icon_row.addWidget(self.icon_btn)
        icon_row.addStretch()

        self.color_input = QLineEdit(self.edit_data.get('color', '#A3BE8C') if self.edit_data else '#A3BE8C')

        self.freq_combo = QComboBox()
        self.freq_combo.addItems(["每日", "每周"])
        if self.edit_data and self.edit_data.get('frequency') == 'weekly':
            self.freq_combo.setCurrentIndex(1)

        # 难度选择器
        self.diff_combo = QComboBox()
        for code, label in DIFFICULTY_OPTIONS:
            self.diff_combo.addItem(label, code)
        if self.edit_data:
            idx = next((i for i, (c, _) in enumerate(DIFFICULTY_OPTIONS) if c == self.edit_data.get('difficulty', 'easy')), 1)
            self.diff_combo.setCurrentIndex(idx)
        else:
            self.diff_combo.setCurrentIndex(1)  # 默认普通

        # 时间段
        time_row = QHBoxLayout()
        self.time_start = QLineEdit(self.edit_data.get('time_start', '') if self.edit_data else '')
        self.time_start.setPlaceholderText("00:00")
        self.time_end = QLineEdit(self.edit_data.get('time_end', '') if self.edit_data else '')
        self.time_end.setPlaceholderText("23:59")
        time_row.addWidget(self.time_start)
        time_row.addWidget(QLabel("到"))
        time_row.addWidget(self.time_end)

        form.addRow("名称:", self.name_input)
        form.addRow("图标:", icon_row)
        form.addRow("难度:", self.diff_combo)
        form.addRow("颜色:", self.color_input)
        form.addRow("频率:", self.freq_combo)
        form.addRow("时间限制:", time_row)
        
        hint = QLabel("（*时间留空即为全天任意时间打卡）")
        hint.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        
        layout.addLayout(form)
        layout.addWidget(hint)

        # 按钮
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(f"QPushButton {{ background: #E5E9F0; border: none; border-radius: 6px; padding: 8px 20px; color: {TEXT_SECONDARY}; font-weight: bold; }} QPushButton:hover {{ background: #D8DEE9; }}")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(f"QPushButton {{ background: {GREEN_ACCENT}; border: none; border-radius: 6px; padding: 8px 20px; color: white; font-weight: bold; }} QPushButton:hover {{ background: {GREEN_HOVER}; }}")
        save_btn.clicked.connect(self._on_save)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _pick_icon(self):
        from category_dialog import IconSelectorDialog
        d = IconSelectorDialog(self)
        if d.exec() == QDialog.DialogCode.Accepted and d.selected_icon:
            self.selected_icon = d.selected_icon
            self.icon_btn.setText(self.selected_icon)

    def _on_save(self):
        if not self.name_input.text().strip():
            QMessageBox.warning(self, "提示", "请输入习惯名称")
            return
        self.accept()

    def get_data(self):
        freq = 'daily' if self.freq_combo.currentIndex() == 0 else 'weekly'
        diff = self.diff_combo.currentData() or 'easy'
        return {
            'title': self.name_input.text().strip(),
            'icon': self.selected_icon,
            'color': self.color_input.text().strip() or '#A3BE8C',
            'frequency': freq,
            'time_start': self.time_start.text().strip() or None,
            'time_end': self.time_end.text().strip() or None,
            'difficulty': diff
        }


class HabitCard(QFrame):
    """单个习惯打卡卡片 (日视图，支持三态)"""
    def __init__(self, habit_data, status=0, streak=0, parent=None):
        super().__init__(parent)
        self.habit_data = habit_data
        self.status = status # 1=成功, -1=失败, 0=未打
        self.streak = streak
        self.setObjectName("habitCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._update_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # 图标
        self.icon_label = QLabel(self.habit_data.get('icon', '✅'))
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        layout.addWidget(self.icon_label)

        # 名称 + 状态(连续天数/时间限制)
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        name_layer = QHBoxLayout()
        self.title_label = QLabel(self.habit_data.get('title', '未命名'))
        self.title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none;")
        name_layer.addWidget(self.title_label)
        
        time_s = self.habit_data.get('time_start')
        time_e = self.habit_data.get('time_end')
        if time_s or time_e:
            time_lbl = QLabel(f"({time_s or '00:00'}~{time_e or '23:59'})")
            time_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
            name_layer.addWidget(time_lbl)
            
        name_layer.addStretch()
        
        info_layout.addLayout(name_layer)

        freq_text = "每日" if self.habit_data.get('frequency', 'daily') == 'daily' else "每周"
        streak_text = f"🔥 {self.streak}天" if self.streak > 0 else freq_text
        self.streak_label = QLabel(streak_text)
        self.streak_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")

        info_layout.addWidget(self.streak_label)
        layout.addLayout(info_layout, 1)

        # 三态打卡按钮
        self.check_btn = QPushButton()
        self.check_btn.setFixedSize(36, 36)
        self.check_btn.clicked.connect(self._on_check_clicked)
        layout.addWidget(self.check_btn)

    def _update_style(self):
        if self.status == 1:
            bg = CHECKED_BG
            border_c = GREEN_ACCENT
            self.check_btn.setText("✓")
            self.check_btn.setStyleSheet(f"""
                QPushButton {{ font-size: 16px; font-weight: bold; color: white; background: {GREEN_ACCENT};
                    border: none; border-radius: 18px; }}
                QPushButton:hover {{ background: {GREEN_HOVER}; }}
            """)
            self.title_label.setStyleSheet(f"color: {GREEN_ACCENT}; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none; text-decoration: line-through;")
        elif self.status == -1:
            bg = MISSED_BG
            border_c = RED_ACCENT
            self.check_btn.setText("×")
            self.check_btn.setStyleSheet(f"""
                QPushButton {{ font-size: 20px; font-weight: bold; color: white; background: {RED_ACCENT};
                    border: none; border-radius: 18px; }}
                QPushButton:hover {{ background: {RED_HOVER}; }}
            """)
            self.title_label.setStyleSheet(f"color: {RED_ACCENT}; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none; text-decoration: line-through;")
        else:
            bg = UNCHECKED_BG
            border_c = BORDER_COLOR
            self.check_btn.setText("○")
            self.check_btn.setStyleSheet(f"""
                QPushButton {{ font-size: 18px; color: {BORDER_COLOR}; background: transparent;
                    border: 2px solid {BORDER_COLOR}; border-radius: 18px; }}
                QPushButton:hover {{ border-color: {GREEN_ACCENT}; color: {GREEN_ACCENT}; }}
            """)
            self.title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none;")

        self.setStyleSheet(f"""
            #habitCard {{ background: {bg}; border: 1px solid {border_c}; border-radius: 10px; }}
            #habitCard:hover {{ background: rgba(163, 190, 140, 0.06); }}
        """)

    def set_status(self, status, streak=0):
        self.status = status
        self.streak = streak
        streak_text = f"🔥 {self.streak}天" if self.streak > 0 else ("每日" if self.habit_data.get('frequency') == 'daily' else "每周")
        self.streak_label.setText(streak_text)
        self._update_style()

    def _on_check_clicked(self):
        pass


class HabitWeeklyView(QWidget):
    """周打卡视图（网格）- 三态+拓宽"""
    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.db = parent_window.db
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.grid = QGridLayout(self.container)
        self.grid.setVerticalSpacing(16)
        self.grid.setHorizontalSpacing(10)
        self.grid.setContentsMargins(20, 15, 20, 15)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)
        self.scroll.setWidget(self.container)

    def refresh(self, habits):
        for i in reversed(range(self.grid.count())): 
            w = self.grid.itemAt(i).widget()
            if w:
                w.deleteLater()
                
        if not habits:
            lbl = QLabel("还没有习惯哦，在日视图添加一个吧 ✨")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px; padding: 40px;")
            self.grid.addWidget(lbl, 0, 0)
            return

        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        dates = [start_of_week + timedelta(days=i) for i in range(7)]
        date_strs = [d.strftime('%Y-%m-%d') for d in dates]
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        
        # 返回 {hid: {date_str: status}}
        checkins = self.db.get_checkins_by_date_range(date_strs[0], date_strs[-1])

        # 绘制表头
        for c, d in enumerate(dates):
            is_today = (d == today)
            color = GREEN_ACCENT if is_today else TEXT_SECONDARY
            font_w = "bold" if is_today else "normal"
            lbl = QLabel(f"{weekdays[c]}\n{d.day}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: {font_w};")
            self.grid.addWidget(lbl, 0, c + 1)
            
        # 绘制所有行
        for r, habit in enumerate(habits):
            h_id = habit['id']
            h_icon = habit.get('icon', '✅')
            h_title = habit.get('title', '')
            
            # 宽界面的图标+文字
            name_layout = QHBoxLayout()
            name_layout.setContentsMargins(0,0,0,0)
            icon_lbl = QLabel(h_icon)
            icon_lbl.setStyleSheet("font-size: 18px;")
            title_lbl = QLabel(h_title)
            title_lbl.setStyleSheet(f"font-size: 13px; color:{TEXT_PRIMARY}; font-weight: bold;")
            
            if habit.get('time_end'):
                time_lbl = QLabel(f"~{habit['time_end']}")
                time_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
            else:
                time_lbl = None
                
            name_layout.addWidget(icon_lbl)
            name_layout.addWidget(title_lbl)
            name_layout.addStretch()
            if time_lbl:
                name_layout.addWidget(time_lbl)
                
            name_widget = QWidget()
            name_widget.setLayout(name_layout)
            name_widget.setMinimumWidth(160)
            self.grid.addWidget(name_widget, r + 1, 0, alignment=Qt.AlignmentFlag.AlignLeft)
            
            habit_checkins = checkins.get(h_id, {})
            # 绘制 7 个卡槽
            for c, d_str in enumerate(date_strs):
                d_obj = dates[c]
                is_future = d_obj > today
                status = habit_checkins.get(d_str, 0)
                
                btn = QPushButton()
                btn.setFixedSize(28, 28)
                if status == 1:
                    btn.setText("✓")
                    btn.setStyleSheet(f"QPushButton {{ background: {GREEN_ACCENT}; color: white; border: none; border-radius: 14px; font-size: 14px; font-weight: bold; }}")
                elif status == -1:
                    btn.setText("×")
                    btn.setStyleSheet(f"QPushButton {{ background: {RED_ACCENT}; color: white; border: none; border-radius: 14px; font-size: 16px; font-weight: bold; }}")
                else:
                    if is_future:
                        btn.setStyleSheet("QPushButton { background: transparent; border: 2px dashed #E5E9F0; border-radius: 14px; }")
                        btn.setEnabled(False)
                    else:
                        btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 2px solid {BORDER_COLOR}; border-radius: 14px; }} QPushButton:hover {{ border-color: {GREEN_ACCENT}; background: rgba(163, 190, 140, 0.1); }}")
                        
                if not is_future:
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.clicked.connect(lambda checked, hid=h_id, ds=d_str: self._on_checkin(hid, ds))
                    
                self.grid.addWidget(btn, r + 1, c + 1, alignment=Qt.AlignmentFlag.AlignCenter)
                
        self.grid.setRowStretch(len(habits) + 1, 1)

    def _on_checkin(self, hid, d_str=None):
        if d_str is None:
            d_str = datetime.now().strftime('%Y-%m-%d')
            
        res, streak, coins = self.db.toggle_checkin(hid, d_str)
        if res == "timeout":
            reply = QMessageBox.question(
                self, "惩罚提醒",
                f"打卡已超过 10 秒保护期，强行修改将扣除 {StudyLogger.FORCE_CHANGE_FEE}{COIN_ICON} 手续费！\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.db.toggle_checkin(hid, d_str, force=True)
                self.parent_window._refresh()
            return
            
        self.parent_window._refresh()


class HabitTrackerWindow(QWidget):
    """习惯打卡主窗口 - 已加宽至 520"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = StudyLogger(config)
        self.settings = QSettings("MyTimeLogger", "HabitTracker")
        self.habit_cards = {}  

        self.setWindowTitle("习惯打卡")
        self.setFixedSize(520, 560)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dragPos = None

        self._build_ui()
        self._load_position()
        self._refresh()

    def _build_ui(self):
        self.bg = QFrame(self)
        self.bg.setObjectName("habitBg")
        self.bg.setGeometry(0, 0, 520, 560)
        self.bg.setStyleSheet(f"""
            #habitBg {{
                background-color: rgba(255, 255, 255, 0.98);
                border: 1px solid {BORDER_COLOR};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(self.bg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ====== 标题栏 ======
        header = QWidget()
        header.setFixedHeight(48)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)

        title_label = QLabel("✅ <b>习惯打卡</b>")
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-family: 'Microsoft YaHei';")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        # 分段控制器 (每日 / 本周)
        self.view_btn_daily = QPushButton("每日")
        self.view_btn_weekly = QPushButton("本周")
        for btn in (self.view_btn_daily, self.view_btn_weekly):
            btn.setFixedSize(48, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._update_tab_style(0)
        
        self.view_btn_daily.clicked.connect(lambda: self.set_view(0))
        self.view_btn_weekly.clicked.connect(lambda: self.set_view(1))
        
        tab_layout = QHBoxLayout()
        tab_layout.setSpacing(0)
        tab_layout.addWidget(self.view_btn_daily)
        tab_layout.addWidget(self.view_btn_weekly)
        
        tab_container = QWidget()
        tab_container.setLayout(tab_layout)
        tab_container.setStyleSheet(f"background: #F0F2F5; border-radius: 12px; padding: 2px;")
        
        header_layout.addWidget(tab_container)
        header_layout.addStretch()

        btn_style = f"QPushButton {{ color: {TEXT_SECONDARY}; background: transparent; font-size: 16px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {GREEN_ACCENT}; }}"
        add_btn = QPushButton("＋")
        add_btn.setFixedSize(30, 30)
        add_btn.setStyleSheet(f"QPushButton {{ color: {GREEN_ACCENT}; background: transparent; font-size: 20px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {GREEN_HOVER}; }}")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_habit)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet(btn_style)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)

        header_layout.addWidget(add_btn)

        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        # ====== 今日日期 ======
        self.date_bar = QLabel(datetime.now().strftime("📅 %Y年%m月%d日 %A"))
        self.date_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_bar.setFixedHeight(28)
        self.date_bar.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: #F8F9FB; border-top: 1px solid #F0F2F5; border-bottom: 1px solid #F0F2F5;")
        layout.addWidget(self.date_bar)

        # ====== 视图层 ======
        self.stack = QStackedWidget()
        
        # 0: 日视图
        self.daily_view_widget = QWidget()
        daily_layout = QVBoxLayout(self.daily_view_widget)
        daily_layout.setContentsMargins(0, 0, 0, 0)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.habit_layout = QVBoxLayout(self.container)
        self.habit_layout.setContentsMargins(30, 10, 30, 10)
        self.habit_layout.setSpacing(8)
        self.habit_layout.addStretch()

        self.empty_label = QLabel("还没有习惯哦\n点击右上角 ＋ 添加一个吧 ✨")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px; padding: 40px;")
        self.habit_layout.insertWidget(0, self.empty_label)

        self.scroll.setWidget(self.container)
        daily_layout.addWidget(self.scroll)
        
        # 1: 周视图
        self.weekly_view_widget = HabitWeeklyView(self)
        
        self.stack.addWidget(self.daily_view_widget)
        self.stack.addWidget(self.weekly_view_widget)
        layout.addWidget(self.stack)

        # 底部状态栏
        self.status_bar = QLabel("📊 今日进度: 0/0")
        self.status_bar.setFixedHeight(30)
        self.status_bar.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 0 16px; border-top: 1px solid #F0F2F5;")
        layout.addWidget(self.status_bar)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.bg)

    def _update_tab_style(self, idx):
        active_style = f"QPushButton {{ background: white; color: {TEXT_PRIMARY}; font-size: 11px; font-weight: bold; border-radius: 10px; border: 1px solid rgba(0,0,0,0.05); }}"
        inactive_style = f"QPushButton {{ background: transparent; color: {TEXT_SECONDARY}; font-size: 11px; border: none; }}"
        if idx == 0:
            self.view_btn_daily.setStyleSheet(active_style)
            self.view_btn_weekly.setStyleSheet(inactive_style)
        else:
            self.view_btn_daily.setStyleSheet(inactive_style)
            self.view_btn_weekly.setStyleSheet(active_style)

    def set_view(self, idx):
        self._update_tab_style(idx)
        self.stack.setCurrentIndex(idx)
        if idx == 1:
            self.date_bar.setText(f"📅 本周 ({datetime.now().strftime('%Y年%W周')})")
        else:
            self.date_bar.setText(datetime.now().strftime("📅 %Y年%m月%d日 %A"))
        self._refresh()

    def _refresh(self):
        """刷新当前视图和状态栏"""
        # 超时检测拦截
        self.db.auto_mark_missed_habits()
        
        habits = self.db.get_all_habits()
        
        for card in self.habit_cards.values():
            card.deleteLater()
        self.habit_cards.clear()
        
        while self.habit_layout.count() > 1:
            item = self.habit_layout.takeAt(0)
            if item.widget() and item.widget() != self.empty_label:
                item.widget().deleteLater()

        today_checkins = self.db.get_today_checkins()

        if not habits:
            self.empty_label.show()
        else:
            self.empty_label.hide()

        total = len(habits)
        done = 0
        for habit in habits:
            hid = habit['id']
            status = today_checkins.get(hid, 0)
            streak = self.db.get_habit_streak(hid)
            if status == 1:
                done += 1

            card = HabitCard(habit, status, streak)
            card.check_btn.clicked.disconnect()
            card.check_btn.clicked.connect(lambda _, hid=hid: self._on_checkin(hid))
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, h=habit: self._show_context_menu(h, pos))
            self.habit_cards[hid] = card
            self.habit_layout.insertWidget(self.habit_layout.count() - 1, card)

        self.weekly_view_widget.refresh(habits)
        balance = self.db.get_balance()
        self.status_bar.setText(f"📊 今日: {done}/{total}  |  💰 {balance}{COIN_ICON}")

    def _on_checkin(self, hid, d_str=None):
        if d_str is None:
            d_str = datetime.now().strftime('%Y-%m-%d')
            
        res, streak, coins = self.db.toggle_checkin(hid, d_str)
        if res == "timeout":
            reply = QMessageBox.question(
                self, "惩罚提醒",
                f"打卡已超过 10 秒保护期，强行修改将扣除 {StudyLogger.FORCE_CHANGE_FEE}{COIN_ICON} 手续费！\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                _, _, c = self.db.toggle_checkin(hid, d_str, force=True)
                self._refresh()
                if c != 0:
                    self._show_coin_toast(c)
            return
        
        if coins != 0:
            self._show_coin_toast(coins)
        self._refresh()

    def _show_coin_toast(self, coins):
        """积分变动 toast 动画"""
        sign = '+' if coins > 0 else ''
        color = GREEN_ACCENT if coins > 0 else RED_ACCENT
        toast = QLabel(f"{sign}{coins}{COIN_ICON}", self)
        toast.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: bold; background: transparent;")
        toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toast.setFixedSize(120, 30)
        toast.move(self.width() // 2 - 60, self.height() // 2)
        toast.show()
        
        effect = QGraphicsOpacityEffect(toast)
        toast.setGraphicsEffect(effect)
        
        anim = QPropertyAnimation(effect, b"opacity", toast)
        anim.setDuration(1200)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(toast.deleteLater)
        anim.start()
        
        move_anim = QPropertyAnimation(toast, b"pos", toast)
        move_anim.setDuration(1200)
        move_anim.setStartValue(toast.pos())
        move_anim.setEndValue(toast.pos() - QPoint(0, 50))
        move_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        move_anim.start()

    def _on_add_habit(self):
        dialog = HabitAddDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.db.add_habit(
                title=data['title'],
                icon=data['icon'],
                color=data['color'],
                frequency=data['frequency'],
                time_start=data['time_start'],
                time_end=data['time_end'],
                difficulty=data['difficulty']
            )
            self._refresh()

    def _show_context_menu(self, habit, pos):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: white; border: 1px solid {BORDER_COLOR}; border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px; color: {TEXT_PRIMARY}; font-size: 13px; }}
            QMenu::item:selected {{ background-color: rgba(163, 190, 140, 0.1); color: {GREEN_ACCENT}; border-radius: 4px; }}
        """)

        edit_action = QAction("✏️ 编辑", self)
        edit_action.triggered.connect(lambda: self._on_edit_habit(habit))
        menu.addAction(edit_action)

        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(lambda: self._on_delete_habit(habit))
        menu.addAction(delete_action)

        card = self.habit_cards.get(habit['id'])
        if card:
            menu.exec(card.mapToGlobal(pos))

    def _on_edit_habit(self, habit):
        dialog = HabitAddDialog(self, edit_data=habit)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.db.update_habit(habit['id'], **data)
            self._refresh()

    def _on_delete_habit(self, habit):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除习惯「{habit['title']}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.remove_habit(habit['id'])
            self._refresh()

    # ======================== 窗口交互 ========================
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.dragPos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.MouseButton.LeftButton and self.dragPos:
            self.move(e.globalPosition().toPoint() - self.dragPos)

    def mouseReleaseEvent(self, e):
        self.dragPos = None

    def show(self):
        super().show()
        self._refresh()

    def hide(self):
        self.settings.setValue("pos", self.pos())
        super().hide()

    def _load_position(self):
        p = self.settings.value("pos")
        if p:
            self.move(p)
