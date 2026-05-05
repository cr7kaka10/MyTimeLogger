# -*- coding: utf-8 -*-
"""
目标挑战模块 (goals_panel.py)
==========================
实现类似 aTimeLogger Pro 的目标功能：
- 设置分类、周期、指标、目标值和奖励/惩罚
- 支持金币奖励或关联兑换项
- 实时计算并展示进度 (支持计时器实时刷新)
- 支持 "每次" 周期及 "大于等于/小于等于" 条件
"""

import logging
import calendar
from datetime import datetime, date, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QScrollArea, QFrame, QDialog, QComboBox, 
    QLineEdit, QSpinBox, QDoubleSpinBox, QMessageBox, QGridLayout, QStackedWidget,
    QGraphicsOpacityEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer, QPoint
from PyQt6.QtGui import QIcon, QFont, QColor

# 样式常量 (与项目 Nord 风格保持一致)
BG_COLOR = "#FFFFFF"
BORDER_COLOR = "#E5E9F0"
TEXT_PRIMARY = "#2E3440"
TEXT_SECONDARY = "#4C566A"
GOLD_ACCENT = "#EBCB8B"
GREEN_ACCENT = "#A3BE8C"
BLUE_ACCENT = "#81A1C1"
RED_ACCENT = "#BF616A"

COIN_ICON = "🪙"

class GoalStatsDialog(QDialog):
    """目标历史完成情况统计图 (月视图/周视图)"""
    def __init__(self, goal_data, db, parent=None):
        super().__init__(parent)
        self.goal_data = goal_data
        self.db = db
        self.current_date = date.today()
        self.view_mode = "month" # "month" or "week"
        
        self.setWindowTitle(f"目标统计: {goal_data['title']}")
        self.setMinimumSize(400, 420)
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_COLOR}; }}
            QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; font-family: 'Microsoft YaHei'; }}
            QPushButton {{ background: #F0F2F5; color: {TEXT_PRIMARY}; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }}
            QPushButton:hover {{ background: #E5E9F0; }}
            QPushButton:checked {{ background: {BLUE_ACCENT}; color: white; }}
        """)
        self._build_ui()
        self._refresh_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # 头部：日期导航和视图切换
        header = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedSize(32, 32)
        self.prev_btn.clicked.connect(self._prev_period)
        
        self.date_lbl = QLabel()
        self.date_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.date_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; min-width: 130px;")
        
        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedSize(32, 32)
        self.next_btn.clicked.connect(self._next_period)

        self.week_btn = QPushButton("周")
        self.week_btn.setCheckable(True)
        self.week_btn.clicked.connect(lambda: self._set_view("week"))
        
        self.month_btn = QPushButton("月")
        self.month_btn.setCheckable(True)
        self.month_btn.setChecked(True)
        self.month_btn.clicked.connect(lambda: self._set_view("month"))

        header.addWidget(self.prev_btn)
        header.addWidget(self.date_lbl)
        header.addWidget(self.next_btn)
        header.addStretch()
        header.addWidget(self.week_btn)
        header.addWidget(self.month_btn)
        layout.addLayout(header)

        # 主视图网格区
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(0, 10, 0, 10)
        layout.addWidget(self.grid_widget, 1)
        
        # 图例区
        legend = QHBoxLayout()
        operator = self.goal_data.get('operator', '>=')
        legend.addWidget(QLabel("图例:"))
        
        box1 = QFrame(); box1.setFixedSize(14, 14); box1.setStyleSheet(f"background: {GREEN_ACCENT}; border-radius: 3px;")
        legend.addWidget(box1)
        legend.addWidget(QLabel("达标"))
        
        box2 = QFrame(); box2.setFixedSize(14, 14); box2.setStyleSheet("background: #ECEFF4; border-radius: 3px;")
        legend.addWidget(box2)
        legend.addWidget(QLabel("未达标/无"))
        
        if operator == '<=':
            box3 = QFrame(); box3.setFixedSize(14, 14); box3.setStyleSheet(f"background: {RED_ACCENT}; border-radius: 3px;")
            legend.addWidget(box3)
            legend.addWidget(QLabel("超限失败"))
            
        legend.addStretch()
        layout.addLayout(legend)

    def _set_view(self, view):
        self.view_mode = view
        if view == "month":
            self.month_btn.setChecked(True)
            self.week_btn.setChecked(False)
        else:
            self.week_btn.setChecked(True)
            self.month_btn.setChecked(False)
        self.current_date = date.today()
        self._refresh_data()

    def _prev_period(self):
        if self.view_mode == "month":
            first = self.current_date.replace(day=1)
            self.current_date = first - timedelta(days=1)
        else:
            self.current_date -= timedelta(days=7)
        self._refresh_data()

    def _next_period(self):
        if self.view_mode == "month":
            _, last = calendar.monthrange(self.current_date.year, self.current_date.month)
            self.current_date = self.current_date.replace(day=last) + timedelta(days=1)
        else:
            self.current_date += timedelta(days=7)
        self._refresh_data()

    def _refresh_data(self):
        # 清空布局
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        # 计算日期范围
        dates = []
        if self.view_mode == "month":
            self.date_lbl.setText(self.current_date.strftime("%Y年%m月"))
            year, month = self.current_date.year, self.current_date.month
            _, last_day = calendar.monthrange(year, month)
            start_date = date(year, month, 1)
            end_date = date(year, month, last_day)
            
            # 补齐整周（周一为起）
            first_weekday = start_date.weekday()
            current = start_date - timedelta(days=first_weekday)
            while current <= end_date or current.weekday() != 0:
                dates.append(current)
                current += timedelta(days=1)
        else:
            start_date = self.current_date - timedelta(days=self.current_date.weekday())
            end_date = start_date + timedelta(days=6)
            self.date_lbl.setText(f"{start_date.strftime('%m.%d')} - {end_date.strftime('%m.%d')}")
            dates = [start_date + timedelta(days=i) for i in range(7)]

        # 拉取数据
        start_str = dates[0].strftime("%Y-%m-%d")
        end_str = dates[-1].strftime("%Y-%m-%d")
        stats = self.db.get_goal_daily_stats(self.goal_data, start_str, end_str)

        # 绘制表头
        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        for col, wd in enumerate(weekdays):
            lbl = QLabel(wd)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-weight: bold; font-size: 13px; padding-bottom: 5px;")
            self.grid_layout.addWidget(lbl, 0, col)

        target = self.goal_data['target_value']
        operator = self.goal_data.get('operator', '>=')
        metric_suffix = "m" if self.goal_data['metric'] == 'duration' else "次"

        # 绘制格子
        row = 1
        for i, d in enumerate(dates):
            col = d.weekday()
            val = stats.get(d.strftime("%Y-%m-%d"), 0)
            
            frame = QFrame()
            frame.setFixedSize(44, 44)
            
            is_current_month = d.month == self.current_date.month if self.view_mode == "month" else True
            
            bg_color = "#ECEFF4" # 默认底色（未达标或无）
            if not is_current_month:
                bg_color = "transparent"
            elif val > 0 or operator == '<=':
                # 评估进度
                if operator == '>=':
                    if val >= target: bg_color = GREEN_ACCENT
                    elif val > 0: bg_color = "#D8DEE9" # 进度未满，浅灰
                else:
                    if val <= target: bg_color = GREEN_ACCENT
                    else: bg_color = RED_ACCENT # 超限失败
                    
            if not is_current_month and bg_color != "transparent":
                # 非当月但为补齐的天数，降低透明度
                op = QGraphicsOpacityEffect()
                op.setOpacity(0.3)
                frame.setGraphicsEffect(op)

            border_style = ""
            if d == date.today():
                border_style = f"border: 2px solid {BLUE_ACCENT};"
                
            frame.setStyleSheet(f"QFrame {{ background: {bg_color}; border-radius: 6px; {border_style} }}")
            frame.setToolTip(f"{d.strftime('%Y-%m-%d')}\n记录值: {int(val)}{metric_suffix}\n目标: {operator}{int(target)}{metric_suffix}")
            
            flayout = QVBoxLayout(frame)
            flayout.setContentsMargins(0,0,0,0)
            day_lbl = QLabel(str(d.day))
            day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            text_color = '#FFFFFF' if bg_color in [GREEN_ACCENT, RED_ACCENT] else TEXT_PRIMARY
            if not is_current_month and bg_color == "transparent": text_color = "#D8DEE9"
            day_lbl.setStyleSheet(f"color: {text_color}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
            flayout.addWidget(day_lbl)
            
            self.grid_layout.addWidget(frame, row, col)
            if col == 6:
                row += 1

class GoalCard(QFrame):
    """单个目标展示卡片"""
    claimed = pyqtSignal() # 领取成功信号

    def __init__(self, goal_data, db, parent=None):
        super().__init__(parent)
        self.goal_data = goal_data
        self.db = db
        self.setObjectName("goalCard")
        if self.goal_data.get('period') != 'per_session':
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)

        # 头部：标题 + 周期标签
        header = QHBoxLayout()
        title_lbl = QLabel(self.goal_data['title'])
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 15px; font-weight: bold;")
        
        period_map = {'daily': '日目标', 'weekly': '周目标', 'monthly': '月目标', 'per_session': '单次'}
        period_text = period_map.get(self.goal_data['period'], '目标')
        period_lbl = QLabel(period_text)
        period_lbl.setStyleSheet(f"background: rgba(129, 161, 193, 0.15); color: {BLUE_ACCENT}; font-size: 10px; padding: 2px 6px; border-radius: 4px;")
        
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(period_lbl)
        layout.addLayout(header)

        # 进度展示区
        prog_layout = QHBoxLayout()
        self.pbar = QProgressBar()
        self.pbar.setTextVisible(False)
        self.pbar.setFixedHeight(8)
        prog_layout.addWidget(self.pbar)
        
        self.percent_lbl = QLabel("0%")
        self.percent_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; width: 35px;")
        prog_layout.addWidget(self.percent_lbl)
        layout.addLayout(prog_layout)

        # 底部：进度数值 + 奖励/领取按钮
        footer = QHBoxLayout()
        self.progress_info = QLabel("0 / 0")
        self.progress_info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        
        # 奖励显示
        reward_id = self.goal_data.get('reward_id')
        reward_coins = self.goal_data.get('reward_coins', 0)
        
        if reward_id:
            all_rewards = self.db.get_all_rewards()
            reward_item = next((r for r in all_rewards if r['id'] == reward_id), None)
            self.reward_info = QLabel(f"{reward_item['icon'] if reward_item else '🎁'} {reward_item['title'] if reward_item else '奖励'}")
        else:
            reward = reward_coins
            penalty = self.goal_data.get('penalty_coins', reward)
            self.reward_info = QLabel(f"🪙奖: {reward:g} · ❌惩: {penalty:g}")
            self.reward_info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold;")
        
        self.reward_info.setStyleSheet(f"font-size: 12px; font-weight: bold;")
        
        self.action_btn = QPushButton("领取")
        self.action_btn.setFixedSize(65, 26)
        
        self.fail_btn = QPushButton("放弃")
        self.fail_btn.setFixedSize(65, 26)

        footer.addWidget(self.progress_info)
        footer.addStretch()
        footer.addWidget(self.reward_info)
        footer.addSpacing(5)
        footer.addWidget(self.action_btn)
        footer.addWidget(self.fail_btn)
        layout.addLayout(footer)

        self.setStyleSheet(f"""
            #goalCard {{ background: white; border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}
            #goalCard:hover {{ border: 1px solid {BLUE_ACCENT}; }}
        """)
        
        self.update_progress()

    def update_progress(self, active_session_info=None):
        """更新进度UI"""
        progress_val, is_claimed, claim_id = self.db.get_goal_progress(self.goal_data, active_session_info)
        target = self.goal_data['target_value']
        operator = self.goal_data.get('operator', '>=')
        self.current_claim_id = claim_id
        
        # 检查是否达标
        if operator == '>=':
            is_met = progress_val >= target
        else:
            is_met = progress_val <= target
            # 对于 "单次且不超过" 的情况，如果还没结束（active_session），只要没超过就不算失败，但也不算成功
            if active_session_info and not is_met:
                pass # 已经超了
        
        # 格式化显示值
        if self.goal_data['metric'] == 'duration':
            curr_text = f"{int(progress_val)}m"
            target_text = f"{operator}{int(target)}m"
        else:
            curr_text = f"{int(progress_val)}次"
            target_text = f"{operator}{int(target)}次"

        self.progress_info.setText(f"{curr_text} / {target_text}")
        self.pbar.setMaximum(int(target))
        self.pbar.setValue(min(int(progress_val), int(target)))
        
        percent = int(progress_val / target * 100) if target > 0 else 0
        self.percent_lbl.setText(f"{percent}%")
        
        # 进度条颜色：达标绿色，未达标蓝色，对于 <= 且超过了则红色
        chunk_color = BLUE_ACCENT
        if is_met:
            chunk_color = GREEN_ACCENT
        elif operator == '<=' and progress_val > target:
            chunk_color = RED_ACCENT

        self.pbar.setStyleSheet(f"""
            QProgressBar {{ background-color: #ECEFF4; border: none; border-radius: 4px; }}
            QProgressBar::chunk {{ background-color: {chunk_color}; border-radius: 4px; }}
        """)

        # 按钮状态
        try: self.action_btn.clicked.disconnect()
        except: pass
        try: self.fail_btn.clicked.disconnect()
        except: pass

        if is_claimed:
            self.action_btn.setText("已完成")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(f"background: {BORDER_COLOR}; color: #AAB0BC; border-radius: 4px; font-size: 11px;")
            self.fail_btn.hide()
        elif is_met and claim_id:
            self.action_btn.setEnabled(True)
            self.action_btn.setText("领取" if self.goal_data['reward_coins'] >= 0 else "确认")
            self.action_btn.setStyleSheet(f"background: {GREEN_ACCENT}; color: white; border-radius: 4px; font-weight: bold; font-size: 11px;")
            self.action_btn.clicked.connect(lambda: self._on_claim(claim_id))
            self.fail_btn.hide()
        else:
            self.action_btn.setText("未达标" if operator == '>=' else "进行中")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(f"background: #ECEFF4; color: {TEXT_SECONDARY}; border-radius: 4px; font-size: 11px;")
            if operator == '<=' and progress_val > target:
                self.fail_btn.show()
                self.fail_btn.setText("放弃")
                self.fail_btn.setStyleSheet(f"background: {RED_ACCENT}; color: white; border-radius: 4px; font-weight: bold; font-size: 11px;")
                self.fail_btn.clicked.connect(lambda: self._on_fail(claim_id))
            else:
                self.fail_btn.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.goal_data['period'] != 'per_session':
            dialog = GoalStatsDialog(self.goal_data, self.db, self)
            dialog.exec()
        super().mousePressEvent(event)

    def _on_fail(self, claim_id):
        penalty = self.goal_data.get('penalty_coins', self.goal_data['reward_coins'])
        title = self.goal_data['title']
        self.db.add_ledger_entry(-abs(penalty), 'goal_fail', self.goal_data['id'], f"目标挑战失败: {title}")
        from particle_effect import show_failure_effect
        show_failure_effect(self)
        self.claimed.emit()

    def _on_claim(self, claim_id):
        amount = self.goal_data['reward_coins']
        title = self.goal_data['title']
        reward_id = self.goal_data.get('reward_id')
        
        self.db.add_external_reward(claim_id, 'goal', title, amount, status=1)
        
        if reward_id:
            all_rewards = self.db.get_all_rewards()
            reward_item = next((r for r in all_rewards if r['id'] == reward_id), None)
            desc = f"达成目标奖励(兑换项): {reward_item['title'] if reward_item else title}"
            self.db.add_ledger_entry(0, 'goal_reward_item', reward_id, desc)
        else:
            prefix = "达成目标惩罚" if amount < 0 else "达成目标奖励"
            self.db.add_ledger_entry(amount, 'goal_reward', self.goal_data['id'], f"{prefix}: {title}")
        
        from particle_effect import start_coin_explosion, show_success_effect
        if amount > 0:
            start_coin_explosion(self.window(), self.action_btn, 5)
        show_success_effect(self.window())
        
        self.claimed.emit()

    """新增/修改目标对话框"""
    def __init__(self, db, category_manager, initial_data=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.cm = category_manager
        self.initial_data = initial_data
        self.setWindowTitle("修改目标" if initial_data else "新增目标")
        self.setFixedWidth(380)
        self._build_ui()
        if initial_data:
            self._fill_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 标题
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("例如：每日深度阅读")
        self.title_input.setStyleSheet("padding: 8px; border: 1px solid #D8DEE9; border-radius: 4px;")
        layout.addWidget(QLabel("目标名称："))
        layout.addWidget(self.title_input)

        # 关联分类
        self.cat_combo = QComboBox()
        cats = self.cm.get_all_active()
        for c in cats:
            self.cat_combo.addItem(f"{c['icon']} {c['name']}", c['id'])
        layout.addWidget(QLabel("关联时间分类："))
        layout.addWidget(self.cat_combo)

        # 周期与指标
        grid = QGridLayout()
        self.period_combo = QComboBox()
        self.period_combo.addItem("每日", "daily")
        self.period_combo.addItem("每周", "weekly")
        self.period_combo.addItem("每月", "monthly")
        self.period_combo.addItem("每次", "per_session")
        grid.addWidget(QLabel("周期："), 0, 0)
        grid.addWidget(self.period_combo, 0, 1)

        self.operator_combo = QComboBox()
        self.operator_combo.addItem("不少于 (>=)", ">=")
        self.operator_combo.addItem("不超过 (<=)", "<=")
        grid.addWidget(QLabel("条件："), 1, 0)
        grid.addWidget(self.operator_combo, 1, 1)

        self.metric_combo = QComboBox()
        self.metric_combo.addItem("累计时长(分钟)", "duration")
        self.metric_combo.addItem("累计次数", "count")
        grid.addWidget(QLabel("指标："), 2, 0)
        grid.addWidget(self.metric_combo, 2, 1)
        layout.addLayout(grid)

        # 目标数值
        val_row = QHBoxLayout()
        self.val_input = QSpinBox()
        self.val_input.setRange(1, 99999)
        self.val_input.setValue(60)
        self.val_input.setMinimumWidth(120)
        val_row.addWidget(QLabel("目标值："))
        val_row.addWidget(self.val_input)
        val_row.addStretch()
        layout.addLayout(val_row)

        # 奖励设置
        layout.addWidget(QLabel("奖励/惩罚类型："))
        self.reward_type_combo = QComboBox()
        self.reward_type_combo.addItem("金币奖励/惩罚", "coins")
        self.reward_type_combo.addItem("兑换项(奖励商店)", "item")
        layout.addWidget(self.reward_type_combo)

        self.reward_stack = QStackedWidget()
        
        # 页面1：金币
        coin_page = QWidget()
        coin_layout = QHBoxLayout(coin_page)
        coin_layout.setContentsMargins(0, 0, 0, 0)
        self.coin_input = QSpinBox()
        self.coin_input.setRange(-10000, 10000)
        self.coin_input.setValue(1)
        self.coin_input.setMinimumWidth(100)
        coin_layout.addWidget(QLabel("金币奖励："))
        coin_layout.addWidget(self.coin_input)
        
        self.penalty_input = QSpinBox()
        self.penalty_input.setRange(0, 10000)
        self.penalty_input.setValue(1)
        self.penalty_input.setMinimumWidth(100)
        coin_layout.addWidget(QLabel("金币惩罚："))
        coin_layout.addWidget(self.penalty_input)
        coin_layout.addStretch()
        
        # 页面2：兑换项
        item_page = QWidget()
        item_layout = QHBoxLayout(item_page)
        item_layout.setContentsMargins(0, 0, 0, 0)
        self.item_combo = QComboBox()
        rewards = self.db.get_all_rewards()
        for r in rewards:
            self.item_combo.addItem(f"{r['icon']} {r['title']}", r['id'])
        item_layout.addWidget(QLabel("选择奖励："))
        item_layout.addWidget(self.item_combo)
        
        self.reward_stack.addWidget(coin_page)
        self.reward_stack.addWidget(item_page)
        layout.addWidget(self.reward_stack)
        
        self.reward_type_combo.currentIndexChanged.connect(self.reward_stack.setCurrentIndex)

        # 按钮
        btns = QHBoxLayout()
        self.save_btn = QPushButton("保存" if self.initial_data else "创建")
        self.save_btn.setStyleSheet(f"background: {BLUE_ACCENT}; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        self.save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        btns.addWidget(self.save_btn)
        layout.addLayout(btns)

    def _fill_data(self):
        d = self.initial_data
        self.title_input.setText(d.get('title', ''))
        
        # 设置 ComboBox
        idx = self.cat_combo.findData(d.get('category_id'))
        if idx >= 0: self.cat_combo.setCurrentIndex(idx)
        
        idx = self.period_combo.findData(d.get('period'))
        if idx >= 0: self.period_combo.setCurrentIndex(idx)
        
        idx = self.operator_combo.findData(d.get('operator', '>='))
        if idx >= 0: self.operator_combo.setCurrentIndex(idx)
        
        idx = self.metric_combo.findData(d.get('metric'))
        if idx >= 0: self.metric_combo.setCurrentIndex(idx)
        
        self.val_input.setValue(int(d.get('target_value', 60)))
        
        # 奖励设置
        reward_id = d.get('reward_id')
        if reward_id:
            self.reward_type_combo.setCurrentIndex(1)
            idx = self.item_combo.findData(reward_id)
            if idx >= 0: self.item_combo.setCurrentIndex(idx)
        else:
            self.reward_type_combo.setCurrentIndex(0)
            self.coin_input.setValue(int(d.get('reward_coins', 0)))
            self.penalty_input.setValue(int(d.get('penalty_coins', 0)))

    def get_data(self):
        is_coin = self.reward_type_combo.currentData() == "coins"
        return {
            'title': self.title_input.text(),
            'category_id': self.cat_combo.currentData(),
            'metric': self.metric_combo.currentData(),
            'target_value': self.val_input.value(),
            'period': self.period_combo.currentData(),
            'reward_coins': self.coin_input.value() if is_coin else 0,
            'penalty_coins': self.penalty_input.value() if is_coin else 0,
            'reward_id': self.item_combo.currentData() if not is_coin else None,
            'operator': self.operator_combo.currentData()
        }

class GoalsWindow(QWidget):
    """目标面板主窗口"""
    def __init__(self, db, category_manager, logic=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.cm = category_manager
        self.logic = logic
        self.setWindowTitle("目标")
        self.setFixedSize(400, 520)
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dragPos = None
        
        self.cards = []
        self._build_ui()
        self.refresh()
        
        # 实时刷新定时器
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(2000) 
        self.update_timer.timeout.connect(self.update_all_progress)
        self.update_timer.start()

    def _build_ui(self):
        self.bg = QFrame(self)
        self.bg.setObjectName("goalsBg")
        self.bg.setGeometry(0, 0, 400, 520)
        self.bg.setStyleSheet(f"#goalsBg {{ background-color: rgba(255, 255, 255, 0.98); border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}")
        
        layout = QVBoxLayout(self.bg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(48)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)
        
        title_label = QLabel("🎯 <b>目标</b>")
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-family: 'Microsoft YaHei';")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        btn_style = f"QPushButton {{ color: {TEXT_SECONDARY}; background: transparent; font-size: 16px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {BLUE_ACCENT}; }}"
        
        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(30, 30)
        self.add_btn.setStyleSheet(btn_style)
        self.add_btn.clicked.connect(self._on_add_goal)
        
        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedSize(30, 30)
        self.refresh_btn.setStyleSheet(btn_style)
        self.refresh_btn.clicked.connect(self.refresh)
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet(btn_style)
        close_btn.clicked.connect(self.hide)
        
        header_layout.addWidget(self.add_btn)
        header_layout.addWidget(self.refresh_btn)
        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.goal_layout = QVBoxLayout(self.container)
        self.goal_layout.setContentsMargins(15, 10, 15, 10)
        self.goal_layout.setSpacing(12)
        self.goal_layout.addStretch()
        
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.bg)

    def refresh(self):
        while self.goal_layout.count() > 1:
            item = self.goal_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards.clear()

        goals = self.db.get_all_goals()
        for g in goals:
            card = GoalCard(g, self.db)
            card.claimed.connect(self.refresh)
            
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, goal_id=g['id']: self._show_context_menu(pos, goal_id))
            
            self.goal_layout.insertWidget(self.goal_layout.count() - 1, card)
            self.cards.append(card)
        
        self.update_all_progress()

    def update_all_progress(self):
        if not self.isVisible() or not self.logic:
            return
            
        active_info = None
        if self.logic.current_state in ["studying", "countup_studying"] and not self.logic.is_paused:
            elapsed_sec = 0
            if self.logic.current_state == "studying":
                session_elapsed = getattr(self.logic, 'current_session_duration', 0) - (self.logic.timer.remainingTime() // 1000)
                elapsed_sec = session_elapsed 
            else:
                if self.logic.current_session_start_time:
                    elapsed_sec = (datetime.now() - self.logic.current_session_start_time).total_seconds()
            
            active_info = {
                'category_id': self.logic.current_category_id,
                'duration_minutes': elapsed_sec / 60.0
            }

        for card in self.cards:
            card.update_progress(active_info)

    def _on_add_goal(self):
        dialog = GoalAddDialog(self.db, self.cm, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data['title']:
                return
            self.db.add_goal(**data)
            self.refresh()

    def _show_context_menu(self, pos, goal_id):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        edit_action = menu.addAction("✏️ 修改目标")
        del_action = menu.addAction("🗑️ 删除目标")
        action = menu.exec(self.mapToGlobal(self.mapFromGlobal(self.cursor().pos()))) 
        if action == del_action:
            if QMessageBox.question(self, "确认删除", "确定要删除这个目标吗？") == QMessageBox.StandardButton.Yes:
                self.db.remove_goal(goal_id)
                self.refresh()
        elif action == edit_action:
            self._on_edit_goal(goal_id)

    def _on_edit_goal(self, goal_id):
        # 获取目标详情
        goals = self.db.get_all_goals()
        goal_data = next((g for g in goals if g['id'] == goal_id), None)
        if not goal_data: return
        
        dialog = GoalAddDialog(self.db, self.cm, initial_data=goal_data, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data['title']: return
            self.db.update_goal(goal_id, **data)
            self.refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)

    def mouseReleaseEvent(self, event):
        self.dragPos = None
