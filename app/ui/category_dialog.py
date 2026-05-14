# -*- coding: utf-8 -*-
"""
分类管理弹窗模块 (category_dialog.py) - 亮色升级版
=================================================
提供两个对话框：
1. CategoryManagerDialog 供用户自定义增删改查分类。
2. CategorySelectDialog 供日清单等模块启动专注前强制选择分类使用。
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, 
                             QPushButton, QLabel, QListWidget, QListWidgetItem,
                             QLineEdit, QComboBox, QMessageBox, QFrame, QFormLayout, QStyledItemDelegate, QStyle,
                             QTabWidget, QWidget, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QRect, QTimer
from PyQt6.QtGui import QColor, QPalette, QCursor, QFont, QFontMetrics

class GroupItemDelegate(QStyledItemDelegate):
    delete_clicked = pyqtSignal(str)
    
    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        rect = option.rect
        btn_rect = QRect(rect.right() - 25, rect.top() + (rect.height() - 20) // 2, 20, 20)
        painter.save()
        painter.setPen(QColor("#BF616A"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "×")
        painter.restore()
        
    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            rect = option.rect
            btn_rect = QRect(rect.right() - 35, rect.top(), 35, rect.height())
            if btn_rect.contains(event.pos()):
                self.delete_clicked.emit(index.data())
                return True
        return super().editorEvent(event, model, option, index)

EMOJI_CATEGORIES = {
    "生活 & 居家": [
        ("🪥", "刷牙"), ("🧴", "护肤/洗脸"), ("🚿", "洗澡"), ("🛏️", "叠被/睡眠"),
        ("🌞", "早起"), ("🌙", "早睡"), ("💧", "喝水"), ("🍎", "吃水果"),
        ("🥗", "吃蔬菜"), ("💊", "吃药"), ("🚭", "戒烟"), ("📵", "限屏幕"),
        ("💰", "记账/存钱"), ("🧹", "打扫"), ("🍳", "做饭"), ("🍽️", "一日三餐"),
        ("☕", "咖啡/茶"), ("🍷", "戒酒/饮品"), ("👗", "穿搭"), ("🗑️", "极简/扔垃圾"),
        ("🛒", "购物"), ("🐶", "遛狗/宠物"), ("🌱", "浇花"), ("🏠", "顾家")
    ],
    "学习 & 工作": [
        ("📖", "阅读"), ("🎧", "听书/播客"), ("💻", "编程/工作"), ("📚", "复习/背单字"),
        ("📝", "写日记/笔记"), ("💡", "思考/复盘"), ("🗣️", "口语/演讲"), ("🎓", "上课"),
        ("📈", "进阶/理财"), ("🎯", "目标/专注"), ("⏰", "时间管理"), ("🔬", "研究"),
        ("📁", "整理文件"), ("✏️", "写作/画图"), ("📊", "数据分析"), ("📋", "待办清单")
    ],
    "运动 & 健康": [
        ("🏃", "跑步"), ("🚶", "散步"), ("🏋️", "健身/铁"), ("🧘", "瑜伽/冥想"),
        ("🏊", "游泳"), ("🚴", "骑行"), ("🧗", "攀岩"), ("🏸", "羽毛球"),
        ("🏀", "篮球"), ("⚽", "足球"), ("🎾", "网球"), ("🏓", "乒乓球"),
        ("🕺", "跳舞"), ("💪", "力量训练"), ("⚖️", "称体重"), ("❤️", "健康监测")
    ],
    "心理 & 休闲": [
        ("🙏", "感恩"), ("😌", "放松/深呼吸"), ("🎨", "画画"), ("🎵", "练琴/音乐"),
        ("🎤", "唱歌"), ("🎮", "游戏"), ("🎬", "看电影/剧"), ("📱", "刷社交"),
        ("📸", "摄影"), ("🎲", "桌游"), ("🧩", "拼图/乐高"), ("🍿", "零食"),
        ("🎂", "生日/庆祝"), ("💬", "社交/聊天"), ("🎉", "聚会"), ("✈️", "旅行")
    ],
    "交通 & 其他": [
        ("🚗", "开车"), ("🚌", "公交"), ("🚇", "地铁"), ("🚕", "打车"),
        ("🚲", "单车"), ("🏫", "学校"), ("🏢", "公司"), ("🏥", "医院"),
        ("🗺️", "导航"), ("⛽", "加油"), ("🏪", "便利店"), ("⭐", "综合类")
    ]
}

class IconSelectorDialog(QDialog):
    """Emoji 图标选择器"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择 Emoji 图标")
        self.setFixedSize(480, 420)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; color: #2E3440; font-family: 'Microsoft YaHei'; }
            QTabWidget::pane { border: 1px solid #D8DEE9; border-radius: 4px; margin-top: -1px; background: #FFFFFF; }
            QTabBar::tab { background: #F0F2F5; color: #4C566A; padding: 8px 12px; border: 1px solid #D8DEE9; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #FFFFFF; color: #2E3440; font-weight: bold; border-bottom-color: #FFFFFF; }
        """)
        self.selected_icon = None

        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        emoji_btn_style = """
            QPushButton { font-size: 22px; background: #F0F2F5; border: 1px solid #D8DEE9; border-radius: 6px; }
            QPushButton:hover { background: #E0E8F0; border: 1px solid #5E81AC; }
        """
        for cat_name, emoji_list in EMOJI_CATEGORIES.items():
            tab_widget = QWidget()
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            content = QWidget()
            grid_layout = QGridLayout(content)
            grid_layout.setSpacing(6)
            grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            for idx, (emoji, name) in enumerate(emoji_list):
                btn = QPushButton(emoji)
                btn.setFixedSize(45, 45)
                btn.setToolTip(name)
                btn.setStyleSheet(emoji_btn_style)
                btn.clicked.connect(lambda *args, e=emoji: self._on_select(e))
                grid_layout.addWidget(btn, idx // 8, idx % 8)
            scroll.setWidget(content)
            tab_layout = QVBoxLayout(tab_widget)
            tab_layout.setContentsMargins(0, 0, 0, 0)
            tab_layout.addWidget(scroll)
            self.tabs.addTab(tab_widget, cat_name)
        main_layout.addWidget(self.tabs)

    def _on_select(self, emoji):
        self.selected_icon = emoji
        self.accept()

class CategoryManagerDialog(QDialog):
    def __init__(self, category_manager, parent=None):
        super().__init__(parent)
        self.category_manager = category_manager
        self.setWindowTitle("⚙️ 分类管理")
        self.setMinimumSize(500, 350)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; color: #2E3440; font-family: 'Microsoft YaHei'; }
            QListWidget { background-color: #F8F9FB; border: 1px solid #D8DEE9; border-radius: 6px; padding: 4px; }
            QListWidget::item:selected { background-color: #5E81AC; color: white; border-radius: 4px; }
            QLineEdit, QComboBox { border: 1px solid #D8DEE9; border-radius: 4px; padding: 4px; background: white; }
            QPushButton { background-color: #F0F2F5; border: 1px solid #D8DEE9; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #E5E9F0; }
        """)
        self._build_ui()
        self._load_categories()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list.model().rowsMoved.connect(self._on_reordered)
        self.list.currentRowChanged.connect(self._on_selected)
        left.addWidget(QLabel("分类列表:"))
        left.addWidget(self.list)
        layout.addLayout(left, 1)

        right = QVBoxLayout()
        form = QFormLayout()
        self.name_in = QLineEdit()
        self.icon_in = QLineEdit()
        self.group_cb = QComboBox()
        self.group_cb.setEditable(True)
        self.color_in = QLineEdit()
        form.addRow("名称:", self.name_in)
        form.addRow("图标:", self.icon_in)
        form.addRow("分组:", self.group_cb)
        form.addRow("颜色:", self.color_in)
        right.addLayout(form)

        btns = QHBoxLayout()
        add_btn = QPushButton("新增")
        add_btn.clicked.connect(self._on_add)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._on_save)
        del_btn = QPushButton("删除")
        del_btn.setStyleSheet("QPushButton { background-color: #BF616A; color: white; }")
        del_btn.clicked.connect(self._on_delete)
        btns.addWidget(add_btn); btns.addWidget(save_btn); btns.addWidget(del_btn)
        right.addLayout(btns)
        layout.addLayout(right, 2)

    def _load_categories(self):
        self.list.clear()
        self.categories = self.category_manager.get_all_active()
        groups = set(["输入", "输出", "生活"])
        for c in self.categories:
            item = QListWidgetItem(f"{c['icon']} {c['name']}")
            item.setData(Qt.ItemDataRole.UserRole, c)
            self.list.addItem(item)
            groups.add(c['group_name'])
        self.group_cb.clear()
        self.group_cb.addItems(sorted(list(groups)))

    def _on_selected(self, idx):
        if idx < 0: return
        cat = self.categories[idx]
        self.current_id = cat['id']
        self.name_in.setText(cat['name'])
        self.icon_in.setText(cat['icon'])
        self.group_cb.setCurrentText(cat['group_name'])
        self.color_in.setText(cat['color'])

    def _on_add(self):
        self.category_manager.add_category(self.name_in.text(), self.icon_in.text(), self.color_in.text(), self.group_cb.currentText())
        self._load_categories()

    def _on_save(self):
        if hasattr(self, 'current_id'):
            self.category_manager.update_category(self.current_id, self.name_in.text(), self.icon_in.text(), self.color_in.text(), self.group_cb.currentText())
            self._load_categories()

    def _on_delete(self):
        if hasattr(self, 'current_id'):
            self.category_manager.remove_category(self.current_id)
            self._load_categories()

    def _on_reordered(self, *args):
        ids = []
        for i in range(self.list.count()):
            cat = self.list.item(i).data(Qt.ItemDataRole.UserRole)
            ids.append((cat['id'], i+1))
        self.category_manager.reorder_categories(ids)

class CategorySelectDialog(QDialog):
    """分类选择器 - 亮色升级版"""
    def __init__(self, category_manager, task_title="未命名任务", parent=None):
        super().__init__(parent)
        self.category_manager = category_manager
        self.task_title = task_title
        self.selected_category_id = None
        self.selected_group_name = None
        self.initial_group = None # 预设分组
        
        self.setWindowTitle("选择活动分类")
        self.setFixedSize(450, 400)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; }
            QLabel { color: #2E3440; font-family: 'Microsoft YaHei'; }
            QTabWidget::pane { border: 1px solid #D8DEE9; border-radius: 4px; background: white; }
            QTabBar::tab { background: #F0F2F5; padding: 8px 20px; border: 1px solid #D8DEE9; min-width: 80px; }
            QTabBar::tab:selected { background: white; border-bottom-color: white; font-weight: bold; color: #5E81AC; }
        """)
        self._build_ui()

    def set_initial_group(self, group_name):
        """设置预选分组"""
        self.initial_group = group_name
        # 尝试切换对应的 tab
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == group_name:
                self.tabs.setCurrentIndex(i)
                break

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel(f"<b>🎯 专注目标:</b> {self.task_title}\n请选择分类：")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("QTabWidget::tab-bar { alignment: center; }")
        
        grouped_cats = self.category_manager.get_grouped()
        # 确保显示所有分组
        for group_name in ["输入", "输出", "生活"]:
            cats = grouped_cats.get(group_name, [])
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            content = QWidget()
            grid = QGridLayout(content)
            grid.setSpacing(10)
            grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            
            from activity_panel import CategoryButton
            for i, cat in enumerate(cats):
                btn = CategoryButton(cat)
                btn.category_clicked.connect(self._on_category_clicked)
                grid.addWidget(btn, i // 4, i % 4)
            
            scroll.setWidget(content)
            tab_layout.addWidget(scroll)
            self.tabs.addTab(tab, group_name)
            
        layout.addWidget(self.tabs)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("QPushButton { background: #E5E9F0; border-radius: 4px; padding: 6px 15px; color: #4C566A; } QPushButton:hover { background: #BF616A; color: white; }")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_category_clicked(self, cat_data):
        self.selected_category_id = cat_data.get("id")
        self.selected_group_name = cat_data.get("group_name")
        self.accept()
