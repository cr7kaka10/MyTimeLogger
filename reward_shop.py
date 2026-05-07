# -*- coding: utf-8 -*-
"""
奖励商店模块 (reward_shop.py)
================================
独立浮动窗口，支持新增/购买/删除奖励，显示余额和积分流水。
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QPushButton, QLabel, QFrame, QMessageBox, QDialog,
                             QScrollArea, QLineEdit, QComboBox, QSpinBox,
                             QListWidget, QListWidgetItem, QFormLayout)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QSettings
from PyQt6.QtGui import QIcon, QFont, QFontMetrics
from datetime import datetime, timedelta
import re

def format_ledger_desc(desc):
    # 移除统一的“领取奖励: ”前缀
    if desc.startswith("领取奖励: "):
        desc = desc[6:]
    
    # 目标
    if "目标达成" in desc or "达成目标奖励" in desc:
        # 提取目标标题。格式：目标达成[2026-05-05]: 娱乐≤60min (0m / <=60m)
        name = desc
        if "]: " in desc:
            name = desc.split("]: ")[1]
        if " (" in name:
            name = name.split(" (")[0]
        return f"【目标】{name} 完成"
    
    if "目标未达标" in desc or "目标挑战失败" in desc or "达成目标惩罚" in desc:
        name = desc
        if "]: " in desc:
            name = desc.split("]: ")[1]
        if " (" in name:
            name = name.split(" (")[0]
        return f"【目标】{name} 失败"

    # 习惯
    if desc.startswith("习惯打卡:") or desc.startswith("习惯打卡完成:"):
        name = desc.split(":")[-1].strip()
        if " (" in name: name = name.split(" (")[0]
        return f"【习惯】{name} 完成"
    
    if desc.startswith("习惯判定失败"):
        name = desc.split(":")[-1].strip()
        return f"【习惯】{name} 失败"

    # 清单/外部
    if desc.startswith("领取外部奖励:"):
        content = desc[8:]
        status = "失败" if ("未达标" in content or "失败" in content) else "完成"
        return f"【清单】{content} {status}"
    
    # 兜底：如果是习惯打卡产生的（通过 re 匹配）
    m = re.match(r'^习惯打卡:\s*(.+?)\s*(\(🔥\d+\))?$', desc)
    if m:
        return f"【习惯】{m.group(1)} 完成".strip()
        
    # 如果没有标签，根据关键词尝试补全
    if "打卡" in desc or "习惯" in desc:
        return f"【习惯】{desc} 完成"
    if "清单" in desc or "任务" in desc:
        return f"【清单】{desc} 完成"
    if "目标" in desc:
        return f"【目标】{desc} 完成"

    # 特殊处理：如果没有前缀但来自 external_claim，通常是习惯或清单
    # 鉴于用户截图，很多直接是名称，我们加个【习惯】兜底或者保持原样
    # 这里我们假设大部分外部同步过来的都是习惯
    return f"【习惯】{desc} 完成" if not desc.startswith("【") else desc

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
BLUE_ACCENT = "#5E81AC"
BG_LIGHT = "#FFFFFF"
COIN_ICON = "🪙"


class RewardAddDialog(QDialog):
    """新增/修改奖励弹窗"""
    def __init__(self, parent=None, reward_data=None):
        super().__init__(parent)
        self.reward_data = reward_data
        self.selected_icon = reward_data.get('icon', '🎁') if reward_data else '🎁'
        self.setWindowTitle("修改奖励" if reward_data else "新增奖励")
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
            # 1. 加载任务
            tasks = db.get_all_active_tasks()
            for t in tasks:
                self.task_combo.addItem(f"📋 {t.get('title', '未知任务')}", t.get('id'))
                
            # 2. 加载目标
            goals = db.get_all_goals()
            for g in goals:
                self.task_combo.addItem(f"🎯 {g.get('title', '未知目标')}", f"goal_{g.get('id')}")
        except Exception:
            pass

        if self.reward_data:
            self.name_input.setText(self.reward_data.get('title', ''))
            price = self.reward_data.get('price', 10)
            self.price_input.setText(str(price) if price else '0')
            self.desc_input.setText(self.reward_data.get('description', ''))
            
            unlock_id = self.reward_data.get('unlock_task_id')
            if unlock_id:
                idx = self.task_combo.findData(unlock_id)
                if idx >= 0:
                    self.task_combo.setCurrentIndex(idx)

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
            available_count = db.get_available_unlocks(unlock_task_id, self.reward_data.get('id'))
            is_completed = available_count > 0
            
            label_text = "🎯 目标达成" if is_completed else ("🎯 目标专属" if unlock_task_id.startswith("goal_") else "📋 任务专属")
            price_lbl = QLabel(label_text)
            price_lbl.setStyleSheet(f"color: {'white' if is_completed else TEXT_SECONDARY}; font-size: 11px; font-weight: bold; background: {GREEN_ACCENT if is_completed else '#E5E9F0'}; border-radius: 4px; padding: 2px 6px;")
            if not is_completed and unlock_task_title:
                price_lbl.setToolTip(f"需先完成: {unlock_task_title}")
            
            btn_text = f"领取({available_count})" if is_completed else "未达成"
            self.buy_btn = QPushButton(btn_text)
            self.buy_btn.setFixedSize(62, 28)
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
        history_header_layout = QHBoxLayout()
        history_header_layout.setContentsMargins(16, 0, 16, 0)
        
        history_header = QLabel("📜 最近流水")
        history_header.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px; font-weight: bold;")
        
        view_all_btn = QPushButton("查看完整流水 ›")
        view_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all_btn.setStyleSheet(f"color: {BLUE_ACCENT}; font-size: 11px; background: transparent; border: none;")
        view_all_btn.clicked.connect(self._show_full_ledger)
        
        history_header_layout.addWidget(history_header)
        history_header_layout.addStretch()
        history_header_layout.addWidget(view_all_btn)
        
        header_widget = QWidget()
        header_widget.setStyleSheet("background: #F8F9FB; border-top: 1px solid #F0F2F5;")
        header_widget.setLayout(history_header_layout)
        header_widget.setFixedHeight(26)
        layout.addWidget(header_widget)

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
                color = RED_ACCENT if amt > 0 else GREEN_ACCENT
                desc = format_ledger_desc(entry.get('description', ''))
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

        edit_action = QAction("✏️ 修改", self)
        edit_action.triggered.connect(lambda: self._on_edit_reward(reward))
        menu.addAction(edit_action)

        delete_action = QAction("🗑️ 删除", self)
        delete_action.triggered.connect(lambda: self._on_delete_reward(reward))
        menu.addAction(delete_action)
        menu.exec(card.mapToGlobal(pos))

    def _on_edit_reward(self, reward):
        dialog = RewardAddDialog(self, reward_data=reward)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            self.db.update_reward(
                reward_id=reward['id'],
                title=data['title'],
                icon=data['icon'],
                price=data['price'],
                description=data['description'],
                unlock_task_id=data.get('unlock_task_id'),
                unlock_task_title=data.get('unlock_task_title')
            )
            self._refresh()

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

    def _show_full_ledger(self):
        dialog = FullLedgerDialog(self.db, self)
        dialog.exec()

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

class TimelineHeaderWidget(QWidget):
    def __init__(self, date_str):
        super().__init__()
        self.setFixedHeight(40)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        timeline_area = QWidget()
        timeline_area.setFixedWidth(40)
        
        line = QFrame(timeline_area)
        line.setStyleSheet("background-color: #E5E7EB;")
        line.setFixedWidth(2)
        line.setGeometry(19, 0, 2, 40)
        
        dot = QFrame(timeline_area)
        dot.setFixedSize(14, 14)
        dot.setGeometry(13, 13, 14, 14)
        dot.setStyleSheet("background-color: #9CA3AF; border-radius: 7px; border: 3px solid #F9FAFB;")
        
        layout.addWidget(timeline_area)
        
        lbl = QLabel(date_str)
        lbl.setStyleSheet("color: #374151; font-size: 14px; font-weight: 900; letter-spacing: 1px;")
        layout.addWidget(lbl)

class TimelineItemWidget(QWidget):
    def __init__(self, time_str, raw_desc, amount, is_last=False):
        super().__init__()
        self.setFixedHeight(66)
        self.full_desc = raw_desc # 保留完整描述用于详情展示
        self.amount = amount
        self.time_str = time_str
        
        tag = ""
        main_text = raw_desc
        import re
        m = re.match(r'^【(.*?)】(.*)', raw_desc)
        if m:
            tag = m.group(1)
            main_text = m.group(2).strip()
            
        is_success = "完成" in main_text
        is_fail = "失败" in main_text
        main_text = main_text.replace("完成", "").replace("失败", "").strip()
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 20, 8)
        layout.setSpacing(0)
        
        timeline_area = QWidget()
        timeline_area.setFixedWidth(40)
        
        line = QFrame(timeline_area)
        line.setStyleSheet("background-color: #E5E7EB;")
        line.setFixedWidth(2)
        if is_last:
            line.setGeometry(19, 0, 2, 30) # Only upper half
        else:
            line.setGeometry(19, 0, 2, 66)
        
        dot = QFrame(timeline_area)
        dot.setFixedSize(10, 10)
        dot.setGeometry(15, 24, 10, 10)
        dot_color = RED_ACCENT if amount > 0 else GREEN_ACCENT
        dot.setStyleSheet(f"background-color: {dot_color}; border-radius: 5px; border: 2px solid white;")
        
        layout.addWidget(timeline_area)
        
        card = QFrame()
        card.setCursor(Qt.CursorShape.PointingHandCursor) # 增加手型光标
        card.setObjectName("TimelineCard")
        card.setStyleSheet("""
            QFrame#TimelineCard {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #F3F4F6;
            }
            QFrame#TimelineCard:hover {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(12, 0, 16, 0)
        
        time_lbl = QLabel(time_str)
        time_lbl.setFixedWidth(42)
        time_lbl.setStyleSheet("color: #9CA3AF; font-size: 12px; font-weight: bold; font-family: 'Consolas', monospace; border: none; background: transparent;")
        card_layout.addWidget(time_lbl)
        
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 10, 0, 10)
        content_layout.setSpacing(4)
        
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        
        if tag:
            tag_lbl = QLabel(tag)
            common_style = "padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: bold; border: none; margin-right: 4px;"
            if tag == "目标": tag_lbl.setStyleSheet(f"background-color: #E0F2FE; color: #0369A1; {common_style}")
            elif tag == "习惯": tag_lbl.setStyleSheet(f"background-color: #F3E8FF; color: #6B21A8; {common_style}")
            elif tag == "清单": tag_lbl.setStyleSheet(f"background-color: #DCFCE7; color: #15803D; {common_style}")
            else: tag_lbl.setStyleSheet(f"background-color: #F3F4F6; color: #374151; {common_style}")
            top_row.addWidget(tag_lbl)
            
        # 对主文本进行摘要处理
        font = QFont("Microsoft YaHei", 13, 800)
        fm = QFontMetrics(font)
        # 限制显示长度，如果过长则摘要
        display_text = fm.elidedText(main_text, Qt.TextElideMode.ElideRight, 200)
        
        title_lbl = QLabel(display_text)
        title_lbl.setFont(font)
        title_lbl.setStyleSheet("color: #1F2937; border: none; background: transparent;")
        top_row.addWidget(title_lbl)
        
        from PyQt6.QtWidgets import QGraphicsDropShadowEffect
        from PyQt6.QtGui import QColor
        if is_success:
            status_lbl = QLabel("✓")
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_lbl.setFixedSize(18, 18)
            status_lbl.setStyleSheet("""
                color: white; 
                background-color: #10B981; 
                border-radius: 9px; 
                font-size: 11px; 
                font-weight: bold;
            """)
            top_row.addWidget(status_lbl)
        elif is_fail:
            status_lbl = QLabel("✕")
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_lbl.setFixedSize(18, 18)
            status_lbl.setStyleSheet("""
                color: white; 
                background-color: #F97316; 
                border-radius: 9px; 
                font-size: 10px; 
                font-weight: bold;
            """)
            top_row.addWidget(status_lbl)
            
        top_row.addStretch()
        content_layout.addLayout(top_row)
        card_layout.addLayout(content_layout)
        
        amt_disp = f"{round(amount, 2):g}"
        sign = '+' if amount > 0 else ''
        color = RED_ACCENT if amount > 0 else GREEN_ACCENT
        
        amt_lbl = QLabel(f"{sign}{amt_disp}")
        amt_lbl.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 900; font-family: 'Consolas', monospace; border: none; background: transparent;")
        card_layout.addWidget(amt_lbl)
        
        layout.addWidget(card)

    def mousePressEvent(self, event):
        """点击弹出完整信息"""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
        from PyQt6.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("流水详情")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(15)
        
        # 样式
        dialog.setStyleSheet("""
            QLabel { font-family: 'Microsoft YaHei'; font-size: 14px; color: #2E3440; }
        """)
        
        # 发生时间
        time_layout = QHBoxLayout()
        time_label = QLabel("📅 发生时间:")
        time_label.setStyleSheet("font-weight: bold; color: #4C566A;")
        time_val = QLabel(self.time_str if len(self.time_str) > 5 else f"今日 {self.time_str}")
        time_layout.addWidget(time_label)
        time_layout.addWidget(time_val)
        time_layout.addStretch()
        layout.addLayout(time_layout)
        
        # 明细内容
        content_label = QLabel("📝 明细记录:")
        content_label.setStyleSheet("font-weight: bold; color: #4C566A;")
        layout.addWidget(content_label)
        
        content_val = QLabel(self.full_desc)
        content_val.setWordWrap(True) # 开启自动换行
        content_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        content_val.setStyleSheet("""
            background-color: #F8FAFC; 
            padding: 12px; 
            border-radius: 6px; 
            color: #1F2937;
            border: 1px solid #E2E8F0;
            line-height: 1.6;
        """)
        layout.addWidget(content_val)
        
        # 变动金额
        amt_layout = QHBoxLayout()
        amt_label = QLabel("💰 变动金额:")
        amt_label.setStyleSheet("font-weight: bold; color: #4C566A;")
        
        amt_disp = f"{round(self.amount, 2):g}"
        sign = '+' if self.amount > 0 else ''
        color = "#BF616A" if self.amount < 0 else "#A3BE8C"
        
        amt_val = QLabel(f"{sign}{amt_disp} 🪙")
        amt_val.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 800; font-family: 'Consolas';")
        
        amt_layout.addWidget(amt_label)
        amt_layout.addWidget(amt_val)
        amt_layout.addStretch()
        layout.addLayout(amt_layout)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.setFixedSize(80, 32)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(f"background-color: {GREEN_ACCENT}; color: white; border-radius: 4px; font-weight: bold;")
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        layout.addLayout(btn_layout)
        
        dialog.exec()

class FullLedgerDialog(QDialog):
    """完整流水查询弹窗"""
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("金币流水明细")
        self.setFixedSize(450, 600)
        self._build_ui()
        self._load_data()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setStyleSheet("background-color: #F9FAFB;")
        
        # 头部统计悬浮卡片
        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        header_card.setStyleSheet("""
            QFrame#HeaderCard {
                background-color: white;
                border-bottom: 1px solid #E5E7EB;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(20, 16, 20, 16)
        header_layout.setSpacing(12)
        
        # Title & Filter
        title_row = QHBoxLayout()
        title_lbl = QLabel("💳 资金明细")
        title_lbl.setStyleSheet(f"color: #1F2937; font-size: 16px; font-weight: bold; font-family: 'Microsoft YaHei'; border: none;")
        title_row.addWidget(title_lbl)
        
        self.period_combo = QComboBox()
        self.period_combo.addItems(["最近7天", "最近30天", "本月", "全部"])
        self.period_combo.setStyleSheet("""
            QComboBox {
                padding: 4px 8px; 
                border: 1px solid #D1D5DB; 
                border-radius: 8px; 
                background: white; 
                color: #374151;
                font-size: 13px;
            }
            QComboBox:hover {
                border: 1px solid #9CA3AF;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
        """)
        self.period_combo.currentIndexChanged.connect(self._load_data)
        title_row.addStretch()
        title_row.addWidget(self.period_combo)
        header_layout.addLayout(title_row)
        
        # Stats summary
        stats_row = QHBoxLayout()
        self.total_in_val = QLabel("+0")
        self.total_in_val.setStyleSheet(f"color: {RED_ACCENT}; font-size: 24px; font-weight: 900; font-family: 'Consolas', monospace; border: none;")
        in_lbl = QLabel("总收入")
        in_lbl.setStyleSheet("color: #6B7280; font-size: 12px; border: none;")
        
        in_box = QVBoxLayout()
        in_box.addWidget(in_lbl)
        in_box.addWidget(self.total_in_val)
        stats_row.addLayout(in_box)
        
        stats_row.addSpacing(40)
        
        self.total_out_val = QLabel("0")
        self.total_out_val.setStyleSheet(f"color: {GREEN_ACCENT}; font-size: 24px; font-weight: 900; font-family: 'Consolas', monospace; border: none;")
        out_lbl = QLabel("总支出")
        out_lbl.setStyleSheet("color: #6B7280; font-size: 12px; border: none;")
        
        out_box = QVBoxLayout()
        out_box.addWidget(out_lbl)
        out_box.addWidget(self.total_out_val)
        stats_row.addLayout(out_box)
        stats_row.addStretch()
        
        header_layout.addLayout(stats_row)
        layout.addWidget(header_card)
        
        # 流水列表
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self.list_widget.setStyleSheet("""
            QListWidget { background-color: #F9FAFB; }
            QListWidget::item { padding: 0px; }
            QListWidget::item:selected { background: transparent; }
        """)
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        layout.addWidget(self.list_widget)
        
    def _load_data(self):
        idx = self.period_combo.currentIndex()
        history = self.db.get_ledger_history(2000)
        
        now = datetime.now()
        filtered = []
        
        for entry in history:
            try:
                dt = datetime.strptime(entry['created_at'], '%Y-%m-%d %H:%M:%S')
                if idx == 0 and (now - dt).days > 7: continue
                if idx == 1 and (now - dt).days > 30: continue
                if idx == 2 and (now.month != dt.month or now.year != dt.year): continue
                filtered.append(entry)
            except:
                pass
                
        self.list_widget.clear()
        
        if not filtered:
            item = QListWidgetItem("暂无流水记录")
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.list_widget.addItem(item)
            self.total_in_val.setText("+0")
            self.total_out_val.setText("0")
            return
            
        total_in = sum(e['amount'] for e in filtered if e['amount'] > 0)
        total_out = sum(e['amount'] for e in filtered if e['amount'] < 0)
        self.total_in_val.setText(f"+{round(total_in, 2):g}")
        self.total_out_val.setText(f"{round(total_out, 2):g}")
        
        current_date_str = None
        
        for i, entry in enumerate(filtered):
            date_header_str = "未知日期"
            time_only_str = ""
            try:
                dt = datetime.strptime(entry['created_at'], '%Y-%m-%d %H:%M:%S')
                date_header_str = dt.strftime('%Y年%m月%d日')
                if dt.date() == now.date():
                    date_header_str = "今天"
                elif dt.date() == (now - timedelta(days=1)).date():
                    date_header_str = "昨天"
                time_only_str = dt.strftime('%H:%M')
            except: pass
            
            if current_date_str != date_header_str:
                current_date_str = date_header_str
                
                hw = TimelineHeaderWidget(current_date_str)
                h_item = QListWidgetItem()
                h_item.setSizeHint(QSize(400, 40))
                self.list_widget.addItem(h_item)
                self.list_widget.setItemWidget(h_item, hw)
            
            amt = entry['amount']
            desc = format_ledger_desc(entry.get('description', '未知流水'))
            is_last = (i == len(filtered) - 1)
            
            iw = TimelineItemWidget(time_only_str, desc, amt, is_last)
            item = QListWidgetItem()
            item.setSizeHint(QSize(400, 66))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, iw)
