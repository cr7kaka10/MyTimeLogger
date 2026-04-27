# -*- coding: utf-8 -*-
"""
习惯打卡模块 (habit_tracker.py)
================================
与滴答清单双向同步：习惯列表从滴答清单拉取（只读），
打卡/取消打卡操作推送到滴答清单。
"""

import logging
from datetime import datetime, timedelta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QFrame, QStackedWidget, QGridLayout,
    QGraphicsOpacityEffect, QMessageBox
)
from PyQt6.QtCore import Qt, QSettings, QPropertyAnimation, QEasingCurve, QPoint, QTimer, pyqtSignal
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
UNCHECKED_BG = "transparent"
COIN_ICON = "🪙"


class HabitCard(QFrame):
    """单个习惯打卡卡片 (从滴答清单同步)"""
    def __init__(self, habit_data, is_checked=False, parent=None):
        super().__init__(parent)
        self.habit_data = habit_data
        self.is_checked = is_checked
        self.setObjectName("habitCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._update_style()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        # 图标
        icon_text = self.habit_data.get('icon', '✅')
        self.icon_label = QLabel(icon_text)
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 24px; background: transparent; border: none;")
        layout.addWidget(self.icon_label)

        # 名称 + 频率
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        self.title_label = QLabel(self.habit_data.get('name', '未命名'))
        self.title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none;")
        info_layout.addWidget(self.title_label)

        # 频率/目标 + 奖励
        goal = self.habit_data.get('goal', 1)
        unit = self.habit_data.get('unit', '次')
        total = self.habit_data.get('totalCheckIns', 0)
        reward_coins = self.habit_data.get('reward_coins', 1.0)
        freq_text = f"目标: {int(goal)}{unit} · 累计打卡 {total} 次 · 🪙{reward_coins:.0f}"
        self.freq_label = QLabel(freq_text)
        self.freq_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        info_layout.addWidget(self.freq_label)
        layout.addLayout(info_layout, 1)

        # 打卡按钮
        self.check_btn = QPushButton()
        self.check_btn.setFixedSize(36, 36)
        layout.addWidget(self.check_btn)

    def _update_style(self):
        if self.is_checked:
            bg = CHECKED_BG
            border_c = GREEN_ACCENT
            self.check_btn.setText("✓")
            self.check_btn.setStyleSheet(f"""
                QPushButton {{ font-size: 16px; font-weight: bold; color: white; background: {GREEN_ACCENT};
                    border: none; border-radius: 18px; }}
                QPushButton:hover {{ background: {GREEN_HOVER}; }}
            """)
            self.title_label.setStyleSheet(f"color: {GREEN_ACCENT}; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei'; background: transparent; border: none; text-decoration: line-through;")
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

    def set_checked(self, checked: bool):
        self.is_checked = checked
        self._update_style()

    def contextMenuEvent(self, event):
        """ 右键菜单设置奖励"""
        from PyQt6.QtWidgets import QMenu, QInputDialog
        from PyQt6.QtGui import QAction
        from database import StudyLogger

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: white; border: 1px solid #D8DEE9; border-radius: 6px; padding: 4px; }
            QMenu::item { padding: 6px 24px; color: #2E3440; font-size: 13px; }
            QMenu::item:selected { background-color: rgba(163, 190, 140, 0.1); color: #A3BE8C; border-radius: 4px; }
        """)
        current = self.habit_data.get('reward_coins', 1.0)
        action = QAction(f"🪙 设置奖励 (当前: {current:.0f})", self)
        action.triggered.connect(self._set_reward)
        menu.addAction(action)
        menu.exec(event.globalPos())

    def _set_reward(self):
        from PyQt6.QtWidgets import QInputDialog
        from database import StudyLogger
        current = self.habit_data.get('reward_coins', 1.0)
        val, ok = QInputDialog.getDouble(self, "设置奖励", f"完成打卡奖励金币数:", current, 0, 100, 1)
        if ok:
            db = StudyLogger({})
            db.set_item_reward('habit', self.habit_data['id'], val)
            self.habit_data['reward_coins'] = val
            # 更新显示
            goal = self.habit_data.get('goal', 1)
            unit = self.habit_data.get('unit', '次')
            total = self.habit_data.get('totalCheckIns', 0)
            self.freq_label.setText(f"目标: {int(goal)}{unit} · 累计打卡 {total} 次 · 🪙{val:.0f}")


class HabitWeeklyView(QWidget):
    """周打卡视图（网格）- 从滴答清单同步"""
    def __init__(self, parent_window):
        super().__init__(parent_window)
        self.parent_window = parent_window

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

    def refresh(self, habits, checkins_map):
        """
        habits: list of API habit dicts
        checkins_map: {habit_id: {date_str(YYYYMMDD): status}}
        """
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.deleteLater()

        if not habits:
            lbl = QLabel("滴答清单中没有习惯数据 📭")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px; padding: 40px;")
            self.grid.addWidget(lbl, 0, 0)
            return

        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        dates = [start_of_week + timedelta(days=i) for i in range(7)]
        date_stamps = [d.strftime('%Y%m%d') for d in dates]
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]

        # 表头
        for c, d in enumerate(dates):
            is_today = (d == today)
            color = GREEN_ACCENT if is_today else TEXT_SECONDARY
            font_w = "bold" if is_today else "normal"
            lbl = QLabel(f"{weekdays[c]}\n{d.day}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: {font_w};")
            self.grid.addWidget(lbl, 0, c + 1)

        # 行
        for r, habit in enumerate(habits):
            h_id = habit['id']
            h_icon = self._parse_icon(habit)
            h_title = habit.get('name', '')

            name_layout = QHBoxLayout()
            name_layout.setContentsMargins(0, 0, 0, 0)
            icon_lbl = QLabel(h_icon)
            icon_lbl.setStyleSheet("font-size: 18px;")
            title_lbl = QLabel(h_title)
            title_lbl.setStyleSheet(f"font-size: 13px; color:{TEXT_PRIMARY}; font-weight: bold;")
            name_layout.addWidget(icon_lbl)
            name_layout.addWidget(title_lbl)
            name_layout.addStretch()

            name_widget = QWidget()
            name_widget.setLayout(name_layout)
            name_widget.setMinimumWidth(160)
            self.grid.addWidget(name_widget, r + 1, 0, alignment=Qt.AlignmentFlag.AlignLeft)

            habit_checkins = checkins_map.get(h_id, {})
            for c, stamp in enumerate(date_stamps):
                d_obj = dates[c]
                is_future = d_obj > today
                status = habit_checkins.get(stamp, None)

                btn = QPushButton()
                btn.setFixedSize(28, 28)
                if status == 0:  # 已完成
                    btn.setText("✓")
                    btn.setStyleSheet(f"QPushButton {{ background: {GREEN_ACCENT}; color: white; border: none; border-radius: 14px; font-size: 14px; font-weight: bold; }}")
                else:
                    if is_future:
                        btn.setStyleSheet("QPushButton { background: transparent; border: 2px dashed #E5E9F0; border-radius: 14px; }")
                        btn.setEnabled(False)
                    else:
                        btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 2px solid {BORDER_COLOR}; border-radius: 14px; }} QPushButton:hover {{ border-color: {GREEN_ACCENT}; background: rgba(163, 190, 140, 0.1); }}")

                if not is_future:
                    btn.setCursor(Qt.CursorShape.PointingHandCursor)
                    btn.clicked.connect(lambda checked, hid=h_id, s=stamp, st=status: self._on_checkin(hid, s, st))

                self.grid.addWidget(btn, r + 1, c + 1, alignment=Qt.AlignmentFlag.AlignCenter)

        self.grid.setRowStretch(len(habits) + 1, 1)

    def _on_checkin(self, hid, stamp, current_status):
        """周视图打卡/取消"""
        new_status = 2 if current_status == 0 else 0  # toggle
        self.parent_window._do_remote_checkin(hid, stamp, new_status)

    def _parse_icon(self, habit):
        icon_res = habit.get('iconRes', '')
        if icon_res.startswith('txt_'):
            return icon_res[4:]
        # 如果是内置系统代号（通常包含字母/下划线）或是空，使用默认图标
        if not icon_res or icon_res.startswith('habit_') or icon_res.isascii():
            return '🎯'
        return icon_res


class HabitTrackerWindow(QWidget):
    """习惯打卡主窗口 - 滴答清单同步版"""
    request_habit_checkin = pyqtSignal(str, str, int)
    request_sync = pyqtSignal()

    def __init__(self, config, sync_worker=None, parent=None):
        super().__init__(parent)
        self.config = config
        self.sync_worker = sync_worker
        self.db = StudyLogger(config)
        self.settings = QSettings("MyTimeLogger", "HabitTracker")
        self.habit_cards = {}
        self._cached_habits = []
        self._cached_checkins = {}  # {habit_id: {stamp: status}}

        if self.sync_worker:
            self.request_habit_checkin.connect(self.sync_worker.sync_habit_checkin)
            self.request_sync.connect(self.sync_worker.refresh)
            self.sync_worker.habits_ready.connect(self._on_habits_ready)

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

        # 同步按钮
        sync_btn = QPushButton("🔄")
        sync_btn.setFixedSize(30, 30)
        sync_btn.setToolTip("从滴答清单同步")
        sync_btn.setStyleSheet(f"QPushButton {{ color: {GREEN_ACCENT}; background: transparent; font-size: 18px; border: none; }} QPushButton:hover {{ background: rgba(163, 190, 140, 0.15); border-radius: 6px; }}")
        sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        sync_btn.clicked.connect(self._refresh)
        header_layout.addWidget(sync_btn)

        btn_style = f"QPushButton {{ color: {TEXT_SECONDARY}; background: transparent; font-size: 16px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {GREEN_ACCENT}; }}"
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet(btn_style)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        # ====== 今日日期 ======
        self.date_bar = QLabel(datetime.now().strftime("📅 %Y年%m月%d日 %A"))
        self.date_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_bar.setFixedHeight(28)
        self.date_bar.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; background: #F8F9FB; border-top: 1px solid #F0F2F5; border-bottom: 1px solid #F0F2F5;")
        layout.addWidget(self.date_bar)

        # ====== 数据来源提示 ======
        source_bar = QLabel("📡 数据来源：滴答清单")
        source_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        source_bar.setFixedHeight(20)
        source_bar.setStyleSheet(f"color: #88C0D0; font-size: 10px; background: rgba(136, 192, 208, 0.08);")
        layout.addWidget(source_bar)

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

        self.empty_label = QLabel("正在从滴答清单同步习惯... 🔄")
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

    def _parse_icon(self, habit):
        """解析滴答清单的 iconRes 字段"""
        icon_res = habit.get('iconRes', '')
        if icon_res.startswith('txt_'):
            return icon_res[4:]
        # 如果是内置系统代号（通常包含字母/下划线）或是空，使用默认图标
        if not icon_res or icon_res.startswith('habit_') or icon_res.isascii():
            return '🎯'
        return icon_res

    def _refresh(self):
        """请求后台从滴答清单拉取最新习惯和打卡数据"""
        if not self.sync_worker:
            self.empty_label.setText("未配置滴答清单同步 ❌")
            self.empty_label.show()
            return
            
        self.request_sync.emit()

    def _on_habits_ready(self, habits, checkins_map):
        """收到后台拉取的数据后更新本地缓存和界面"""
        self._cached_habits = habits
        self._cached_checkins = checkins_map
        self._update_ui_from_cache()

    def _update_ui_from_cache(self):
        """仅根据本地缓存重新渲染UI"""
        today_stamp = datetime.now().strftime('%Y%m%d')
        # 渲染日视图
        self._render_daily(self._cached_habits, today_stamp)
        # 渲染周视图
        self.weekly_view_widget.refresh(self._cached_habits, self._cached_checkins)

        # 更新状态栏
        total = len(self._cached_habits)
        done = sum(1 for h in self._cached_habits if self._cached_checkins.get(h['id'], {}).get(today_stamp) == 0)
        balance = self.db.get_balance()
        self.status_bar.setText(f"📊 今日: {done}/{total}  |  💰 {balance}{COIN_ICON}")

    def _render_daily(self, habits, today_stamp):
        """渲染日视图的习惯卡片"""
        # 清理旧卡片
        for card in self.habit_cards.values():
            card.deleteLater()
        self.habit_cards.clear()

        while self.habit_layout.count() > 1:
            item = self.habit_layout.takeAt(0)
            if item.widget() and item.widget() != self.empty_label:
                item.widget().deleteLater()

        if not habits:
            self.empty_label.setText("滴答清单中没有活跃习惯 📭\n请在滴答清单 App 中添加习惯")
            self.empty_label.show()
            return

        self.empty_label.hide()

        for habit in habits:
            hid = habit['id']
            is_checked = self._cached_checkins.get(hid, {}).get(today_stamp) == 0

            # 转换 icon
            habit_display = dict(habit)
            habit_display['icon'] = self._parse_icon(habit)
            habit_display['reward_coins'] = self.db.get_item_reward('habit', hid, 1.0)

            card = HabitCard(habit_display, is_checked)
            card.check_btn.clicked.connect(lambda _, h_id=hid, checked=is_checked: self._on_checkin(h_id, today_stamp, checked))
            self.habit_cards[hid] = card
            self.habit_layout.insertWidget(self.habit_layout.count() - 1, card)

    def _on_checkin(self, habit_id, stamp, currently_checked):
        """日视图打卡/取消打卡"""
        new_status = 2 if currently_checked else 0  # 0=完成, 2=取消
        self._do_remote_checkin(habit_id, stamp, new_status)

    def _do_remote_checkin(self, habit_id, stamp, new_status):
        """执行远端打卡并刷新"""
        if not self.sync_worker:
            return

        # 异步发送请求，不阻塞UI
        self.request_habit_checkin.emit(habit_id, stamp, new_status)

        # 本地积分处理
        reward = self.db.get_item_reward('habit', habit_id, 1.0)
        habit_name = next((h.get('name', '未知习惯') for h in self._cached_habits if h['id'] == habit_id), '未知习惯')
        ext_id = f"habit_{habit_id}_{stamp}"
        
        if new_status == 0:
            coins = reward
            self.db.add_external_reward(ext_id, 'habit', habit_name, coins, status=1)
            self.db.add_ledger_entry(coins, 'habit_complete', None, f"习惯打卡完成: {habit_name}")
            self._show_coin_toast(coins)
        elif new_status == 2:
            coins = -reward
            self.db.remove_external_reward(ext_id)
            self.db.add_ledger_entry(coins, 'habit_uncheck', None, f"取消习惯打卡: {habit_name}")
            self._show_coin_toast(coins)

        # 本地更新状态并刷新UI，不要马上调API去拉回旧数据
        if habit_id not in self._cached_checkins:
            self._cached_checkins[habit_id] = {}
        self._cached_checkins[habit_id][stamp] = new_status
        
        self._update_ui_from_cache()

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
