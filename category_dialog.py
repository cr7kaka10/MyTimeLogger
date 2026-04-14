# -*- coding: utf-8 -*-
"""
分类管理弹窗模块 (category_dialog.py)
=====================================
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
        # 增大字号让其更加明显
        font.setPointSize(16)
        painter.setFont(font)
        painter.drawText(btn_rect, Qt.AlignmentFlag.AlignCenter, "×")
        painter.restore()
        
    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease:
            rect = option.rect
            # 扩大点按热区：从右侧算起宽度达35px，高度覆盖整个条目
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
            QTabBar { font-family: 'Microsoft YaHei'; }
            QTabBar::tab { background: #F0F2F5; color: #4C566A; padding: 8px 12px; border: 1px solid #D8DEE9; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #FFFFFF; color: #2E3440; font-weight: bold; border-bottom-color: #FFFFFF; }
            QToolTip { font-family: 'Microsoft YaHei'; background: #FFFFFF; color: #2E3440; border: 1px solid #D8DEE9; }
        """)
        self.selected_icon = None
        self._full_lib_loaded = False  # 懒加载标记

        # 构建 FA 字体检测器，用于过滤无效图标
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
                if not self._fa_fm.inFont(char):
                    continue
                btn = QPushButton(char)
                btn.setFixedSize(45, 45)
                btn.setToolTip(name)
                btn.setStyleSheet(icon_btn_style)
                btn.clicked.connect(lambda *args, c=char: self._on_select(c))
                grid_layout.addWidget(btn, col_idx // 9, col_idx % 9)
                col_idx += 1
                
            self.tabs.addTab(tab_widget, cat_name)
            
        # ====== 扩增：完整字库滚动屏（懒加载） ======
        scroll_tab = QWidget()
        scroll_layout = QVBoxLayout(scroll_tab)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        self._full_lib_scroll_area = QScrollArea()
        self._full_lib_scroll_area.setWidgetResizable(True)
        self._full_lib_scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        placeholder = QLabel("切换到此页面后将自动加载...")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #4C566A; font-size: 14px;")
        self._full_lib_scroll_area.setWidget(placeholder)
        
        scroll_layout.addWidget(self._full_lib_scroll_area)
        self._full_lib_tab_index = self.tabs.addTab(scroll_tab, "🗃️ 完整字库(688个)")
        
        # 切换 tab 时懒加载完整字库
        self.tabs.currentChanged.connect(self._on_tab_changed)
            
        main_layout.addWidget(self.tabs)

    def _on_select(self, char):
        """选中图标后关闭弹窗"""
        self.selected_icon = char
        self.accept()

    def _on_tab_changed(self, index):
        """切换到完整字库 tab 时懒加载按钮，并过滤无效图标"""
        if index == self._full_lib_tab_index and not self._full_lib_loaded:
            self._full_lib_loaded = True
            content_widget = QWidget()
            full_grid = QGridLayout(content_widget)
            full_grid.setSpacing(6)
            full_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            
            icon_btn_style = """
                QPushButton { font-family: 'Font Awesome 6 Free'; font-size: 20px; font-weight: 900; background: #F0F2F5; color: #3B4252; border: 1px solid #D8DEE9; border-radius: 6px;} 
                QPushButton:hover { background: #E0E8F0; border: 1px solid #5E81AC; }
            """
            col_idx = 0
            for char_code in range(0xf000, 0xf900):
                char = chr(char_code)
                if not self._fa_fm.inFont(char):
                    continue
                btn = QPushButton(char)
                btn.setFixedSize(45, 45)
                btn.setStyleSheet(icon_btn_style)
                btn.clicked.connect(lambda *args, c=char: self._on_select(c))
                full_grid.addWidget(btn, col_idx // 9, col_idx % 9)
                col_idx += 1
            
            self._full_lib_scroll_area.setWidget(content_widget)
            # 更新 tab 标题显示实际数量
            self.tabs.setTabText(self._full_lib_tab_index, f"🗃️ 完整字库({col_idx}个)")


class CategoryManagerDialog(QDialog):
    """分类管理 CRUD 弹窗"""
    
    def __init__(self, category_manager, parent=None):
        super().__init__(parent)
        self.category_manager = category_manager
        self.setWindowTitle("⚙️ 分类管理")
        self.setMinimumSize(500, 350)
        self.setStyleSheet("""
            QDialog { background-color: #FFFFFF; color: #2E3440; font-family: 'Microsoft YaHei'; }
            QLabel { color: #2E3440; font-family: 'Microsoft YaHei'; }
            QListWidget { background-color: #F0F2F5; color: #3B4252; border: 1px solid #D8DEE9; border-radius: 5px; font-family: 'Font Awesome 6 Free', 'Microsoft YaHei'; font-weight: bold; }
            QListWidget::item:selected { background-color: #E5E9F0; color: #5E81AC; border-left: 3px solid #5E81AC; }
            QLineEdit, QComboBox { background-color: #FFFFFF; color: #2E3440; border: 1px solid #D8DEE9; border-radius: 4px; padding: 4px; font-family: 'Font Awesome 6 Free', 'Microsoft YaHei'; font-weight: bold; }
            QPushButton { background-color: #F0F2F5; color: #3B4252; border: 1px solid #D8DEE9; border-radius: 4px; padding: 6px; font-family: 'Font Awesome 6 Free', 'Microsoft YaHei'; }
            QPushButton:hover { background-color: #E0E8F0; }
        """)
        self.current_category = None
        self._build_ui()
        self._load_categories()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # 左侧列表
        left_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        # 开启拖拽支持
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_widget.model().rowsMoved.connect(self._on_list_reordered)
        self.list_widget.currentRowChanged.connect(self._on_list_selected)
        left_layout.addWidget(QLabel("已启用分类 (支持拖拽排序):"))
        left_layout.addWidget(self.list_widget)

        # 右侧表单
        right_layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        self.name_input = QLineEdit()
        self.icon_input = QLineEdit()
        self.icon_input.setPlaceholderText("可输Emoji，或点右侧挑选=>")
        
        self.icon_btn = QPushButton("库")
        self.icon_btn.setStyleSheet("""
            QPushButton { background-color: #5E81AC; color: white; border: none; } 
            QPushButton:hover { background-color: #81A1C1; }
        """)
        self.icon_btn.clicked.connect(self._open_icon_picker)
        
        icon_layout = QHBoxLayout()
        icon_layout.addWidget(self.icon_input)
        icon_layout.addWidget(self.icon_btn)
        
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_delegate = GroupItemDelegate(self)
        self.group_combo.setItemDelegate(self.group_delegate)
        self.group_delegate.delete_clicked.connect(self._on_delete_group)
        self.group_combo.view().viewport().installEventFilter(self)
        
        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText("如: #5E81AC")
        
        form_layout.addRow("名称:", self.name_input)
        form_layout.addRow("图标:", icon_layout)
        form_layout.addRow("分组:", self.group_combo)
        form_layout.addRow("颜色:", self.color_input)
        
        right_layout.addLayout(form_layout)

        # 按钮区域
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("🆕 新增")
        self.btn_save = QPushButton("💾 保存修改")
        self.btn_delete = QPushButton("🗑️ 删除")
        
        self.btn_add.clicked.connect(self._on_add)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_delete.clicked.connect(self._on_delete)

        self.btn_delete.setStyleSheet("""
            QPushButton { background-color: #BF616A; color: white; border: none; } 
            QPushButton:hover { background-color: #D08770; }
        """)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_delete)
        
        right_layout.addStretch()
        right_layout.addLayout(btn_layout)

        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)
        
        # 底部关闭按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom_layout.addWidget(close_btn)
        right_layout.addLayout(bottom_layout)

    def _load_categories(self):
        self.list_widget.clear()
        self.categories = self.category_manager.get_all_active()
        
        # 收集所有的 unique groups
        group_set = set()
        for cat in self.categories:
            item = QListWidgetItem(f"{cat['icon']} {cat['name']} ({cat['group_name']})")
            item.setData(Qt.ItemDataRole.UserRole, cat)
            self.list_widget.addItem(item)
            group_set.add(cat['group_name'])
            
        # 补充默认分组如果不存在
        for default_grp in ["输入", "输出", "生活"]:
            group_set.add(default_grp)
            
        current_text = self.group_combo.currentText()
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItems(sorted(list(group_set)))
        self.group_combo.setCurrentText(current_text if current_text else "输入")
        self.group_combo.blockSignals(False)
            
        self._clear_form()

    def _open_icon_picker(self):
        diag = IconSelectorDialog(self)
        if diag.exec() == QDialog.DialogCode.Accepted and diag.selected_icon:
            self.icon_input.setText(diag.selected_icon)

    def _clear_form(self):
        self.current_category = None
        self.name_input.clear()
        self.icon_input.clear()
        self.color_input.setText("#5E81AC")
        self.group_combo.setCurrentIndex(0)

    def _on_list_selected(self, index):
        if index < 0 or index >= len(self.categories):
            return
        cat = self.categories[index]
        self.current_category = cat
        self.name_input.setText(cat['name'])
        self.icon_input.setText(cat.get('icon', ''))
        self.color_input.setText(cat.get('color', '#5E81AC'))
        self.group_combo.setCurrentText(cat.get('group_name', '输入'))

    def _on_add(self):
        name = self.name_input.text().strip()
        icon = self.icon_input.text().strip()
        color = self.color_input.text().strip()
        group = self.group_combo.currentText()
        
        if not name:
            QMessageBox.warning(self, "错误", "名称不能为空")
            return
            
        cat_id = self.category_manager.add_category(name, icon, color, group)
        if cat_id:
            QMessageBox.information(self, "成功", "分类添加成功")
            self._load_categories()
        else:
            QMessageBox.critical(self, "错误", "添加失败")

    def _on_save(self):
        if not self.current_category:
            QMessageBox.warning(self, "提示", "请先选择要修改的分类")
            return
            
        name = self.name_input.text().strip()
        icon = self.icon_input.text().strip()
        color = self.color_input.text().strip()
        group = self.group_combo.currentText()
        cat_id = self.current_category['id']
        
        if self.category_manager.update_category(cat_id, name, icon, color, group):
            QMessageBox.information(self, "成功", "修改已保存")
            self._load_categories()
        else:
            QMessageBox.critical(self, "错误", "修改失败")

    def _on_list_reordered(self, parent, start, end, destination, row):
        """处理拖拽排序回写"""
        order_list = []
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            cat_data = item.data(Qt.ItemDataRole.UserRole)
            if cat_data:
                order_list.append((cat_data['id'], index + 1))
        
        if order_list:
            if self.category_manager.reorder_categories(order_list):
                # 重新加载同步所有本地列表数据
                self._load_categories()
            else:
                QMessageBox.warning(self, "错误", "排序保存失败！")

    def _on_delete(self):
        if not self.current_category:
            return
            
        reply = QMessageBox.question(self, "确认删除", f"确定要删除分类 '{self.current_category['name']}' 吗？\n(这不会删除历史记录)", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            if self.category_manager.remove_category(self.current_category['id']):
                self._load_categories()
            else:
                QMessageBox.critical(self, "错误", "删除失败")

    def _on_delete_group(self, group_name):
        # 隐藏下拉框
        self.group_combo.hidePopup()
        reply = QMessageBox.question(self, "确认删除分组", f"删除分组 '{group_name}' 会把该组下所有相关分类移动至 '未分组'，确定吗？", 
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            for cat in self.categories:
                if cat['group_name'] == group_name:
                    self.category_manager.update_category(cat['id'], cat['name'], cat.get('icon', ''), cat.get('color', ''), "未分组")
            self._load_categories()
            # 从下拉框中移除
            idx = self.group_combo.findText(group_name)
            if idx >= 0:
                self.group_combo.removeItem(idx)
            self.group_combo.setCurrentText("未分组")

    def eventFilter(self, obj, event):
        # 拦截下拉框弹窗的列表点击事件以支持 X 号删除
        if hasattr(self, 'group_combo') and obj == self.group_combo.view().viewport():
            if event.type() == QEvent.Type.MouseButtonRelease:
                pos = event.pos()
                index = self.group_combo.view().indexAt(pos)
                if index.isValid():
                    rect = self.group_combo.view().visualRect(index)
                    # 匹配委托里的热区：右侧 35px
                    btn_rect = QRect(rect.right() - 35, rect.top(), 35, rect.height())
                    if btn_rect.contains(pos):
                        group_name = index.data()
                        if group_name:
                            # 异步调用删除，避免闪退或重入
                            QTimer.singleShot(0, lambda: self._on_delete_group(group_name))
                        return True
        return super().eventFilter(obj, event)


class CategorySelectDialog(QDialog):
    """日清单等功能启动专注前弹出的精简分类选择器"""
    
    def __init__(self, category_manager, task_title="未命名任务", parent=None):
        super().__init__(parent)
        self.category_manager = category_manager
        self.task_title = task_title
        self.selected_category_id = None
        self.selected_group_name = None
        
        self.setWindowTitle("请选择活动分类")
        self.setFixedSize(400, 300)
        self.setStyleSheet("""
            QDialog { background-color: #2E3440; color: #D8DEE9; }
            QLabel { color: #ECEFF4; }
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        title_label = QLabel(f"即将开始: {self.task_title}\n请选择它属于哪个分类：")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 13px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)

        grid_layout = QGridLayout()
        grouped_cats = self.category_manager.get_grouped()
        
        row_offset = 0
        for group_name, cats in grouped_cats.items():
            if group_name not in ["输入", "输出"]:
                continue
            if not cats: continue
            
            # 分组标题
            grp_label = QLabel(f"── {group_name} ──")
            grp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grp_label.setStyleSheet("color: #4C566A; font-size: 11px;")
            grid_layout.addWidget(grp_label, row_offset, 0, 1, 4)
            row_offset += 1
            
            from activity_panel import CategoryButton
            for i, cat in enumerate(cats):
                btn = CategoryButton(cat)
                btn.category_clicked.connect(self._on_category_clicked)
                grid_layout.addWidget(btn, row_offset + i // 4, i % 4)
            
            row_offset += (len(cats) - 1) // 4 + 1
            
        layout.addLayout(grid_layout)
        layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton { background-color: #4C566A; color: #ECEFF4; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #BF616A; }
        """)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_category_clicked(self, cat_data):
        self.selected_category_id = cat_data.get("id")
        self.selected_group_name = cat_data.get("group_name")
        self.accept()
