# -*- coding: utf-8 -*-
"""
奖励商店模块 (reward_shop.py)
================================
独立浮动窗口，支持新增/购买/删除奖励，显示余额和积分流水。
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QFrame, QDialog, QLineEdit,
    QFormLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFont

from database import StudyLogger

logger = logging.getLogger(__name__)

TEXT_PRIMARY = "#2E3440"
TEXT_SECONDARY = "#4C566A"
BORDER_COLOR = "#D8DEE9"
GREEN_ACCENT = "#A3BE8C"
GREEN_HOVER = "#8FBF65"
GOLD_ACCENT = "#EBCB8B"
GOLD_HOVER = "#D9B44A"
RED_ACCENT = "#BF616A"
BG_LIGHT = "#FFFFFF"
COIN_ICON = "🪙"


class RewardAddDialog(QDialog):
    """新增奖励弹窗"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_icon = '🎁'
        self.setWindowTitle("新增奖励")
        self.setFixedSize(340, 260)
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_LIGHT}; font-family: 'Microsoft YaHei'; }}
            QLineEdit {{ border: 1px solid {BORDER_COLOR}; border-radius: 6px; padding: 6px 10px; background: #F8F9FB; font-size: 13px; }}
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
        self.name_input.setPlaceholderText("例如：看一集番剧")

        icon_row = QHBoxLayout()
        self.icon_btn = QPushButton(self.selected_icon)
        self.icon_btn.setFixedSize(40, 40)
        self.icon_btn.setStyleSheet(f"""
            QPushButton {{ font-size: 22px; background: #F0F2F5; border: 1px solid {BORDER_COLOR}; border-radius: 8px; }}
            QPushButton:hover {{ background: #E0E8F0; border-color: {GOLD_ACCENT}; }}
        """)
        self.icon_btn.clicked.connect(self._pick_icon)
        icon_row.addWidget(self.icon_btn)
        icon_row.addStretch()

        self.price_input = QLineEdit("10")
        self.price_input.setPlaceholderText("价格")

        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("描述（选填）")
        
        from PyQt6.QtWidgets import QComboBox
        self.task_combo = QComboBox()
        self.task_combo.addItem("无（普通金币商品）", None)
        try:
            from database import StudyLogger
            db = StudyLogger({})
            tasks = db.get_all_active_tasks()
            for t in tasks:
                self.task_combo.addItem(t.get('title', '未知任务'), t.get('id'))
        except Exception:
            pass

        form.addRow("名称:", self.name_input)
        form.addRow("图标:", icon_row)
        form.addRow(f"价格({COIN_ICON}):", self.price_input)
        form.addRow("描述:", self.desc_input)
        form.addRow("解锁任务:", self.task_combo)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(f"QPushButton {{ background: #E5E9F0; border: none; border-radius: 6px; padding: 8px 20px; color: {TEXT_SECONDARY}; font-weight: bold; }} QPushButton:hover {{ background: #D8DEE9; }}")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(f"QPushButton {{ background: {GOLD_ACCENT}; border: none; border-radius: 6px; padding: 8px 20px; color: white; font-weight: bold; }} QPushButton:hover {{ background: {GOLD_HOVER}; }}")
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
            QMessageBox.warning(self, "提示", "请输入奖励名称")
            return
        
        task_id = self.task_combo.currentData()
        if not task_id:
            try:
                float(self.price_input.text().strip())
            except ValueError:
                QMessageBox.warning(self, "提示", "非任务解锁型商品，价格必须是有效数字")
                return
                
        self.accept()

    def get_data(self):
        task_id = self.task_combo.currentData()
        task_title = self.task_combo.currentText() if task_id else None
        
        price_val = 0.0
        if not task_id:
            try: price_val = float(self.price_input.text().strip())
            except: pass
            
        return {
            'title': self.name_input.text().strip(),
            'icon': self.selected_icon,
            'price': price_val,
            'description': self.desc_input.text().strip(),
            'unlock_task_id': task_id,
            'unlock_task_title': task_title
        }


class RewardCard(QFrame):
    """单个奖励卡片"""
    def __init__(self, reward_data, parent=None):
        super().__init__(parent)
        self.reward_data = reward_data
        self.setObjectName("rewardCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        icon_lbl = QLabel(self.reward_data.get('icon', '🎁'))
        icon_lbl.setFixedSize(36, 36)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("font-size: 22px; background: transparent; border: none;")
        layout.addWidget(icon_lbl)

        info = QVBoxLayout()
        info.setSpacing(2)
        title = QLabel(self.reward_data.get('title', '未命名'))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold; font-family: 'Microsoft YaHei';")
        desc = self.reward_data.get('description', '')
        desc_lbl = QLabel(desc if desc else "暂无描述")
        desc_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        info.addWidget(title)
        info.addWidget(desc_lbl)
        layout.addLayout(info, 1)

        unlock_task_id = self.reward_data.get('unlock_task_id')
        unlock_task_title = self.reward_data.get('unlock_task_title')

        if unlock_task_id:
            from database import StudyLogger
            db = StudyLogger({})
            is_completed = db.is_task_completed(unlock_task_id)
            
            price_lbl = QLabel("任务专属")
            price_lbl.setStyleSheet(f"color: {GREEN_HOVER}; font-size: 11px; font-weight: bold; background: rgba(163, 190, 140, 0.15); border-radius: 4px; padding: 2px 6px;")
            
            self.buy_btn = QPushButton("解锁")
            self.buy_btn.setFixedSize(52, 28)
            if is_completed:
                self.buy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                self.buy_btn.setStyleSheet(f"""
                    QPushButton {{ background: {GREEN_ACCENT}; color: white; border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }}
                    QPushButton:hover {{ background: {GREEN_HOVER}; }}
                """)
            else:
                self.buy_btn.setCursor(Qt.CursorShape.ForbiddenCursor)
                self.buy_btn.setEnabled(False)
                self.buy_btn.setStyleSheet(f"""
                    QPushButton {{ background: #CBD2D9; color: white; border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }}
                """)
        else:
            price = self.reward_data.get('price', 0)
            price_lbl = QLabel(f"{price}{COIN_ICON}")
            price_lbl.setStyleSheet(f"color: {GOLD_HOVER}; font-size: 14px; font-weight: bold;")
            
            self.buy_btn = QPushButton("兑换")
            self.buy_btn.setFixedSize(52, 28)
            self.buy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.buy_btn.setStyleSheet(f"""
                QPushButton {{ background: {GOLD_ACCENT}; color: white; border: none; border-radius: 6px; font-size: 12px; font-weight: bold; }}
                QPushButton:hover {{ background: {GOLD_HOVER}; }}
            """)
        
        layout.addWidget(price_lbl)
        layout.addWidget(self.buy_btn)

        self.setStyleSheet(f"""
            #rewardCard {{ background: white; border: 1px solid {BORDER_COLOR}; border-radius: 10px; }}
            #rewardCard:hover {{ background: rgba(235, 203, 139, 0.06); }}
        """)


class RewardShopWindow(QWidget):
    """奖励商店浮动窗口"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.db = StudyLogger(config)
        self.settings = QSettings("MyTimeLogger", "RewardShop")

        self.setWindowTitle("奖励商店")
        self.setFixedSize(420, 560)
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
        self.bg.setObjectName("shopBg")
        self.bg.setGeometry(0, 0, 420, 560)
        self.bg.setStyleSheet(f"""
            #shopBg {{
                background-color: rgba(255, 255, 255, 0.98);
                border: 1px solid {BORDER_COLOR};
                border-radius: 12px;
            }}
        """)
        layout = QVBoxLayout(self.bg)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题栏
        header = QWidget()
        header.setFixedHeight(48)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 12, 0)

        title_label = QLabel("🏪 <b>奖励商店</b>")
        title_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-family: 'Microsoft YaHei';")
        header_layout.addWidget(title_label)
        header_layout.addStretch()

        add_btn = QPushButton("＋")
        add_btn.setFixedSize(30, 30)
        add_btn.setStyleSheet(f"QPushButton {{ color: {GOLD_ACCENT}; background: transparent; font-size: 20px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {GOLD_HOVER}; }}")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_reward)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setStyleSheet(f"QPushButton {{ color: {TEXT_SECONDARY}; background: transparent; font-size: 16px; border: none; font-weight: bold; }} QPushButton:hover {{ color: {GOLD_ACCENT}; }}")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)

        header_layout.addWidget(add_btn)
        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        # 余额区
        self.balance_label = QLabel(f"💰 0 {COIN_ICON}")
        self.balance_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.balance_label.setFixedHeight(50)
        self.balance_label.setStyleSheet(f"""
            color: {GOLD_HOVER}; font-size: 26px; font-weight: bold;
            background: rgba(235, 203, 139, 0.08);
            border-top: 1px solid #F0F2F5; border-bottom: 1px solid #F0F2F5;
            font-family: 'Microsoft YaHei';
        """)
        layout.addWidget(self.balance_label)

        # 奖励列表
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.reward_layout = QVBoxLayout(self.container)
        self.reward_layout.setContentsMargins(15, 10, 15, 10)
        self.reward_layout.setSpacing(8)
        self.reward_layout.addStretch()

        self.empty_label = QLabel("还没有奖励哦\n点击 ＋ 添加一个吧 🎁")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px; padding: 30px;")
        self.reward_layout.insertWidget(0, self.empty_label)

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

        # 分割线 + 流水标题
        history_header = QLabel("  📜 最近流水")
        history_header.setFixedHeight(24)
        history_header.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: bold; background: #F8F9FB; border-top: 1px solid #F0F2F5;")
        layout.addWidget(history_header)

        # 流水区域
        self.history_widget = QWidget()
        self.history_widget.setFixedHeight(110)
        self.history_layout = QVBoxLayout(self.history_widget)
        self.history_layout.setContentsMargins(16, 4, 16, 4)
        self.history_layout.setSpacing(2)
        layout.addWidget(self.history_widget)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.bg)

    def _refresh(self):
        # 更新余额
        balance = self.db.get_balance()
        self.balance_label.setText(f"💰 {balance} {COIN_ICON}")

        # 清理旧奖励卡片
        while self.reward_layout.count() > 1:
            item = self.reward_layout.takeAt(0)
            if item.widget() and item.widget() != self.empty_label:
                item.widget().deleteLater()

        rewards = self.db.get_all_rewards()
        if not rewards:
            self.empty_label.show()
        else:
            self.empty_label.hide()

        for reward in rewards:
            card = RewardCard(reward)
            card.buy_btn.clicked.connect(lambda _, r=reward: self._on_buy(r))
            card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            card.customContextMenuRequested.connect(lambda pos, r=reward, c=card: self._show_context_menu(r, pos, c))
            self.reward_layout.insertWidget(self.reward_layout.count() - 1, card)

        # 更新流水
        while self.history_layout.count():
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        history = self.db.get_ledger_history(5)
        if not history:
            empty = QLabel("暂无记录")
            empty.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
            self.history_layout.addWidget(empty)
        else:
            for entry in history:
                amt = entry['amount']
                amt_disp = f"{round(amt, 2):g}"
                sign = '+' if amt > 0 else ''
                color = GREEN_ACCENT if amt > 0 else RED_ACCENT
                desc = entry.get('description', '')
                time_str = ''
                try:
                    dt = datetime.strptime(entry['created_at'], '%Y-%m-%d %H:%M:%S')
                    time_str = dt.strftime('%H:%M')
                except Exception:
                    pass
                row = QLabel(f"<span style='color:{color}; font-weight:bold;'>{sign}{amt_disp}{COIN_ICON}</span> &nbsp; {desc} &nbsp; <span style='color:#999;'>{time_str}</span>")
                row.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
                row.setTextFormat(Qt.TextFormat.RichText)
                self.history_layout.addWidget(row)

    def _on_buy(self, reward):
        is_task_unlock = bool(reward.get('unlock_task_id'))
        if is_task_unlock:
            msg_text = f"确定要解锁「{reward['title']}」吗？\n（需要已完成任务：{reward.get('unlock_task_title', '指定任务')}）"
        else:
            msg_text = f"确定要花费 {reward['price']}{COIN_ICON} 兑换「{reward['title']}」吗？"
            
        reply = QMessageBox.question(
            self, "确认兑换", msg_text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok, msg = self.db.buy_reward(reward['id'])
            if ok:
                QMessageBox.information(self, "🎉 兑换成功", msg)
            else:
                QMessageBox.warning(self, "兑换失败", msg)
            self._refresh()

    def _on_add_reward(self):
        dialog = RewardAddDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.db.add_reward(
                title=data['title'],
                icon=data['icon'],
                price=data['price'],
                description=data['description'],
                unlock_task_id=data.get('unlock_task_id'),
                unlock_task_title=data.get('unlock_task_title')
            )
            self._refresh()

    def _show_context_menu(self, reward, pos, card):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QAction

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background-color: white; border: 1px solid {BORDER_COLOR}; border-radius: 6px; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px; color: {TEXT_PRIMARY}; font-size: 13px; }}
            QMenu::item:selected {{ background-color: rgba(235, 203, 139, 0.1); color: {GOLD_HOVER}; border-radius: 4px; }}
        """)

        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(lambda: self._on_delete_reward(reward))
        menu.addAction(delete_action)
        menu.exec(card.mapToGlobal(pos))

    def _on_delete_reward(self, reward):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除奖励「{reward['title']}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.remove_reward(reward['id'])
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
