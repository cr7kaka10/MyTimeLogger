# -*- coding: utf-8 -*-
import os
import json
import base64
import logging
import traceback
from datetime import datetime, timedelta, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QFrame, QStackedWidget, QGridLayout,
    QLineEdit, QTextEdit, QTabWidget, QGraphicsOpacityEffect,
    QMessageBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QThread
from PyQt6.QtGui import QFont, QColor

from config import save_config
from utils import resource_path

logger = logging.getLogger(__name__)

# ==================== 配色与常量 (同步项目风格) ====================
TEXT_PRIMARY = "#2E3440"
TEXT_SECONDARY = "#4C566A"
BORDER_COLOR = "transparent" # 移除所有边框
CARD_BG = "#F0F2F5" # 使用背景色区分卡片
GREEN_ACCENT = "#A3BE8C"
RED_ACCENT = "#BF616A"
BG_LIGHT = "#FFFFFF"
PANEL_COLOR = "#F8F9FB"
CST = timezone(timedelta(hours=8))

def clean_url(url):
    """自动处理用户填写的 URL，确保其符合 OpenAI SDK 要求（不含 /chat/completions）"""
    url = url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[:-len("/chat/completions")].rstrip("/")
    return url

class AITestWorker(QThread):
    """专门用于测试 API 连通性的线程"""
    finished = pyqtSignal(bool, str)

    def __init__(self, base_url, api_key, model_name, is_vision=False):
        super().__init__()
        self.base_url = clean_url(base_url)
        self.api_key = api_key
        self.model_name = model_name
        self.is_vision = is_vision

    def run(self):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            
            test_content = "hi"
            messages = [{"role": "user", "content": test_content}]
            if self.is_vision:
                # 视觉模型测试：传一个极小的透明像素 base64 以验证视觉能力
                pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
                messages[0]["content"] = [
                    {"type": "text", "text": "hi"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{pixel}"}}
                ]
            
            client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                max_tokens=5
            )
            self.finished.emit(True, "连接成功！响应正常。")
        except Exception as e:
            self.finished.emit(False, f"连接失败: {str(e)}")


class AIWorker(QThread):
    """AI 分析工作线程，支持分离的视觉与文本模型配置"""
    finished = pyqtSignal(str, dict)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, ai_cfg, image_path=None, sleep_data=None):
        super().__init__()
        self.ai_cfg = ai_cfg
        self.image_path = image_path
        self.sleep_data = sleep_data

    def run(self):
        try:
            from openai import OpenAI
            import time
            
            # ── 步骤 1: 视觉解析 ──
            if self.image_path and os.path.exists(self.image_path):
                self.progress.emit("📸 正在进行 4K 级高清采样...")
                v_url = clean_url(self.ai_cfg.get("vision_base_url", ""))
                v_key = self.ai_cfg.get("vision_api_key", "")
                v_model = self.ai_cfg.get("vision_model", "glm-4v-flash")
                
                if not v_key:
                    self.error.emit("⚠️ 未配置「视觉 API Key」，无法解析截图。")
                    return
                
                client_v = OpenAI(api_key=v_key, base_url=v_url)
                
                # 图片预处理
                final_img_path = self.image_path
                temp_img_path = None
                try:
                    from PIL import Image
                    with Image.open(self.image_path) as img:
                        w, h = img.size
                        if h > 2000:
                            new_h = 4096 if h > 4096 else h
                            new_w = int(w * (new_h / h))
                            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                            temp_img_path = self.image_path + ".hd.jpg"
                            img.convert("RGB").save(temp_img_path, "JPEG", quality=95)
                            final_img_path = temp_img_path
                except Exception as img_err:
                    logger.warning(f"图片预处理失败: {img_err}")

                with open(final_img_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                
                if temp_img_path and os.path.exists(temp_img_path):
                    try: os.remove(temp_img_path)
                    except: pass

                ext = os.path.splitext(final_img_path)[1].lower().lstrip(".")
                mime = "image/jpeg" if ext in ("jpg", "jpeg", "hd.jpg") else f"image/{ext}"

                prompt = """提取以下字段并以 JSON 返回：
sleep_date (截图中的日期, 格式如 M月D日),
sleep_score (睡眠得分, 整数), 
sleep_start (入睡时间, HH:mm), 
sleep_end (醒来时间, HH:mm), 
total_sleep_min (总睡眠时长, 分钟), 
deep_sleep_min (深睡时长, 分钟), 
light_sleep_min (浅睡时长, 分钟), 
rem_sleep_min (快速眼动时长, 分钟), 
deep_sleep_ratio (深睡比例, 整数,不带%),
awake_count (清醒次数, 整数),
sleep_continuity (睡眠连续性得分, 整数),
breathing_score (呼吸质量评分, 整数),
official_interpretation (截图底部的官方解读与建议原文, 字符串).
注意：只返回 JSON 代码块。"""

                # 视觉重试机制
                max_retries = 3
                raw = ""
                for attempt in range(max_retries):
                    try:
                        self.progress.emit(f"📸 视觉模型解析中 (第 {attempt+1} 次尝试)...")
                        vision_resp = client_v.chat.completions.create(
                            model=v_model,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                                    {"type": "text", "text": prompt}
                                ]
                            }],
                            max_tokens=1024,
                            temperature=0.1
                        )
                        raw = vision_resp.choices[0].message.content.strip()
                        if raw: break
                    except Exception as ve:
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue
                        raise ve

                if "```" in raw:
                    raw = raw.split("```")[1].replace("json", "").strip()
                
                if not raw or raw == "{}":
                    self.error.emit("❌ 视觉模型未能提取到任何有效数据。")
                    return

                try:
                    self.sleep_data = json.loads(raw)
                    if self.sleep_data.get("sleep_score") or self.sleep_data.get("total_sleep_min"):
                        self.progress.emit("✅ 截图数据提取成功")
                    else:
                        raise ValueError("Data incomplete")
                except:
                    self.sleep_data = {"raw_ocr": raw}
                    self.progress.emit("⚠️ 提取到非标准数据，尝试智能匹配...")

            # ── 步骤 2: 生成完整时间管理报告 ──
            self.progress.emit("🌐 正在拉取 aTimeLogger 数据并生成综合报告...")
            
            # 解析日期
            sleep_date = self.sleep_data.get("sleep_date", "")
            # 处理日期格式，例如 "5月9日" -> "2026-05-09"
            target_date = datetime.now().strftime("%Y-%m-%d")
            import re
            match = re.search(r"(\d+)月(\d+)日", sleep_date)
            if match:
                month, day = match.groups()
                target_date = f"{datetime.now().year}-{int(month):02d}-{int(day):02d}"
            
            # 将生成的完整报告写入 UI 的 analysis.summary 字段中
            self.sleep_data['date'] = target_date
            
            # 引入 generate_full_report 模块
            import sys
            skill_dir = os.path.join(os.path.dirname(__file__), "document", "skills", "time-management")
            if skill_dir not in sys.path:
                sys.path.insert(0, skill_dir)
            from generate_full_report import generate_comprehensive_report
            
            # 直接调用并注入睡眠数据
            report_path = generate_comprehensive_report(target_date, injected_sleep_data=self.sleep_data)
            
            if report_path and os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report = f.read()
            else:
                report = "生成报告失败，请检查终端日志。"
                self.error.emit(report)
                return
                
            self.finished.emit(report, self.sleep_data)

        except Exception as e:
            self.error.emit(f"❌ 分析失败：{e}")


class AIConfigWidget(QWidget):
    """AI 分离配置面板"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._test_worker = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)

        # 视觉部分
        v_group, v_test_btn = self._create_group("📸 1. 视觉模型 (用于识别截图)", "用于将睡眠详情图片解析为结构化数字。")
        v_layout = v_group.layout()
        ai_cfg = self.config.get("ai_model_config", {})
        
        self.v_url = self._make_field("API 地址 (Base URL):", ai_cfg.get("vision_base_url", "https://open.bigmodel.cn/api/paas/v4"), v_layout)
        self.v_key = self._make_field("API Key:", ai_cfg.get("vision_api_key", ""), v_layout, is_password=True)
        self.v_model = self._make_field("模型名称 (Model Name):", ai_cfg.get("vision_model", "glm-4v-flash"), v_layout)
        v_test_btn.clicked.connect(lambda: self._test_connection(True))
        layout.addWidget(v_group)

        # 文本部分
        t_group, t_test_btn = self._create_group("🧠 2. 文本模型 (用于生成报告)", "用于根据识别出的数字生成深度的文字分析建议。")
        t_layout = t_group.layout()
        self.t_url = self._make_field("API 地址 (Base URL):", ai_cfg.get("text_base_url", "https://open.bigmodel.cn/api/paas/v4"), t_layout)
        self.t_key = self._make_field("API Key:", ai_cfg.get("text_api_key", ""), t_layout, is_password=True)
        self.t_model = self._make_field("模型名称 (Model Name):", ai_cfg.get("text_model", "glm-4-flash"), t_layout)
        t_test_btn.clicked.connect(lambda: self._test_connection(False))
        layout.addWidget(t_group)

        self.save_btn = QPushButton("💾 保存全部配置")
        self.save_btn.setFixedHeight(38)
        self.save_btn.setStyleSheet(f"background: {GREEN_ACCENT}; color: white; border-radius: 6px; font-weight: bold;")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_config)
        layout.addWidget(self.save_btn)
        layout.addStretch()

    def _create_group(self, title, desc):
        group = QFrame()
        group.setStyleSheet(f"QFrame {{ background: white; border: 1px solid {BORDER_COLOR}; border-radius: 10px; }}")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(10)
        
        header = QHBoxLayout()
        t_lbl = QLabel(title)
        t_lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 14px; font-weight: bold; border: none;")
        test_btn = QPushButton("🧪 测试连接")
        test_btn.setFixedSize(70, 22)
        test_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        test_btn.setStyleSheet(f"QPushButton {{ background: #F0F2F5; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_COLOR}; border-radius: 4px; font-size: 10px; }} QPushButton:hover {{ background: #E5E9F0; }}")
        header.addWidget(t_lbl)
        header.addStretch()
        header.addWidget(test_btn)
        layout.addLayout(header)

        d_lbl = QLabel(desc)
        d_lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px; border: none;")
        layout.addWidget(d_lbl)
        return group, test_btn

    def _make_field(self, label_text, value, parent_layout, is_password=False):
        row = QHBoxLayout()
        row.setSpacing(10)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(120)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; border: none;")
        edit = QLineEdit(value)
        if is_password: edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setStyleSheet(f"QLineEdit {{ border: 1px solid {BORDER_COLOR}; border-radius: 4px; padding: 5px; font-size: 12px; }}")
        row.addWidget(lbl)
        row.addWidget(edit)
        parent_layout.addLayout(row)
        return edit

    def _test_connection(self, is_vision):
        if self._test_worker and self._test_worker.isRunning(): return
        
        url = self.v_url.text() if is_vision else self.t_url.text()
        key = self.v_key.text() if is_vision else self.t_key.text()
        model = self.v_model.text() if is_vision else self.t_model.text()
        
        if not key.strip():
            QMessageBox.warning(self, "错误", "请先填写 API Key")
            return
            
        self._test_worker = AITestWorker(url, key, model, is_vision)
        self._test_worker.finished.connect(self._on_test_finished)
        self._test_worker.start()
        # 按钮状态提示
        sender = self.sender()
        if sender: 
            sender.setEnabled(False)
            sender.setText("测试中...")
            self._last_test_btn = sender

    def _on_test_finished(self, success, msg):
        if hasattr(self, "_last_test_btn"):
            self._last_test_btn.setEnabled(True)
            self._last_test_btn.setText("🧪 测试连接")
        
        if success:
            QMessageBox.information(self, "连接测试", msg)
        else:
            QMessageBox.critical(self, "连接测试", msg)

    def _save_config(self):
        c = self.config.setdefault("ai_model_config", {})
        c["vision_base_url"] = self.v_url.text().strip()
        c["vision_api_key"]  = self.v_key.text().strip()
        c["vision_model"]    = self.v_model.text().strip()
        c["text_base_url"]   = self.t_url.text().strip()
        c["text_api_key"]    = self.t_key.text().strip()
        c["text_model"]      = self.t_model.text().strip()
        save_config(self.config)
        QMessageBox.information(self, "成功", "AI 配置已分流保存！")


class SleepStatisticsWindow(QWidget):
    """睡眠与 AI 统计主窗口"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.resize(800, 600)
        self.setMinimumSize(800, 600)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.dragPos = None
        self.current_date = datetime.now(CST).date()
        self._selected_image = None   # 用户选择的截图路径
        self._ai_worker = None        # AIWorker 线程引用
        self._current_sleep_data = None  # 当前加载的 JSON 数据

        self._build_ui()
        self.load_data()

    def _build_ui(self):
        # 允许内部框架自适应
        wrapper_layout = QVBoxLayout(self)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        
        # 背景卡片
        self.bg = QFrame(self)
        wrapper_layout.addWidget(self.bg)
        
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

        max_btn = QPushButton("□")
        max_btn.setFixedSize(30, 30)
        max_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        max_btn.setStyleSheet(f"""
            QPushButton {{ color: {TEXT_SECONDARY}; font-size: 16px; border: none; background: transparent; }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; }}
        """)
        def toggle_maximize():
            if self.isMaximized():
                self.showNormal()
                max_btn.setText("□")
            else:
                self.showMaximized()
                max_btn.setText("❐")
        max_btn.clicked.connect(toggle_maximize)
        header_layout.addWidget(max_btn)

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
        self.date_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT_PRIMARY}; background: transparent; border: none;")
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
        self.score_card.setStyleSheet(f"background: {PANEL_COLOR}; border-radius: 12px; border: none;")
        score_layout = QVBoxLayout(self.score_card)
        self.score_val = QLabel("--")
        self.score_val.setStyleSheet("font-size: 48px; font-weight: bold; color: #81A1C1;")
        self.score_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.score_desc = QLabel("睡眠评分")
        self.score_desc.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 14px; font-weight: 500;")
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
            ("清醒时长", "awake_duration", " min"), # 计算项
            ("深睡比例", "deep_sleep_ratio", "%"),
            ("清醒次数", "awake_count", " 次"),
            ("睡眠连续性", "sleep_continuity", " 分"),
            ("呼吸质量", "breathing_score", " 分")
        ]
        for i, (label, key, unit) in enumerate(metric_names):
            card = self._create_metric_card(label)
            # 使用 2x4 布局 (i // 4 行, i % 4 列)
            self.grid.addWidget(card, i // 4, i % 4)
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
        analysis_layout.setSpacing(8)
        analysis_layout.setContentsMargins(12, 12, 12, 12)

        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlaceholderText("点击下方按钮进行 AI 分析...")
        self.analysis_text.setStyleSheet(
            f"border: none; background: transparent; color: {TEXT_PRIMARY}; font-size: 13px; line-height: 1.6;"
        )
        analysis_layout.addWidget(self.analysis_text)

        # 截图路径显示
        self.img_path_label = QLabel("未选择截图")
        self.img_path_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none; padding: 2px;")
        self.img_path_label.setWordWrap(True)
        analysis_layout.addWidget(self.img_path_label)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.pick_img_btn = QPushButton("📂 选择截图")
        self.pick_img_btn.setFixedHeight(36)
        self.pick_img_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pick_img_btn.setStyleSheet(f"""
            QPushButton {{ background: #81A1C1; color: white; border-radius: 6px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background: #6A8FAF; }}
        """)
        self.pick_img_btn.clicked.connect(self._pick_image)
        btn_row.addWidget(self.pick_img_btn)

        self.ai_btn = QPushButton("🚀 AI 分析")
        self.ai_btn.setFixedHeight(36)
        self.ai_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ai_btn.setStyleSheet(f"""
            QPushButton {{ background: {GREEN_ACCENT}; color: white; border-radius: 6px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background: #8FBF65; }}
        """)
        self.ai_btn.clicked.connect(self._run_ai_analysis)
        btn_row.addWidget(self.ai_btn)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setFixedHeight(36)
        self.refresh_btn.setFixedWidth(60)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: #D8DEE9; color: {TEXT_PRIMARY}; border-radius: 6px; font-size: 12px; }}
            QPushButton:hover {{ background: #C4CDD9; }}
        """)
        self.refresh_btn.clicked.connect(self.load_data)
        btn_row.addWidget(self.refresh_btn)

        analysis_layout.addLayout(btn_row)
        self.tabs.addTab(analysis_page, "分析建议")

        # 配置页
        self.config_page = AIConfigWidget(self.config)
        self.tabs.addTab(self.config_page, "AI 配置")

        right_layout.addWidget(self.tabs)
        content_layout.addWidget(right_panel, 4)

        main_layout.addWidget(content)

    def _create_metric_card(self, title):
        card = QFrame()
        card.setStyleSheet(f"background: {CARD_BG}; border: none; border-radius: 10px;")
        layout = QVBoxLayout(card)
        l_title = QLabel(title)
        l_title.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
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

        # --- 智能计算：清醒时长 ---
        # 醒来时间 - 入睡时间 - 实际睡眠总时长
        try:
            start_str = data.get("sleep_start")
            end_str = data.get("sleep_end")
            total_sleep = data.get("total_sleep_min")
            
            if start_str and end_str and total_sleep:
                fmt = "%H:%M"
                t_start = datetime.strptime(start_str, fmt)
                t_end = datetime.strptime(end_str, fmt)
                if t_end < t_start: t_end += timedelta(days=1)
                in_bed_min = int((t_end - t_start).total_seconds() / 60)
                awake_min = max(0, in_bed_min - int(total_sleep))
                data["awake_duration"] = awake_min
        except Exception as e:
            logger.warning(f"清醒时长计算失败: {e}")

        # 兼容新旧字段名
        FALLBACKS = {
            "deep_sleep_min": lambda d: d.get("deep_sleep_min") or (d.get("deep_sleep", 0) / 60 if d.get("deep_sleep") else None),
            "light_sleep_min": lambda d: d.get("light_sleep_min") or (d.get("light_sleep", 0) / 60 if d.get("light_sleep") else None),
            "rem_sleep_min": lambda d: d.get("rem_sleep_min") or (d.get("rem_sleep", 0) / 60 if d.get("rem_sleep") else None),
        }

        for key, (label, unit) in self.metrics.items():
            val = FALLBACKS.get(key, lambda d: d.get(key))(data)
            if val is None:
                label.setText("--")
            elif isinstance(val, (int, float)):
                label.setText(f"{val:.0f}{unit}")
            else:
                label.setText(f"{val}{unit}")

        # 时间显示
        bed = data.get("sleep_start", "")
        wake = data.get("sleep_end", "")
        if bed and wake:
            self.img_path_label.setText(f"🛏️ {bed} → ⏰ {wake}")
        
        # 分析报告 Markdown 渲染
        analysis = data.get("analysis", {})
        report = ""
        if isinstance(analysis, dict):
            report = analysis.get("summary", "")
        else:
            report = str(analysis) if analysis else ""
        
        if report:
            self.analysis_text.setMarkdown(report)
        else:
            self.analysis_text.setText("数据已加载，点击《🚀 AI 分析》生成智能报告。")
            
        self._current_sleep_data = data  # 缓存当前数据供 AI 使用

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

    def _pick_image(self):
        """打开文件选择器选择截图"""
        from PyQt6.QtCore import QSettings
        settings = QSettings("MyTimeLogger", "SleepAnalysis")
        last_dir = settings.value("last_image_dir", os.path.expanduser("~"))
        
        path, _ = QFileDialog.getOpenFileName(
            self, "选择华为运动健康睡眠截图",
            last_dir,
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            settings.setValue("last_image_dir", os.path.dirname(path))
            self._selected_image = path
            fname = os.path.basename(path)
            self.img_path_label.setText(f"✅ 已选择: {fname}")

    def _run_ai_analysis(self):
        """启动 AI 分析线程"""
        if self._ai_worker and self._ai_worker.isRunning():
            return

        ai_cfg = self.config.get("ai_model_config", {})
        v_key = ai_cfg.get("vision_api_key", "").strip()
        t_key = ai_cfg.get("text_api_key", "").strip()
        
        if not v_key or not t_key:
            QMessageBox.warning(self, "请先配置", "请确保「AI 配置」页的「视觉」和「文本」API Key 均已填写。")
            self.tabs.setCurrentIndex(1)
            return

        # 准备的数据：截图或已加载的 JSON
        has_image = self._selected_image and os.path.exists(self._selected_image)
        has_data  = bool(self._current_sleep_data)
        if not has_image and not has_data:
            QMessageBox.information(self, "无数据", "请先选择截图，或切换日期使 JSON 数据加载。")
            return

        self.ai_btn.setEnabled(False)
        self.ai_btn.setText("⏳ 分析中...")
        self.analysis_text.setPlaceholderText("")
        self.analysis_text.setText("🔄 开始分析，请稍候...")

        self._ai_worker = AIWorker(
            ai_cfg=ai_cfg,
            image_path=self._selected_image if has_image else None,
            sleep_data=None if has_image else self._current_sleep_data
        )
        self._ai_worker.progress.connect(lambda msg: self.analysis_text.append(f"\n{msg}"))
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_finished(self, report, sleep_data):
        """AI 分析完成：智能识别日期、自动归档并渲染"""
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("🚀 AI 分析")
        
        if not sleep_data: return
        
        # 1. 智能识别日期逻辑
        target_date = self.current_date
        date_str_extracted = sleep_data.get("sleep_date") # 例如 "5月8日"
        if date_str_extracted:
            try:
                # 尝试解析 M月D日，年份默认为当前 UI 年份
                current_year = self.current_date.year
                clean_date = date_str_extracted.replace("月", "-").replace("日", "")
                parsed_date = datetime.strptime(f"{current_year}-{clean_date}", "%Y-%m-%d")
                
                # 如果解析出的日期和当前 UI 日期不符，更新 target_date 并提醒
                if parsed_date.date() != self.current_date:
                    target_date = parsed_date
                    self.current_date = parsed_date
                    self.date_label.setText(self.current_date.strftime("%Y-%m-%d"))
                    logger.info(f"检测到截图日期为 {date_str_extracted}，已自动切换日期。")
            except Exception as de:
                logger.warning(f"日期解析失败 ({date_str_extracted}): {de}")

        # 2. 将报告存入数据对象
        sleep_data["analysis"] = {"summary": report}
        self._current_sleep_data = sleep_data
        
        # 3. 自动保存到对应的日期文件
        try:
            save_date_str = target_date.strftime("%Y-%m-%d")
            save_dir = resource_path(os.path.join("document", "skills", "time-management", "huawei_health_data"))
            os.makedirs(save_dir, exist_ok=True)
            data_path = os.path.join(save_dir, f"sleep_{save_date_str}.json")
            
            with open(data_path, 'w', encoding='utf-8') as f:
                json.dump(sleep_data, f, ensure_ascii=False, indent=2)
            logger.info(f"睡眠数据已保存至: {data_path}")
        except Exception as e:
            logger.error(f"保存睡眠数据失败: {e}")

        # 4. 刷新 UI 指标并渲染 Markdown 报告
        self._update_ui_with_data(sleep_data)
        self.analysis_text.setMarkdown(report) # 使用 Markdown 渲染
        self.analysis_text.setStyleSheet(f"border: none; background: transparent; color: {TEXT_PRIMARY}; font-size: 13px; line-height: 1.5;")

    def _on_ai_error(self, msg):
        self.analysis_text.setText(msg)
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("🚀 AI 分析")
