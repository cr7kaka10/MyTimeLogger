# -*- coding: utf-8 -*-
"""
对话框模块 (dialogs.py)
======================
自定义对话框组件:
- MarkdownTextEdit: 支持 Markdown 列表实时渲染的富文本编辑器
- MarkdownInputDialog: 基于 MarkdownTextEdit 的输入对话框（暂停原因/专注总结）
"""

from PyQt6.QtWidgets import QTextEdit, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextListFormat, QTextCursor


class MarkdownTextEdit(QTextEdit):
    """
    增强版文本编辑器，支持:
    - 输入 "- " / "+ " / "* " + 空格 自动转为无序列表
    - 输入 "1." + 空格 自动转为有序列表
    - Ctrl+Enter 快捷提交所属对话框
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptRichText(True)
        self.setPlaceholderText("")
        self.document().setDocumentMargin(0)

    def keyPressEvent(self, event):
        cursor = self.textCursor()

        # 空格键：触发列表转换
        if event.key() == Qt.Key.Key_Space:
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            line_text = cursor.selectedText()
            cursor.clearSelection()

            # 无序列表 (- , + , * )
            if line_text in ["-", "+", "*"]:
                cursor.beginEditBlock()
                for _ in range(len(line_text)):
                    cursor.deletePreviousChar()
                list_format = QTextListFormat()
                list_format.setStyle(QTextListFormat.Style.ListDisc)
                list_format.setIndent(1)
                cursor.createList(list_format)
                cursor.endEditBlock()
                return

            # 有序列表 (1. )
            elif line_text == "1.":
                cursor.beginEditBlock()
                for _ in range(2):
                    cursor.deletePreviousChar()
                list_format = QTextListFormat()
                list_format.setStyle(QTextListFormat.Style.ListDecimal)
                list_format.setIndent(1)
                cursor.createList(list_format)
                cursor.endEditBlock()
                return

        # 回车键：Ctrl+Enter 快捷提交
        if event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                parent_dialog = self.window()
                if isinstance(parent_dialog, QDialog):
                    parent_dialog.accept()
                    return

        super().keyPressEvent(event)


class MarkdownInputDialog(QDialog):
    """
    支持 Markdown 输入的自定义对话框。

    特性:
    - Nord 暗色主题
    - 默认 "+" 列表符号起始
    - Cancel 在左、OK 在右
    - 支持 Ctrl+Enter 快捷提交

    Args:
        title: 对话框标题
        label: 提示文字
        parent: 父窗口
        initial_text: 初始文本内容
    """

    def __init__(self, title, label, parent=None, initial_text=""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 350)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)

        self.label = QLabel(label)
        self.label.setStyleSheet("font-weight: bold; color: #88C0D0; margin-bottom: 5px;")
        layout.addWidget(self.label)

        self.text_edit = MarkdownTextEdit()
        self.text_edit.setViewportMargins(0, 0, 0, 0)
        self.text_edit.document().setDocumentMargin(5)

        # 默认起始列表符号
        display_text = initial_text if initial_text else "+ "
        self.text_edit.setMarkdown(display_text)

        # 光标移到文本末尾
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)

        layout.addWidget(self.text_edit)

        # 按钮布局: Cancel 在左, OK 在右
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedWidth(80)
        self.cancel_btn.clicked.connect(self.reject)

        self.ok_btn = QPushButton("OK")
        self.ok_btn.setFixedWidth(80)
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setDefault(True)

        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        layout.addLayout(btn_layout)

        # Nord 暗色主题样式
        self.setStyleSheet("""
            QDialog { background-color: #2E3440; }
            QLabel { color: #ECEFF4; font-size: 14px; }
            QTextEdit { 
                background-color: #3B4252; 
                color: #ECEFF4; 
                border: 1px solid #4C566A; 
                border-radius: 4px;
                padding: 10px 10px 10px 5px;
                margin: 0px;
                font-size: 14px;
                selection-background-color: #88C0D0;
            }
            QPushButton { 
                background-color: #4C566A; 
                color: #ECEFF4; 
                border-radius: 4px; 
                padding: 6px 15px;
            }
            QPushButton:hover { background-color: #5E81AC; }
        """)

    def textValue(self):
        """导出为 Markdown 格式字符串"""
        return self.text_edit.toMarkdown()
