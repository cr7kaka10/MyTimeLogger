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

FA_CATEGORIES = {
    "工作 & 效率": [
        ("\uf02d", "书本/阅读"), ("\uf108", "电脑/编程"), ("\uf109", "台式机/办公"),
        ("\uf07b", "文件夹"), ("\uf115", "打开的文件夹"), ("\uf15c", "文档/笔记"),
        ("\uf0c6", "附件/回形针"), ("\uf0b1", "公文包/办公"), ("\uf02e", "书签/标记"),
        ("\uf1ea", "报纸/阅读"), ("\uf201", "趋势/数据"), ("\uf080", "条形图"),
        ("\uf200", "饼图"), ("\uf0ca", "列表/清单"), ("\uf0ae", "任务/进度"),
        ("\uf073", "日历/计划"), ("\uf133", "打卡/签到"), ("\uf274", "添加计划"),
        ("\uf017", "时钟/时间"), ("\uf0eb", "灯泡/创意"), ("\uf135", "火箭/起飞"),
        ("\uf0e8", "架构/网络"), ("\uf114", "空文件夹"), ("\uf0ce", "桌子/会议"),
        ("\uf03a", "列表/排序"), ("\uf0c5", "复制/文档"), ("\uf0ee", "上传/云端"),
        ("\uf019", "下载/保存"), ("\uf012", "信号/网络"), ("\uf2b5", "握手/合作"),
        ("\uf0a1", "喇叭/广播"), ("\uf55b", "钱包/财务"), ("\uf0d6", "钞票/资金"),
        ("\uf153", "人民币/日元"), ("\uf155", "美元/生意"), ("\uf24e", "天平/法律"),
        ("\uf21b", "身份/工牌")
    ],
    "生活 & 居家": [
        ("\uf015", "主页/家庭"), ("\uf236", "床/睡觉"), ("\uf2cd", "个人/洗头"),
        ("\uf2e7", "餐饮/吃饭"), ("\uf0f4", "咖啡/休息"), ("\uf0fc", "啤酒/饮酒"),
        ("\uf578", "鱼/海鲜"), ("\uf805", "汉堡/快餐"), ("\uf78c", "胡萝卜/蔬菜"),
        ("\uf07a", "购物车/购物"), ("\uf290", "袋子/买菜"), ("\uf54f", "商店/小卖部"),
        ("\uf68f", "店铺/商业"), ("\uf21e", "心跳/健康"), ("\uf0f9", "急救/看病"),
        ("\uf481", "药丸/吃药"), ("\uf118", "微笑/情绪"), ("\uf5a4", "戒指/首饰"),
        ("\uf1ae", "儿童/小孩"), ("\uf0c0", "群组/社交"), ("\uf002", "搜索/查找"),
        ("\uf234", "加好友/社交"), ("\uf1fd", "生日/蛋糕"), ("\uf06b", "火热/做饭"),
        ("\uf185", "太阳/白天"), ("\uf186", "月亮/夜晚"), ("\uf0e9", "雨伞/下雨"),
        ("\uf2dc", "雪花/冬天"), ("\uf021", "循环/刷新"), ("\uf1b2", "方块/积木"),
        ("\uf12e", "拼图/逻辑"), ("\uf06c", "叶子/环保"), ("\uf552", "洗手池/卫生间"),
        ("\uf2a0", "温度计/气温"), ("\uf1ad", "建筑/城市"), ("\uf2b9", "联系人/卡片"),
        ("\uf0f2", "行李/旅行")
    ],
    "娱乐 & 休闲": [
        ("\uf11b", "手柄/游戏"), ("\uf001", "音乐/听歌"), ("\uf025", "耳机/听课"),
        ("\uf008", "电影/影视"), ("\uf03e", "照片/图像"), ("\uf030", "相机/拍照"),
        ("\uf043", "水滴/画画"), ("\uf53f", "调色板/绘画"), ("\uf70c", "跑步/运动"),
        ("\uf44b", "哑铃/健身"), ("\uf434", "足球/球类"), ("\uf45f", "乒乓球/运动"),
        ("\uf6cf", "骰子/桌游"), ("\uf521", "VR/虚拟现实"), ("\uf5dc", "大脑/思考"),
        ("\uf188", "昆虫/自然"), ("\uf51f", "金币/财富"), ("\uf091", "奖杯/荣誉"),
        ("\uf005", "星星/收藏"), ("\uf145", "入场券/活动"), ("\uf5eb", "龙/虚幻"),
        ("\uf57a", "小人/舞蹈"), ("\uf5a0", "地图/冒险"), ("\uf500", "朋友/聚会"),
        ("\uf5b2", "魔术/魔法"), ("\uf0fb", "飞机/冲浪"), ("\uf29b", "购物中心/逛街")
    ],
    "交通 & 行程": [
        ("\uf1b9", "汽车/车"), ("\uf207", "公交/通勤"), ("\uf238", "火车/地铁"),
        ("\uf559", "出租车/打车"), ("\uf206", "自行车/骑行"), ("\uf2fc", "摩托/机车"),
        ("\uf072", "飞机/出差"), ("\uf5b0", "航班/出发"), ("\uf21d", "轮船/航海"),
        ("\uf275", "工厂/生产"), ("\uf0f8", "医院/医疗"), ("\uf19c", "大学/教育"),
        ("\uf549", "学校/校园"), ("\uf041", "坐标/打卡"), ("\uf5ea", "方向/路名"),
        ("\uf124", "图钉/地点"), ("\uf024", "旗帜/目的地"), ("\uf502", "指南针/导航")
    ],
    "物品 & 工具": [
        ("\uf5ad", "钢笔/写作"), ("\uf304", "原珠笔/记号"), ("\uf040", "铅笔/编辑"),
        ("\uf246", "鼠标/外设"), ("\uf11c", "键盘/输入"), ("\uf10a", "平板/电子"),
        ("\uf3ce", "手机/通讯"), ("\uf028", "喇叭/音量"), ("\uf0f3", "闹钟/提醒"),
        ("\uf023", "锁/隐私"), ("\uf13e", "解锁/公开"), ("\uf084", "钥匙/密码"),
        ("\uf013", "齿轮/机器"), ("\uf0ad", "扳手/修理"), ("\uf0e0", "信封/邮件"),
        ("\uf2b6", "打开的邮件"), ("\uf02c", "标签/分类"), ("\uf067", "加号/新建"),
        ("\uf00c", "打勾/完成"), ("\uf00d", "叉号/取消"), ("\uf071", "警告/注意"),
        ("\uf05a", "提示/信息"), ("\uf059", "问号/帮助"), ("\uf11e", "旗帜/里程碑"),
        ("\uf466", "快递箱/包裹"), ("\uf410", "手机应用/碎片"), ("\uf0c4", "剪刀/裁剪")
    ]
}

class IconSelectorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择主题矢量图标 (aTimeLogger 风格)")
        self.setFixedSize(540, 480)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; color: #2E3440; font-family: 'Microsoft YaHei'; }
            QTabWidget::pane { border: 1px solid #D8DEE9; border-radius: 4px; margin-top: -1px; background: #FFFFFF; }
            QTabBar::tab { background: #F0F2F5; color: #4C566A; padding: 8px 12px; border: 1px solid #D8DEE9; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #FFFFFF; color: #2E3440; font-weight: bold; border-bottom-color: #FFFFFF; }
        """)
        self.selected_icon = None
        self._full_lib_loaded = False 

        self._fa_font = QFont('Font Awesome 6 Free')
        self._fa_font.setWeight(QFont.Weight.Black)
        self._fa_font.setPixelSize(20)
        self._fa_fm = QFontMetrics(self._fa_font)
        
        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        icon_btn_style = """
            QPushButton { font-family: 'Font Awesome 6 Free'; font-size: 20px; font-weight: 900; background: #F0F2F5; color: #3B4252; border: 1px solid #D8DEE9; border-radius: 6px;} 
            QPushButton:hover { background: #E0E8F0; border: 1px solid #5E81AC; }
        """
        for cat_name, icon_list in FA_CATEGORIES.items():
            tab_widget = QWidget()
            grid_layout = QGridLayout(tab_widget)
            grid_layout.setSpacing(6)
            grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            col_idx = 0
            for char, name in icon_list:
                if not self._fa_fm.inFont(char): continue
                btn = QPushButton(char)
                btn.setFixedSize(45, 45)
                btn.setToolTip(name)
                btn.setStyleSheet(icon_btn_style)
                btn.clicked.connect(lambda *args, c=char: self._on_select(c))
                grid_layout.addWidget(btn, col_idx // 9, col_idx % 9)
                col_idx += 1
            self.tabs.addTab(tab_widget, cat_name)
            
        scroll_tab = QWidget()
        scroll_layout = QVBoxLayout(scroll_tab)
        self._full_lib_scroll_area = QScrollArea()
        self._full_lib_scroll_area.setWidgetResizable(True)
        self._full_lib_scroll_area.setWidget(QLabel("加载中..."))
        scroll_layout.addWidget(self._full_lib_scroll_area)
        self._full_lib_tab_index = self.tabs.addTab(scroll_tab, "🗃️ 完整库")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        main_layout.addWidget(self.tabs)

    def _on_select(self, char):
        self.selected_icon = char
        self.accept()

    def _on_tab_changed(self, index):
        if index == self._full_lib_tab_index and not self._full_lib_loaded:
            self._full_lib_loaded = True
            content = QWidget()
            grid = QGridLayout(content)
            idx = 0
            for code in range(0xf000, 0xf900):
                char = chr(code)
                if not self._fa_fm.inFont(char): continue
                btn = QPushButton(char)
                btn.setFixedSize(45, 45)
                btn.setStyleSheet("QPushButton { font-family: 'Font Awesome 6 Free'; font-size: 20px; font-weight: 900; background: #F0F2F5; color: #3B4252; border: 1px solid #D8DEE9; border-radius: 6px; } QPushButton:hover { background: #5E81AC; color: white; }")
                btn.clicked.connect(lambda *args, c=char: self._on_select(c))
                grid.addWidget(btn, idx // 9, idx % 9)
                idx += 1
            self._full_lib_scroll_area.setWidget(content)

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
