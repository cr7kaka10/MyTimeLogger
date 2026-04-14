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
                             QLineEdit, QComboBox, QMessageBox, QFrame, QFormLayout, QStyledItemDelegate, QStyle)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QRect, QTimer
from PyQt6.QtGui import QColor, QPalette, QCursor

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

class CategoryManagerDialog(QDialog):
    """分类管理 CRUD 弹窗"""
    
    def __init__(self, category_manager, parent=None):
        super().__init__(parent)
        self.category_manager = category_manager
        self.setWindowTitle("⚙️ 分类管理")
        self.setMinimumSize(500, 350)
        self.setStyleSheet("""
            QDialog { background-color: #2E3440; color: #D8DEE9; }
            QLabel { color: #D8DEE9; }
            QListWidget { background-color: #3B4252; color: #D8DEE9; border: 1px solid #4C566A; border-radius: 5px; }
            QLineEdit, QComboBox { background-color: #4C566A; color: #ECEFF4; border: 1px solid #434C5E; border-radius: 4px; padding: 4px; }
            QPushButton { background-color: #4C566A; color: #ECEFF4; border-radius: 4px; padding: 6px; }
            QPushButton:hover { background-color: #5E81AC; }
        """)
        self.current_category = None
        self._build_ui()
        self._load_categories()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)

        # 左侧列表
        left_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_list_selected)
        left_layout.addWidget(QLabel("已启用分类:"))
        left_layout.addWidget(self.list_widget)

        # 右侧表单
        right_layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        self.name_input = QLineEdit()
        self.icon_input = QLineEdit()
        self.icon_input.setPlaceholderText("如: 📖")
        
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_delegate = GroupItemDelegate(self)
        self.group_combo.setItemDelegate(self.group_delegate)
        self.group_delegate.delete_clicked.connect(self._on_delete_group)
        self.group_combo.view().viewport().installEventFilter(self)
        
        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText("如: #5E81AC")
        
        form_layout.addRow("名称:", self.name_input)
        form_layout.addRow("图标(Emoji):", self.icon_input)
        form_layout.addRow("分组:", self.group_combo)
        form_layout.addRow("颜色(Hex):", self.color_input)
        
        right_layout.addLayout(form_layout)

        # 按钮区域
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("🆕 新增")
        self.btn_save = QPushButton("💾 保存修改")
        self.btn_delete = QPushButton("🗑️ 删除")
        
        self.btn_add.clicked.connect(self._on_add)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_delete.clicked.connect(self._on_delete)

        self.btn_delete.setStyleSheet("QPushButton { background-color: #BF616A; } QPushButton:hover { background-color: #D08770; }")

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
