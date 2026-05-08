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
BORDER_COLOR = "#D8DEE9"
GREEN_ACCENT = "#A3BE8C"
RED_ACCENT = "#BF616A"
BG_LIGHT = "#FFFFFF"
CST = timezone(timedelta(hours=8))

class AIWorker(QThread):
    """AI 分析工作线程，避免 UI 卡顿"""
    finished = pyqtSignal(str)    # 成功：返回分析文本
    error = pyqtSignal(str)       # 失败：返回错误信息
    progress = pyqtSignal(str)    # 进度：中间状态提示

    def __init__(self, ai_cfg, image_path=None, sleep_data=None):
        super().__init__()
        self.ai_cfg = ai_cfg
        self.image_path = image_path    # 截图路径（可选）
        self.sleep_data = sleep_data    # JSON 数据（可选）

    def run(self):
        try:
            from openai import OpenAI
            base_url = self.ai_cfg.get("base_url", "").rstrip("/")
            api_key  = self.ai_cfg.get("api_key", "")
            if not api_key:
                self.error.emit("⚠️ 未配置 API Key，请先在「AI 配置」页填写。")
                return

            client = OpenAI(api_key=api_key, base_url=base_url)

            # ── 步骤 1: 若有截图，用视觉模型解析 ──
            if self.image_path and os.path.exists(self.image_path):
                self.progress.emit("📸 正在用视觉模型解析截图...")
                with open(self.image_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                ext = os.path.splitext(self.image_path)[1].lower().lstrip(".")
                mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

                vision_model = self.ai_cfg.get("vision_model", "glm-4.6v-flash")
                vision_resp = client.chat.completions.create(
                    model=vision_model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{img_b64}"}
                            },
                            {
                                "type": "text",
                                "text": (
                                    "这是华为健康APP的睡眠详情截图，请精确提取以下字段并以JSON格式返回（只返回JSON，不要多余文字）：\n"
                                    "sleep_score（睡眠评分，整数）, sleep_start（入睡时间，如22:30）, "
                                    "sleep_end（起床时间，如07:00）, total_sleep_min（总睡眠分钟数）, "
                                    "deep_sleep_min（深睡分钟数）, light_sleep_min（浅睡分钟数）, "
                                    "rem_sleep_min（快速眼动分钟数）, deep_sleep_ratio（深睡占比%，纯数字）。"
                                    "若截图中某字段不存在，对应值填 null。"
                                )
                            }
                        ]
                    }],
                    max_tokens=512,
                    temperature=0.1
                )
                raw = vision_resp.choices[0].message.content.strip()
                # 提取 JSON 块
                if "```" in raw:
                    raw = raw.split("```")[1].lstrip("json").strip()
                try:
                    self.sleep_data = json.loads(raw)
                    self.progress.emit("✅ 截图解析完成，正在生成分析报告...")
                except json.JSONDecodeError:
                    self.progress.emit(f"⚠️ 视觉模型返回格式异常，已尝试继续...\n原始内容: {raw[:200]}")
                    self.sleep_data = {"raw_ocr": raw}

            # ── 步骤 2: 用文本模型生成分析报告 ──
            if not self.sleep_data:
                self.error.emit("❌ 没有可分析的睡眠数据，请先提供截图或加载 JSON。")
                return

            self.progress.emit("🧠 正在生成深度分析报告（启用深度思考）...")
            text_model = self.ai_cfg.get("text_model", "glm-4.7-flash")
            data_str = json.dumps(self.sleep_data, ensure_ascii=False, indent=2)
            text_resp = client.chat.completions.create(
                model=text_model,
                messages=[{
                    "role": "system",
                    "content": (
                        "你是一位专业的睡眠健康顾问，请根据用户的睡眠数据给出简洁有深度的分析报告。"
                        "报告包含：①整体评价（2句话）②关键亮点（深睡/REM情况）③改进建议（1~2条具体可行的建议）。"
                        "语气亲切，用中文，总字数控制在200字以内。"
                    )
                }, {
                    "role": "user",
                    "content": f"我的睡眠数据如下：\n{data_str}\n请给出分析。"
                }],
                extra_body={"thinking": {"type": "enabled"}},
                max_tokens=1024,
                temperature=0.7
            )
            report = text_resp.choices[0].message.content.strip()
            self.finished.emit(report)

        except ImportError:
            self.error.emit("❌ 缺少 openai 库，请运行：pip install openai")
        except Exception as e:
            logger.error(traceback.format_exc())
            self.error.emit(f"❌ 分析失败：{e}")


class AIConfigWidget(QWidget):
    """AI 模型配置面板（智谱双模型）"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("🤖 AI 模型配置（智谱 GLM）")
        title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        tip = QLabel("Base URL: https://open.bigmodel.cn/api/paas/v4")
        tip.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        tip.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(tip)

        ai_cfg = self.config.get("ai_model_config", {})

        self.base_url_input = self._make_field("Base URL:", ai_cfg.get("base_url", "https://open.bigmodel.cn/api/paas/v4"))
        layout.addLayout(self.base_url_input[0])

        self.api_key_input = self._make_field("API Key:", ai_cfg.get("api_key", ""), is_password=True)
        layout.addLayout(self.api_key_input[0])

        self.vision_model_input = self._make_field("视觉模型（截图解析）:", ai_cfg.get("vision_model", "glm-4.6v-flash"))
        layout.addLayout(self.vision_model_input[0])

        self.text_model_input = self._make_field("文本模型（报告生成）:", ai_cfg.get("text_model", "glm-4.7-flash"))
        layout.addLayout(self.text_model_input[0])

        layout.addStretch()

        self.save_btn = QPushButton("💾 保存配置")
        self.save_btn.setFixedHeight(36)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {GREEN_ACCENT}; color: white; border-radius: 6px; font-weight: bold; }}
            QPushButton:hover {{ background-color: #8FBF65; }}
        """)
        self.save_btn.clicked.connect(self._save_config)
        layout.addWidget(self.save_btn)

    def _make_field(self, label_text, value, is_password=False):
        layout = QVBoxLayout()
        layout.setSpacing(4)
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        line_edit = QLineEdit(value)
        if is_password:
            line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        line_edit.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {BORDER_COLOR}; border-radius: 6px;
                padding: 7px; background: white; color: {TEXT_PRIMARY};
            }}
            QLineEdit:focus {{ border-color: {GREEN_ACCENT}; }}
        """)
        layout.addWidget(label)
        layout.addWidget(line_edit)
        return layout, line_edit

    def _save_config(self):
        if "ai_model_config" not in self.config:
            self.config["ai_model_config"] = {}
        c = self.config["ai_model_config"]
        c["base_url"]      = self.base_url_input[1].text().strip()
        c["api_key"]       = self.api_key_input[1].text().strip()
        c["vision_model"]  = self.vision_model_input[1].text().strip()
        c["text_model"]    = self.text_model_input[1].text().strip()
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
        self.img_path_label = QLabel("未选择截图（也可直接分析已加载的 JSON 数据）")
        self.img_path_label.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
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

        self.analysis_text.setText(f"{time_info}{summary}" if (time_info or summary) else "数据已加载，点击《🚀 AI 分析》生成智能报告。")
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
        path, _ = QFileDialog.getOpenFileName(
            self, "选择半华健康睡眠截图",
            os.path.expanduser("~"),
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if path:
            self._selected_image = path
            fname = os.path.basename(path)
            self.img_path_label.setText(f"✅ 已选择: {fname}")

    def _run_ai_analysis(self):
        """启动 AI 分析线程"""
        # 防止重复启动
        if self._ai_worker and self._ai_worker.isRunning():
            return

        ai_cfg = self.config.get("ai_model_config", {})
        if not ai_cfg.get("api_key", "").strip():
            QMessageBox.warning(self, "请先配置", "请先在「AI 配置」页填写 API Key。")
            self.tabs.setCurrentIndex(1)  # 切换到配置页
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

    def _on_ai_finished(self, report):
        self.analysis_text.setText(report)
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("🚀 AI 分析")

    def _on_ai_error(self, msg):
        self.analysis_text.setText(msg)
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("🚀 AI 分析")
