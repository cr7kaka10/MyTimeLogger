# -*- coding: utf-8 -*-
import os
import json
import logging
from datetime import datetime, timedelta, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QFrame, QStackedWidget, QGridLayout,
    QLineEdit, QTextEdit, QTabWidget, QGraphicsOpacityEffect, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt6.QtGui import QFont, QColor

from config import save_config
from utils import resource_path

logger = logging.getLogger(__name__)

# ==================== 配色与常量 (同步项目风格) ====================
TEXT_PRIMARY = "#2E3440"
TEXT_SECONDARY = "#4C566A"
BORDER_COLOR = "#D8DEE9"
GREEN_ACCENT = "#A3BE8C"
RED_ACCENT = "#BF616A"
BG_LIGHT = "#FFFFFF"
CST = timezone(timedelta(hours=8))

class AIConfigWidget(QWidget):
    """AI 模型配置面板"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🤖 AI 模型配置")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        # 配置项
        ai_cfg = self.config.get("ai_model_config", {})
        
        self.base_url_input = self._create_input("Base URL:", ai_cfg.get("base_url", ""))
        layout.addLayout(self.base_url_input[0])
        
        self.api_key_input = self._create_input("API Key:", ai_cfg.get("api_key", ""), is_password=True)
        layout.addLayout(self.api_key_input[0])
        
        self.model_name_input = self._create_input("Model Name:", ai_cfg.get("model_name", "qwen-vl-max"))
        layout.addLayout(self.model_name_input[0])

        layout.addStretch()

        self.save_btn = QPushButton("💾 保存配置")
        self.save_btn.setFixedHeight(36)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {GREEN_ACCENT};
                color: white;
                border-radius: 6px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #8FBF65;
            }}
        """)
        self.save_btn.clicked.connect(self._save_config)
        layout.addWidget(self.save_btn)

    def _create_input(self, label_text, value, is_password=False):
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        
        line_edit = QLineEdit(value)
        if is_password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        
        line_edit.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {BORDER_COLOR};
                border-radius: 6px;
                padding: 8px;
                background: white;
                color: {TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {GREEN_ACCENT};
            }}
        """)
        
        layout.addWidget(label)
        layout.addWidget(line_edit)
        return layout, line_edit

    def _save_config(self):
        if "ai_model_config" not in self.config:
            self.config["ai_model_config"] = {}
            
        self.config["ai_model_config"]["base_url"] = self.base_url_input[1].text()
        self.config["ai_model_config"]["api_key"] = self.api_key_input[1].text()
        self.config["ai_model_config"]["model_name"] = self.model_name_input[1].text()
        
        save_config(self.config)
        QMessageBox.information(self, "成功", "AI 配置已保存！")

class SleepStatisticsWindow(QWidget):
    """睡眠与 AI 统计主窗口"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setFixedSize(800, 600)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dragPos = None
        self.current_date = datetime.now(CST).date()
        
        self._build_ui()
        self.load_data()

    def _build_ui(self):
        # 背景卡片
        self.bg = QFrame(self)
        self.bg.setGeometry(0, 0, 800, 600)
        self.bg.setStyleSheet(f"""
            QFrame {{
                background-color: {BG_LIGHT};
                border: 1px solid {BORDER_COLOR};
                border-radius: 12px;
            }}
        """)
        
        main_layout = QVBoxLayout(self.bg)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ====== 标题栏 ======
        header = QWidget()
        header.setFixedHeight(50)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 15, 0)

        title = QLabel("🌙 睡眠与 AI 统计分析")
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ color: {TEXT_SECONDARY}; font-size: 20px; border: none; background: transparent; }}
            QPushButton:hover {{ color: {RED_ACCENT}; }}
        """)
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)
        main_layout.addWidget(header)

        # ====== 分割线 ======
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {BORDER_COLOR}; max-height: 1px;")
        main_layout.addWidget(line)

        # ====== 内容区 ======
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # --- 左侧: 数据面板 (60%) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(20)

        # 日期切换
        date_layout = QHBoxLayout()
        self.prev_btn = QPushButton("◀")
        self.next_btn = QPushButton("▶")
        for b in (self.prev_btn, self.next_btn):
            b.setFixedSize(30, 30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"QPushButton {{ border: 1px solid {BORDER_COLOR}; border-radius: 15px; color: {TEXT_PRIMARY}; }} QPushButton:hover {{ background: #F0F2F5; }}")
        
        self.date_label = QLabel(self.current_date.strftime("%Y-%m-%d"))
        self.date_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT_PRIMARY};")
        self.date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.prev_btn.clicked.connect(lambda: self.change_date(-1))
        self.next_btn.clicked.connect(lambda: self.change_date(1))
        
        date_layout.addWidget(self.prev_btn)
        date_layout.addWidget(self.date_label, 1)
        date_layout.addWidget(self.next_btn)
        left_layout.addLayout(date_layout)

        # 评分大展示
        self.score_card = QFrame()
        self.score_card.setFixedHeight(120)
        self.score_card.setStyleSheet(f"background: #F8F9FB; border-radius: 10px; border: none;")
        score_layout = QVBoxLayout(self.score_card)
        self.score_val = QLabel("--")
        self.score_val.setStyleSheet("font-size: 48px; font-weight: bold; color: #A3BE8C;")
        self.score_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_desc = QLabel("睡眠评分")
        self.score_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px;")
        self.score_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(self.score_val)
        score_layout.addWidget(self.score_desc)
        left_layout.addWidget(self.score_card)

        # 指标 Grid
        self.grid = QGridLayout()
        self.grid.setSpacing(15)
        self.metrics = {}
        metric_names = [
            ("深睡", "deep_sleep_min", " min"),
            ("浅睡", "light_sleep_min", " min"),
            ("快速眼动", "rem_sleep_min", " min"),
            ("深睡比例", "deep_sleep_ratio", "%")
        ]
        for i, (label, key, unit) in enumerate(metric_names):
            card = self._create_metric_card(label)
            self.grid.addWidget(card, i // 2, i % 2)
            self.metrics[key] = (card.findChild(QLabel, "val"), unit)
        
        left_layout.addLayout(self.grid)
        left_layout.addStretch()

        content_layout.addWidget(left_panel, 6)

        # --- 右侧: AI 与分析 (40%) ---
        right_panel = QWidget()
        right_panel.setStyleSheet(f"background-color: #F8F9FB; border-left: 1px solid {BORDER_COLOR}; border-bottom-right-radius: 12px;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: none; }}
            QTabBar::tab {{
                padding: 10px 20px;
                color: {TEXT_SECONDARY};
                background: transparent;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                color: {GREEN_ACCENT};
                border-bottom: 2px solid {GREEN_ACCENT};
            }}
        """)

        # 分析页
        analysis_page = QWidget()
        analysis_layout = QVBoxLayout(analysis_page)
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlaceholderText("在此展示 AI 睡眠分析报告...")
        self.analysis_text.setStyleSheet(f"border: none; background: transparent; color: {TEXT_PRIMARY}; font-size: 13px;")
        analysis_layout.addWidget(self.analysis_text)
        
        # 服务状态提示
        self.server_status = QLabel("📡 HTTP 服务: 端口 5055\n手机端运行脚本即可自动同步")
        self.server_status.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 10px; background: #F0F2F5; border-radius: 6px;")
        self.server_status.setWordWrap(True)
        analysis_layout.addWidget(self.server_status)

        self.refresh_btn = QPushButton("🔄 刷新数据")
        self.refresh_btn.setFixedHeight(40)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: {GREEN_ACCENT}; color: white; border-radius: 6px; font-weight: bold; }}
            QPushButton:hover {{ background: #8FBF65; }}
        """)
        self.refresh_btn.clicked.connect(self.load_data)
        analysis_layout.addWidget(self.refresh_btn)
        
        self.tabs.addTab(analysis_page, "分析建议")

        # 配置页
        self.config_page = AIConfigWidget(self.config)
        self.tabs.addTab(self.config_page, "AI 配置")

        right_layout.addWidget(self.tabs)
        content_layout.addWidget(right_panel, 4)

        main_layout.addWidget(content)

    def _create_metric_card(self, title):
        card = QFrame()
        card.setStyleSheet(f"background: white; border: 1px solid {BORDER_COLOR}; border-radius: 8px;")
        layout = QVBoxLayout(card)
        l_title = QLabel(title)
        l_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        l_val = QLabel("--")
        l_val.setObjectName("val")
        l_val.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 18px; font-weight: bold;")
        layout.addWidget(l_title)
        layout.addWidget(l_val)
        return card

    def change_date(self, delta):
        self.current_date += timedelta(days=delta)
        self.date_label.setText(self.current_date.strftime("%Y-%m-%d"))
        self.load_data()

    def load_data(self):
        date_str = self.current_date.strftime("%Y-%m-%d")
        data_path = resource_path(os.path.join("document", "skills", "time-management", "huawei_health_data", f"sleep_{date_str}.json"))
        
        if os.path.exists(data_path):
            try:
                with open(data_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._update_ui_with_data(data)
            except Exception as e:
                logger.error(f"加载睡眠数据失败: {e}")
                self._clear_ui()
        else:
            self._clear_ui()

    def _update_ui_with_data(self, data):
        score = data.get("sleep_score", 0)
        self.score_val.setText(str(score))
        if score >= 85: color = GREEN_ACCENT
        elif score >= 70: color = "#81A1C1"
        else: color = RED_ACCENT
        self.score_val.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {color};")

        # 兼容新旧字段名: 旧格式用 deep_sleep (秒), 新格式用 deep_sleep_min (分钟)
        FALLBACKS = {
            "deep_sleep_min": lambda d: d.get("deep_sleep_min") or (d.get("deep_sleep", 0) / 60 if d.get("deep_sleep") else None),
            "light_sleep_min": lambda d: d.get("light_sleep_min") or (d.get("light_sleep", 0) / 60 if d.get("light_sleep") else None),
            "rem_sleep_min": lambda d: d.get("rem_sleep_min") or (d.get("rem_sleep", 0) / 60 if d.get("rem_sleep") else None),
            "deep_sleep_ratio": lambda d: d.get("deep_sleep_ratio"),
        }

        for key, (label, unit) in self.metrics.items():
            val = FALLBACKS.get(key, lambda d: d.get(key))(data)
            if val is None:
                label.setText("--")
            elif isinstance(val, float):
                label.setText(f"{val:.0f}{unit}")
            else:
                label.setText(f"{val}{unit}")

        # 时间显示
        bed = data.get("sleep_start", "")
        wake = data.get("sleep_end", "")
        time_info = ""
        if bed and wake:
            time_info = f"🛏️ {bed} → ⏰ {wake}\n"

        # 分析文本
        analysis = data.get("analysis", {})
        if isinstance(analysis, dict):
            summary = analysis.get("summary", "")
        else:
            summary = str(analysis) if analysis else ""

        self.analysis_text.setText(f"{time_info}{summary}" if (time_info or summary) else "数据已加载，暂无分析文本。")

    def _clear_ui(self):
        self.score_val.setText("--")
        self.score_val.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {TEXT_SECONDARY};")
        for label, unit in self.metrics.values():
            label.setText("--")
        self.analysis_text.setText("该日期暂无睡眠记录文件。")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)
            event.accept()
