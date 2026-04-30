# -*- coding: utf-8 -*-
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QProgressBar, QScrollArea, QFrame,
                             QDialog, QFormLayout, QLineEdit, QComboBox, 
                             QMessageBox, QSpinBox, QDoubleSpinBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QFont
from datetime import datetime

# 样式常量
TEXT_PRIMARY = "#2E3440"
TEXT_SECONDARY = "#4C566A"
BORDER_COLOR = "#D8DEE9"
GOLD_ACCENT = "#EBCB8B"
GOLD_HOVER = "#D9B44A"
GREEN_ACCENT = "#A3BE8C"
GREEN_HOVER = "#8FBF65"
SAPPHIRE_BLUE = "#5E81AC"
BG_LIGHT = "#FFFFFF"

class GoalAddDialog(QDialog):
    """添加目标对话框"""
    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.setWindowTitle("创建新目标 🎯")
        self.setFixedSize(340, 280)
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_LIGHT}; font-family: 'Microsoft YaHei'; }}
            QLineEdit, QComboBox, QDoubleSpinBox {{ border: 1px solid {BORDER_COLOR}; border-radius: 6px; padding: 6px 10px; background: #F8F9FB; font-size: 13px; }}
            QLabel {{ color: {TEXT_PRIMARY}; font-size: 13px; }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("例如：每日深度学习")
        
        self.cat_combo = QComboBox()
        for cid, name in self.categories:
            self.cat_combo.addItem(name, cid)

        self.metric_combo = QComboBox()
        self.metric_combo.addItem("累计时长 (分钟)", "duration")
        self.metric_combo.addItem("累计次数 (次)", "count")

        self.period_combo = QComboBox()
        self.period_combo.addItem("每日", "daily")
        self.period_combo.addItem("每周", "weekly")
        self.period_combo.addItem("每月", "monthly")

        self.target_input = QDoubleSpinBox()
        self.target_input.setRange(0.1, 99999)
        self.target_input.setValue(60)

        self.reward_input = QDoubleSpinBox()
        self.reward_input.setRange(0, 1000)
        self.reward_input.setValue(1.0)

        form.addRow("目标名称:", self.title_input)
        form.addRow("时间分类:", self.cat_combo)
        form.addRow("考核指标:", self.metric_combo)
        form.addRow("考核周期:", self.period_combo)
        form.addRow("目标数值:", self.target_input)
        form.addRow("奖励金币:", self.reward_input)
        layout.addLayout(form)

        btns = QHBoxLayout()
        cancel = QPushButton("取消")
        cancel.setFixedSize(80, 30)
        cancel.clicked.connect(self.reject)
        
        save = QPushButton("保存")
        save.setFixedSize(80, 30)
        save.setStyleSheet(f"background: {SAPPHIRE_BLUE}; color: white; font-weight: bold; border: none; border-radius: 6px;")
        save.clicked.connect(self.accept)
        
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

    def get_data(self):
        return {
            'title': self.title_input.text().strip(),
            'category_id': self.cat_combo.currentData(),
            'metric': self.metric_combo.currentData(),
            'period': self.period_combo.currentData(),
            'target_value': self.target_input.value(),
            'reward_coins': self.reward_input.value()
        }

class GoalCard(QFrame):
    """单个目标进度卡片"""
    claim_clicked = pyqtSignal(dict)
    delete_clicked = pyqtSignal(int)

    def __init__(self, goal_data, progress, is_claimed, claim_id, parent=None):
        super().__init__(parent)
        self.goal_data = goal_data
        self.progress = progress
        self.is_claimed = is_claimed
        self.claim_id = claim_id
        self._build_ui()

    def _build_ui(self):
        self.setObjectName("goalCard")
        self.setStyleSheet(f"""
            #goalCard {{ 
                background: white; border: 1px solid {BORDER_COLOR}; border-radius: 10px; 
            }}
            #goalCard:hover {{ background: rgba(94, 129, 172, 0.03); border: 1px solid {SAPPHIRE_BLUE}; }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)

        # 标题行
        header = QHBoxLayout()
        title_lbl = QLabel(f"<b>{self.goal_data['title']}</b>")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 13px;")
        
        period_map = {'daily': '日', 'weekly': '周', 'monthly': '月'}
        period_lbl = QLabel(period_map.get(self.goal_data['period'], ''))
        period_lbl.setStyleSheet("color: white; background: #81A1C1; border-radius: 4px; padding: 1px 5px; font-size: 9px; font-weight: bold;")
        
        header.addWidget(title_lbl)
        header.addWidget(period_lbl)
        header.addStretch()
        
        del_btn = QPushButton("×")
        del_btn.setFixedSize(18, 18)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.setStyleSheet("QPushButton { color: #BF616A; border: none; font-size: 14px; } QPushButton:hover { font-weight: bold; }")
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.goal_data['id']))
        header.addWidget(del_btn)
        layout.addLayout(header)

        # 进度条
        target = self.goal_data['target_value']
        percent = min(100, int(self.progress / target * 100)) if target > 0 else 0
        
        pbar = QProgressBar()
        pbar.setFixedHeight(6)
        pbar.setRange(0, 100)
        pbar.setValue(percent)
        pbar.setTextVisible(False)
        pbar.setStyleSheet(f"""
            QProgressBar {{ background: #ECEFF4; border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background: {GREEN_ACCENT if percent >= 100 else SAPPHIRE_BLUE}; border-radius: 3px; }}
        """)
        layout.addWidget(pbar)

        # 底部信息
        footer = QHBoxLayout()
        unit = "分钟" if self.goal_data['metric'] == 'duration' else "次"
        prog_lbl = QLabel(f"{self.progress:g} / {target:g} {unit}")
        prog_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        
        reward_lbl = QLabel(f"{self.goal_data['reward_coins']:g} 🪙")
        reward_lbl.setStyleSheet(f"color: {GOLD_HOVER}; font-size: 12px; font-weight: bold;")
        
        footer.addWidget(prog_lbl)
        footer.addStretch()
        footer.addWidget(reward_lbl)
        
        self.btn = QPushButton("领 取" if percent >= 100 and not self.is_claimed else ("已领取" if self.is_claimed else "进行中"))
        self.btn.setFixedSize(54, 24)
        self.btn.setEnabled(percent >= 100 and not self.is_claimed)
        if self.is_claimed:
            self.btn.setStyleSheet("background: #D8DEE9; color: #4C566A; border: none; border-radius: 4px; font-size: 10px;")
        elif percent >= 100:
            self.btn.setStyleSheet(f"background: {GREEN_ACCENT}; color: white; border: none; border-radius: 4px; font-size: 10px; font-weight: bold;")
        else:
            self.btn.setStyleSheet(f"background: #F0F2F5; color: {SAPPHIRE_BLUE}; border: none; border-radius: 4px; font-size: 10px;")
        
        self.btn.clicked.connect(lambda: self.claim_clicked.emit({'goal': self.goal_data, 'claim_id': self.claim_id}))
        footer.addWidget(self.btn)
        
        layout.addLayout(footer)

class GoalsWindow(QWidget):
    """目标挑战独立窗口"""
    def __init__(self, db, category_manager, parent=None):
        super().__init__(parent)
        self.db = db
        self.category_manager = category_manager
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 520)
        self.dragPos = None
        
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # 外层阴影/圆角容器
        self.bg = QFrame(self)
        self.bg.setObjectName("mainBg")
        self.bg.setStyleSheet(f"""
            #mainBg {{ background: white; border: 1px solid {BORDER_COLOR}; border-radius: 12px; }}
        """)
        layout = QVBoxLayout(self.bg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 自定义标题栏
        title_bar = QFrame()
        title_bar.setFixedHeight(45)
        title_bar.setStyleSheet(f"background: {BG_LIGHT}; border-bottom: 1px solid #F0F2F5; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(15, 0, 10, 0)
        
        title_lbl = QLabel("🎯 <b>挑战目标</b>")
        title_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 15px;")
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()
        
        add_btn = QPushButton("＋")
        add_btn.setFixedSize(28, 28)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setStyleSheet(f"QPushButton {{ color: {SAPPHIRE_BLUE}; border: none; font-size: 20px; font-weight: bold; }} QPushButton:hover {{ background: #F0F2F5; border-radius: 4px; }}")
        add_btn.clicked.connect(self._on_add_goal)
        title_layout.addWidget(add_btn)
        
        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("QPushButton { color: #BF616A; border: none; font-size: 20px; } QPushButton:hover { background: #FEE; border-radius: 4px; }")
        close_btn.clicked.connect(self.hide)
        title_layout.addWidget(close_btn)
        
        layout.addWidget(title_bar)

        # 滚动区域
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(15, 12, 15, 12)
        self.list_layout.setSpacing(10)
        self.list_layout.addStretch()
        
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(0, 0, 0, 0)
        main_vbox.addWidget(self.bg)

    def refresh(self):
        """刷新列表"""
        while self.list_layout.count() > 1:
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        goals = self.db.get_all_goals()
        if not goals:
            empty = QLabel("目前没有目标挑战\n点击右上角 ＋ 开始吧 🏁")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 13px; padding: 60px;")
            self.list_layout.insertWidget(0, empty)
        else:
            for goal in goals:
                progress, is_claimed, claim_id = self.db.get_goal_progress(goal)
                card = GoalCard(goal, progress, is_claimed, claim_id)
                card.claim_clicked.connect(self._on_claim)
                card.delete_clicked.connect(self._on_delete)
                self.list_layout.insertWidget(self.list_layout.count() - 1, card)

    def _on_add_goal(self):
        cats = self.category_manager.get_categories() if self.category_manager else []
        cat_list = [(c['id'], c['name']) for c in cats]
        
        dialog = GoalAddDialog(cat_list, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            if not data['title']: return
            if self.db.add_goal(**data):
                self.refresh()

    def _on_delete(self, goal_id):
        if QMessageBox.question(self, "确认", "确定要删除此目标吗？", 
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            if self.db.remove_goal(goal_id):
                self.refresh()

    def _on_claim(self, data):
        goal = data['goal']
        claim_id = data['claim_id']
        desc = f"目标达成奖励: {goal['title']}"
        if self.db.add_ledger_entry(goal['reward_coins'], 'goal_reward', goal['id'], desc):
            self.db.add_external_reward(claim_id, 'goal', goal['title'], goal['reward_coins'], status=1)
            QMessageBox.information(self, "恭喜", f"已领取奖励 {goal['reward_coins']} 🪙！")
            self.refresh()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)
