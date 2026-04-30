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
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QScrollArea, QFrame, QDialog, QComboBox, 
    QLineEdit, QSpinBox, QDoubleSpinBox, QMessageBox, QGridLayout, QStackedWidget
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

class GoalCard(QFrame):
    """单个目标展示卡片"""
    claimed = pyqtSignal() # 领取成功信号

    def __init__(self, goal_data, db, parent=None):
        super().__init__(parent)
        self.goal_data = goal_data
        self.db = db
        self.setObjectName("goalCard")
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
            color = RED_ACCENT if reward_coins < 0 else GOLD_ACCENT
            prefix = "惩罚:" if reward_coins < 0 else "奖励:"
            self.reward_info = QLabel(f"{prefix} {COIN_ICON} {abs(reward_coins)}")
            self.reward_info.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
        
        self.reward_info.setStyleSheet(f"font-size: 12px; font-weight: bold;")
        
        self.action_btn = QPushButton("领取")
        self.action_btn.setFixedSize(65, 26)

        footer.addWidget(self.progress_info)
        footer.addStretch()
        footer.addWidget(self.reward_info)
        footer.addSpacing(5)
        footer.addWidget(self.action_btn)
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

        if is_claimed:
            self.action_btn.setText("已完成")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(f"background: {BORDER_COLOR}; color: #AAB0BC; border-radius: 4px; font-size: 11px;")
        elif is_met and claim_id:
            # 只有在入库了（有claim_id）且达标时才能领取
            self.action_btn.setEnabled(True)
            self.action_btn.setText("领取" if self.goal_data['reward_coins'] >= 0 else "确认")
            self.action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.action_btn.setStyleSheet(f"background: {GREEN_ACCENT}; color: white; border-radius: 4px; font-weight: bold; font-size: 11px;")
            self.action_btn.clicked.connect(lambda: self._on_claim(claim_id))
        else:
            self.action_btn.setText("未达标" if operator == '>=' else "进行中")
            if operator == '<=' and progress_val > target:
                self.action_btn.setText("失败")
            self.action_btn.setEnabled(False)
            self.action_btn.setStyleSheet(f"background: #ECEFF4; color: {TEXT_SECONDARY}; border-radius: 4px; font-size: 11px;")

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
            msg = f"恭喜达成目标！\n获得奖励: {reward_item['icon'] if reward_item else ''} {reward_item['title'] if reward_item else title}"
        else:
            prefix = "达成目标惩罚" if amount < 0 else "达成目标奖励"
            self.db.add_ledger_entry(amount, 'goal_reward', self.goal_data['id'], f"{prefix}: {title}")
            msg = f"目标已确认！\n{'获得' if amount >=0 else '扣除'}奖励: {abs(amount)} {COIN_ICON}"
        
        QMessageBox.information(self, "🎉 操作成功", msg)
        self.claimed.emit()

class GoalAddDialog(QDialog):
    """新增目标对话框"""
    def __init__(self, db, category_manager, parent=None):
        super().__init__(parent)
        self.db = db
        self.cm = category_manager
        self.setWindowTitle("新增目标")
        self.setFixedWidth(380)
        self._build_ui()

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
        self.coin_input.setMinimumWidth(120)
        coin_layout.addWidget(QLabel("金币数量："))
        coin_layout.addWidget(self.coin_input)
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
        save_btn = QPushButton("创建")
        save_btn.setStyleSheet(f"background: {BLUE_ACCENT}; color: white; padding: 8px; border-radius: 4px; font-weight: bold;")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        btns.addWidget(save_btn)
        layout.addLayout(btns)

    def get_data(self):
        is_coin = self.reward_type_combo.currentData() == "coins"
        return {
            'title': self.title_input.text(),
            'category_id': self.cat_combo.currentData(),
            'metric': self.metric_combo.currentData(),
            'target_value': self.val_input.value(),
            'period': self.period_combo.currentData(),
            'reward_coins': self.coin_input.value() if is_coin else 0,
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
        del_action = menu.addAction("🗑️ 删除目标")
        action = menu.exec(self.mapToGlobal(self.mapFromGlobal(self.cursor().pos()))) 
        if action == del_action:
            if QMessageBox.question(self, "确认删除", "确定要删除这个目标吗？") == QMessageBox.StandardButton.Yes:
                self.db.remove_goal(goal_id)
                self.refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)

    def mouseReleaseEvent(self, event):
        self.dragPos = None
