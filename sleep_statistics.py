# -*- coding: utf-8 -*-
import os
import json
import base64
import logging
import shutil
import traceback
import time
import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QCalendarWidget, QDateEdit, QDateTimeEdit, QDialog, QFrame, QGridLayout,
    QLineEdit, QTextEdit, QTabWidget, QGraphicsOpacityEffect,
    QMessageBox, QFileDialog, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QThread, QRectF, QPointF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QPainterPath
import re

# ==================== 通用工具函数 ====================
def to_min(val):
    """将各种格式的时间字符串或数值转换为分钟数"""
    if val is None or val == "": return 0
    if isinstance(val, (int, float)): return val
    s = str(val).lower()
    # 处理 "1小时20分", "1h 20m" 等
    h_match = re.search(r'(\d+)\s*(?:h|小时|时)', s)
    m_match = re.search(r'(\d+)\s*(?:m|分钟|分)', s)
    total = 0
    if h_match: total += int(h_match.group(1)) * 60
    if m_match: total += int(m_match.group(1))
    if total > 0: return total
    # 纯数字字符串 (处理 "80min", "约25" 等)
    try: 
        clean_s = re.sub(r'[^\d.]', '', s)
        if not clean_s: return 0
        # 统一转为 int，如果是 "80.5" 这种带点的字符串则先转 float 再转 int
        return int(float(clean_s))
    except: return 0

def clean_num(val):
    """提取字符串中的数字"""
    if val is None or val == "": return 0
    if isinstance(val, (int, float)): return val
    try: 
        clean_s = re.sub(r'[^\d.]', '', str(val))
        if not clean_s: return 0
        val = float(clean_s)
        return int(val) if val == int(val) else val
    except: return 0

def format_val(v):
    """格式化数值显示，去除多余的 .0"""
    if v is None: return ""
    try:
        fv = float(v)
        if fv == int(fv): return str(int(fv))
        return f"{fv:.1f}"
    except: return str(v)

from config import save_config
from utils import resource_path
from database import StudyLogger

logger = logging.getLogger(__name__)
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))

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
    if not url or not isinstance(url, str): return ""
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
            import httpx
            # 自定义 httpx 客户端：放宽 SSL 并增加超时
            http_client = httpx.Client(verify=False, timeout=httpx.Timeout(30.0, connect=10.0))
            client = OpenAI(api_key=self.api_key, base_url=self.base_url, http_client=http_client)
            
            test_content = "hi"
            messages = [{"role": "user", "content": test_content}]
            if self.is_vision:
                # 视觉模型测试：传一个 64x64 的黑色块图片，以验证视觉能力（解决 1x1 像素过小导致某些模型报错的问题）
                pixel = "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABmJLR0QA/wD/AP+gvaeTAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH5gYKEi8yN9iXFAAAACpJREFUeNrtwTEBAAAAwiD7p14HbAAAAAAAAAAAAAAAAAAAAAAAAAAAALgB9VAAAT67988AAAAASUVORK5CYII="
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

    def __init__(self, ai_cfg, image_path=None, sleep_data=None, force_pull=False, date_str=None, session_id=None, include_time_analysis=True, db=None):
        super().__init__()
        self.db = db
        self.ai_cfg = ai_cfg
        self.image_path = image_path
        self.sleep_data = sleep_data
        self.force_pull = force_pull
        self.date_str = date_str
        self.session_id = session_id # 用于 SSE 推送
        self.include_time_analysis = include_time_analysis

    def update_progress(self, msg):
        """同时更新本地 UI 和 Web 推送"""
        self.progress.emit(msg)
        if self.session_id:
            try:
                from sleep_server import broker
                broker.push(self.session_id, {"status": "progress", "msg": msg})
            except: pass

    @staticmethod
    def validate_data(data):
        """校验华为睡眠数据完整性 (仅校验 AI 提取的原始数据)"""
        # 核心原始指标：评分、深睡、深睡比例、入睡/醒来时刻、总时长
        # 注意：sleep_cycles, awake_min, fall_asleep_min, wake_up_min 是后续计算出来的，不在此校验
        required = ["sleep_score", "deep_sleep_min", "deep_sleep_ratio", "sleep_start", "sleep_end", "total_sleep_min"]
        missing = []
        for key in required:
            val = data.get(key)
            # 允许 0，但不允许 None 或空字符串
            if val is None or val == "":
                missing.append(key)
        
        if missing:
            msg = f"缺失核心原始指标: {', '.join(missing)}"
            print(f"  [校验失败] {msg}")
            return False, msg
            
        # ====== 核心数学校验 (v6.2) ======
        try:
            total = to_min(data.get("total_sleep_min", 0))
            deep = to_min(data.get("deep_sleep_min", 0))
            light = to_min(data.get("light_sleep_min", 0))
            rem = to_min(data.get("rem_sleep_min", 0))
            
            # 数学恒等式：总时长 = 深睡 + 浅睡 + REM (必须绝对相等)
            sum_stages = deep + light + rem
            if total != sum_stages:
                msg = f"数学校验失败: 总时长({total}) != 阶段之和({sum_stages}) [深{deep}+浅{light}+REM{rem}]"
                print(f"  [校验失败] {msg}")
                return False, msg
            print(f"  [校验通过] 数学逻辑自洽: {total} == {sum_stages}")
        except Exception as e:
            print(f"  [校验跳过] 数学检查异常: {e}")
            
        return True, ""

        # 检查额外指标是否大部分提取成功 (允许部分缺失但不能全是0)
        extra = ["light_sleep_min", "rem_sleep_min", "awake_count", "sleep_continuity", "breathing_score"]
        extracted_count = sum(1 for k in extra if data.get(k) and data.get(k) > 0)
        if extracted_count < 1:
            print(f"  [校验失败] 补充指标全部缺失")
            return False
        return True

    def normalize_data(self, data):
        """对 AI 返回的原始数据进行‘填坑’和归一化处理"""
        if not data or not isinstance(data, dict): return data
        
        # 时长类字段

        # 时长类字段
        time_fields = [
            "deep_sleep_min", "light_sleep_min", "rem_sleep_min", 
            "awake_min", "fall_asleep_min", "wake_up_min", "total_sleep_min"
        ]
        for f in time_fields:
            if f in data: data[f] = to_min(data[f])
            
        # 纯数字类字段
        num_fields = [
            "sleep_score", "sleep_cycles", "awake_count", 
            "deep_sleep_ratio", "light_sleep_ratio", "rem_sleep_ratio", 
            "sleep_continuity", "breathing_score"
        ]
        for f in num_fields:
            if f in data: data[f] = clean_num(data[f])
            
        # 自动补算缺失的比例
        t = data.get("total_sleep_min", 0)
        if t and t > 0:
            if data.get("deep_sleep_ratio") is None and data.get("deep_sleep_min") is not None:
                data["deep_sleep_ratio"] = round(to_min(data["deep_sleep_min"]) / t * 100)
            if data.get("light_sleep_ratio") is None and data.get("light_sleep_min") is not None:
                data["light_sleep_ratio"] = round(to_min(data["light_sleep_min"]) / t * 100)
            if data.get("rem_sleep_ratio") is None and data.get("rem_sleep_min") is not None:
                data["rem_sleep_ratio"] = round(to_min(data["rem_sleep_min"]) / t * 100)
                
        return data

    def run(self):
        try:
            from sleep_analyzer import SleepAnalyzer

            analyzer = SleepAnalyzer(
                ai_cfg=self.ai_cfg,
                image_path=self.image_path,
                sleep_data=self.sleep_data,
                date_str=self.date_str,
                include_time_analysis=self.include_time_analysis,
                db=self.db,
                progress_callback=self.update_progress,
            )
            result = analyzer.analyze()
            if result.status != "done":
                raise Exception(result.error or "分析失败")

            self.sleep_data = result.sleep_data
            report = result.analysis_report
            
            if self.session_id:
                try:
                    from sleep_server import broker
                    broker.push(self.session_id, {
                        "status": "done",
                        "result": self.sleep_data
                    })
                except: pass

            self.finished.emit(report, self.sleep_data)

        except Exception as e:
            logger.error(f"AIWorker Error: {e}")
            if self.session_id:
                try:
                    from sleep_server import broker
                    broker.push(self.session_id, {"status": "error", "msg": f"❌ 错误: {str(e)}"})
                except: pass
            self.error.emit(f"❌ 分析失败：{e}")


class SleepTrendChart(QWidget):
    """
    自定义睡眠趋势图表组件 (QPainter 纯绘图实现)
    支持切换：入睡/起床用时、评分、周期、深睡时长
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.history = []  # 存储最近 N 天的记录
        self.current_metric = "fall_asleep_min" # 默认显示入睡用时
        self.metric_map = {
            "sleep_score": ("睡眠评分", "分", "#81A1C1"),
            "total_sleep_min": ("总时长", "h", "#88C0D0"),
            "deep_sleep_min": ("深睡时长", "min", "#B48EAD"),
            "sleep_cycles": ("睡眠周期", "个", "#A3BE8C"),
            "fall_asleep_min": ("入睡用时", "min", "#EBCB8B"),
            "wake_up_min": ("起床用时", "min", "#D08770")
        }
        self.setMouseTracking(True)
        self.hover_index = -1
        self.setFixedHeight(220)

    def set_data(self, history_data):
        self.history = history_data
        self.update()

    def set_metric(self, metric_key):
        if metric_key in self.metric_map:
            self.current_metric = metric_key
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not self.history:
            painter.setPen(QColor(TEXT_SECONDARY))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "暂无历史趋势数据，请先分析几天记录")
            return

        w, h = self.width(), self.height()
        padding_l, padding_r = 45, 25
        padding_t, padding_b = 40, 40
        
        chart_w = w - padding_l - padding_r
        chart_h = h - padding_t - padding_b
        
        # 1. 准备数据
        vals = []
        for d in self.history:
            v = d.get(self.current_metric, 0)
            if self.current_metric == "total_sleep_min":
                v = (v or 0) / 60.0 # 分钟转小时
            vals.append(float(v or 0))
            
        max_val = max(vals) if vals else 1
        if max_val <= 0: max_val = 1
        max_val *= 1.3 # 留出顶部空间显示文字
        
        count = len(vals)
        step_x = chart_w / (count - 1) if count > 1 else chart_w
        
        # 2. 绘制背景参考线
        painter.setPen(QPen(QColor("#EDF1F7"), 1, Qt.PenStyle.DashLine))
        for i in range(4):
            y_line = h - padding_b - (i * 0.33 * chart_h)
            painter.drawLine(padding_l, int(y_line), w - padding_r, int(y_line))
            
        # 3. 绘制平滑曲线
        points = []
        for i, v in enumerate(vals):
            x = padding_l + i * step_x
            y = h - padding_b - (v / max_val * chart_h)
            points.append(QPointF(x, y))
            
        color_hex = self.metric_map[self.current_metric][2]
        main_color = QColor(color_hex)

        if len(points) > 1:
            # 绘制面积填充
            grad_path = QPainterPath()
            grad_path.moveTo(points[0].x(), h - padding_b)
            for p in points:
                grad_path.lineTo(p)
            grad_path.lineTo(points[-1].x(), h - padding_b)
            grad_path.closeSubpath()
            
            gradient = QLinearGradient(0, padding_t, 0, h - padding_b)
            fill_color = QColor(main_color)
            fill_color.setAlpha(50)
            gradient.setColorAt(0, fill_color)
            fill_color.setAlpha(0)
            gradient.setColorAt(1, fill_color)
            painter.fillPath(grad_path, QBrush(gradient))
            
            # 绘制主曲线 (贝塞尔平滑)
            painter.setPen(QPen(main_color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            path = QPainterPath()
            path.moveTo(points[0])
            for i in range(len(points)-1):
                p1 = points[i]
                p2 = points[i+1]
                dx = (p2.x() - p1.x()) / 2
                path.cubicTo(p1.x() + dx, p1.y(), p2.x() - dx, p2.y(), p2.x(), p2.y())
            painter.drawPath(path)
            
            # 4. 绘制数据点与日期
            for i, p in enumerate(points):
                is_hover = (i == self.hover_index)
                
                # 日期标签
                painter.setPen(QColor(TEXT_SECONDARY))
                painter.setFont(QFont("Segoe UI", 8))
                date_str = self.history[i]['date'][-5:] # MM-DD
                painter.drawText(QRectF(p.x()-20, h-padding_b+10, 40, 20), Qt.AlignmentFlag.AlignCenter, date_str)
                
                # 数据点
                painter.setBrush(QColor(BG_LIGHT))
                painter.setPen(QPen(main_color, 2))
                radius = 5 if is_hover else 3
                painter.drawEllipse(p, radius, radius)
                
                if is_hover:
                    # 悬停框
                    val = vals[i]
                    unit = self.metric_map[self.current_metric][1]
                    tip = f"{val:.1f}{unit}" if val != int(val) else f"{int(val)}{unit}"
                    
                    painter.setBrush(QColor(TEXT_PRIMARY))
                    painter.setPen(Qt.PenStyle.NoPen)
                    tip_rect = QRectF(p.x() - 35, p.y() - 35, 70, 24)
                    painter.drawRoundedRect(tip_rect, 5, 5)
                    painter.setPen(QColor("white"))
                    painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                    painter.drawText(tip_rect, Qt.AlignmentFlag.AlignCenter, tip)

    def mouseMoveEvent(self, event):
        if not self.history: return
        padding_l, padding_r = 45, 25
        chart_w = self.width() - padding_l - padding_r
        count = len(self.history)
        step_x = chart_w / (count - 1) if count > 1 else chart_w
        
        idx = round((event.pos().x() - padding_l) / step_x)
        if 0 <= idx < count:
            if idx != self.hover_index:
                self.hover_index = idx
                self.update()
        else:
            if self.hover_index != -1:
                self.hover_index = -1
                self.update()

    def leaveEvent(self, event):
        self.hover_index = -1
        self.update()


class AIConfigWidget(QWidget):
    """AI 分离配置面板"""
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._test_worker = None
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setSpacing(12)
        layout.setContentsMargins(15, 10, 15, 10)

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

        # 备用模型部分
        b_group, b_test_btn = self._create_group("🛡️ 3. 备用模型 (自动容灾)", "当主模型 3 次重试失败后，自动切换至此配置进行最后分析。")
        b_layout = b_group.layout()
        self.b_url = self._make_field("API 地址 (Base URL):", ai_cfg.get("backup_base_url", ""), b_layout)
        self.b_key = self._make_field("API Key:", ai_cfg.get("backup_api_key", ""), b_layout, is_password=True)
        self.b_model = self._make_field("模型名称 (Model Name):", ai_cfg.get("backup_model", ""), b_layout)
        b_test_btn.clicked.connect(lambda: self._test_connection(True, is_backup=True))
        layout.addWidget(b_group)

        # 底部留白，防止最后一个按钮被遮挡

        # 底部留白，防止最后一个按钮被遮挡
        layout.addSpacing(20)

        self.save_btn = QPushButton("💾 保存全部配置")
        self.save_btn.setFixedHeight(38)
        self.save_btn.setStyleSheet(f"background: {GREEN_ACCENT}; color: white; border-radius: 6px; font-weight: bold;")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_config)
        layout.addWidget(self.save_btn)
        layout.addStretch()

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _apply_preset(self, url, v_model, t_model, is_backup=False):
        if is_backup:
            self.b_url.setText(url)
            self.b_model.setText(v_model)
        else:
            self.v_url.setText(url)
            self.t_url.setText(url)
            self.v_model.setText(v_model)
            self.t_model.setText(t_model)

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
        row = QVBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-weight: bold; border: none;")
        edit = QLineEdit(value)
        edit.setMinimumHeight(32) # 确保高度充足
        if is_password: edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setStyleSheet(f"QLineEdit {{ border: 1px solid #E5E9F0; border-radius: 4px; padding: 6px; font-size: 12px; background: white; }}")
        row.addWidget(lbl)
        row.addWidget(edit)
        parent_layout.addLayout(row)
        return edit

    def _test_connection(self, is_vision, is_backup=False):
        if self._test_worker and self._test_worker.isRunning(): return
        
        if is_backup:
            url, key, model = self.b_url.text(), self.b_key.text(), self.b_model.text()
        else:
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
        c["backup_base_url"] = self.b_url.text().strip()
        c["backup_api_key"]  = self.b_key.text().strip()
        c["backup_model"]    = self.b_model.text().strip()
        save_config(self.config)
        QMessageBox.information(self, "成功", "AI 配置已保存！")


class SleepStatisticsWindow(QWidget):
    """睡眠与 AI 统计主窗口"""
    def __init__(self, config, parent=None, sleep_server=None):
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
        self.db = StudyLogger(self.config)
        self._selected_image = None   # 用户选择的截图路径
        self._ai_worker = None        # AIWorker 线程引用
        self._current_sleep_data = None  # 当前加载的 JSON 数据

        # 注: 图片接收信号由 GUI._on_sleep_image_uploaded 统一管理，避免双重触发

        self._build_ui()
        self.load_data()
        # 启动时更新按钮状态
        self._update_nav_buttons()
        # 启动时自动清理残留临时文件
        self._cleanup_all_pending_images()

    def _on_image_received(self, temp_path, session_id="default"):
        """当 HTTP 服务接收到图片时触发"""
        logger.info(f"SleepStatisticsWindow: 收到图片信号 -> {temp_path} (Session: {session_id})")
        # 1. 记录当前上传的路径，以便后续归档
        self._selected_image = temp_path
        fname = os.path.basename(temp_path)
        self.img_path_label.setText(f"📱 手机上传: {fname}")
        
        # 2. 确保窗口可见
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            
        # 3. 触发 AI 分析 (内部会自动识别日期、落库并同步数据)
        self._run_ai_analysis(force_sync=True, image_path=temp_path, session_id=session_id)

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
        content = QSplitter(Qt.Orientation.Horizontal)
        content.setChildrenCollapsible(False)
        content.setStyleSheet("QSplitter::handle { background: transparent; width: 6px; }")

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
        
        self.date_label = QPushButton(self.current_date.strftime("%Y-%m-%d"))
        self.date_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.date_label.setStyleSheet(f"""
            QPushButton {{ 
                font-size: 16px; 
                font-weight: bold; 
                color: {TEXT_PRIMARY}; 
                background: transparent; 
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 4px 12px;
            }} 
            QPushButton:hover {{ 
                background: #F0F2F5; 
                color: {GREEN_ACCENT};
                border: 1px solid {BORDER_COLOR};
            }}
        """)
        self.date_label.clicked.connect(self._show_calendar_popup)
        
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
        # 重新定义指标顺序：周期和深睡排在最前面，并设为 priority (橙色)
        metric_names = [
            ("睡眠周期", "sleep_cycles", " 个", "priority", "参考值：> 5.0 个"),
            ("深睡时长", "deep_sleep_min", " min", "priority", "参考值：60 - 120 min"),
            ("入睡用时", "fall_asleep_min", " min", "highlight", "参考值：< 20 min"),
            ("起床用时", "wake_up_min", " min", "highlight", "参考值：< 15 min"),
            ("清醒次数", "awake_count", " 次", "normal", "参考值：<= 2 次"),
            ("清醒时长", "awake_min", " min", "normal", "参考值：< 15 min"),
            ("深睡比例", "deep_sleep_ratio", " %", "normal", "参考值：20% - 60%"),
            ("睡眠连续性", "sleep_continuity", " 分", "normal", "参考值：> 70 分"),
            ("呼吸质量", "breathing_score", " 分", "normal", "参考值：> 90 分"),
            ("浅睡", "light_sleep_min", " min", "normal", "参考值：20% - 60%"),
            ("快速眼动", "rem_sleep_min", " min", "normal", "参考值：10% - 30%"),
            ("总时长", "total_sleep_min", " min", "normal", "总睡眠时长")
        ]
        for i, (label, key, unit, mode, tip) in enumerate(metric_names):
            card = self._create_metric_card(label, mode, tip)
            self.grid.addWidget(card, i // 4, i % 4)
            self.metrics[key] = (card.findChild(QLabel, "val"), unit)
        
        left_layout.addLayout(self.grid)
        left_layout.addStretch()

        content.addWidget(left_panel)

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

        self.sleep_btn = QPushButton("🌙 睡眠分析")
        self.sleep_btn.setFixedHeight(36)
        self.sleep_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sleep_btn.setStyleSheet(f"""
            QPushButton {{ background: #8FBF65; color: white; border-radius: 6px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background: #A2D178; }}
        """)
        self.sleep_btn.clicked.connect(lambda: self._run_ai_analysis(include_time_analysis=False))
        btn_row.addWidget(self.sleep_btn)

        self.full_btn = QPushButton("📑 完整分析")
        self.full_btn.setFixedHeight(36)
        self.full_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.full_btn.setStyleSheet(f"""
            QPushButton {{ background: {GREEN_ACCENT}; color: white; border-radius: 6px; font-weight: bold; font-size: 12px; }}
            QPushButton:hover {{ background: #3E8B81; }}
        """)
        self.full_btn.clicked.connect(lambda: self._run_ai_analysis(include_time_analysis=True))
        btn_row.addWidget(self.full_btn)

        self.refresh_btn = QPushButton("🔄 强制刷新")
        self.refresh_btn.setFixedHeight(36)
        self.refresh_btn.setFixedWidth(85)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(f"""
            QPushButton {{ background: #D8DEE9; color: {TEXT_PRIMARY}; border-radius: 6px; font-size: 12px; text-align: center; }}
            QPushButton:hover {{ background: #C4CDD9; }}
        """)
        self.refresh_btn.clicked.connect(self.force_refresh_data)
        btn_row.addWidget(self.refresh_btn)

        analysis_layout.addLayout(btn_row)
        self.tabs.addTab(analysis_page, "分析建议")

        # --- 趋势统计页 ---
        trend_page = QWidget()
        trend_layout = QVBoxLayout(trend_page)
        trend_layout.setContentsMargins(15, 15, 15, 15)
        trend_layout.setSpacing(10)
        
        # 指标切换切换按钮行
        self.chart_btn_row = QHBoxLayout()
        self.chart_btn_row.setSpacing(5)
        self.trend_btns = {}
        metric_btns = [
            ("入睡", "fall_asleep_min"),
            ("起床", "wake_up_min"),
            ("得分", "sleep_score"),
            ("周期", "sleep_cycles"),
            ("深睡", "deep_sleep_min")
        ]
        for name, key in metric_btns:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setFixedSize(55, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._switch_trend_metric(k))
            self.chart_btn_row.addWidget(btn)
            self.trend_btns[key] = btn
        
        self.chart_btn_row.addStretch()
        trend_layout.addLayout(self.chart_btn_row)
        
        # 趋势图表实例
        self.trend_chart = SleepTrendChart()
        trend_layout.addWidget(self.trend_chart)
        
        # 底部简单统计文本
        self.trend_info = QLabel("提示：点击上方按钮切换查看不同指标的趋势走势")
        self.trend_info.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px;")
        self.trend_info.setWordWrap(True)
        trend_layout.addWidget(self.trend_info)
        trend_layout.addStretch()
        
        self.tabs.addTab(trend_page, "趋势统计")
        self.trend_btns["sleep_cycles"].setChecked(True)
        self.trend_chart.set_metric("sleep_cycles")

        # 配置页
        self.config_page = AIConfigWidget(self.config)
        self.tabs.addTab(self.config_page, "AI 配置")

        right_layout.addWidget(self.tabs)
        content.addWidget(right_panel)
        content.setSizes([480, 320])

        main_layout.addWidget(content)

    def _create_metric_card(self, title, mode="normal", tip=""):
        card = QFrame()
        if tip:
            card.setToolTip(tip)
            
        if mode == "priority":
            # 橙色模式：最高优先级
            bg_color = "#FFF4E5" # 极淡橘背景
            title_color = "#D08770" # 核心橘文字
            icon = "🔥"
        elif mode == "highlight":
            # 蓝色模式：次高优先级
            bg_color = "#EBF5FF"
            title_color = "#5E81AC"
            icon = "🌟"
        else:
            bg_color = CARD_BG
            title_color = TEXT_SECONDARY
            icon = ""
            
        card.setStyleSheet(f"background: {bg_color}; border: none; border-radius: 10px;")
        layout = QVBoxLayout(card)
        l_title = QLabel(f"{icon} {title}" if icon else title)
        l_title.setStyleSheet(f"color: {title_color}; font-size: 11px; font-weight: bold;")
        
        l_val = QLabel("--")
        l_val.setObjectName("val")
        l_val.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: bold;")
        
        layout.addWidget(l_title)
        layout.addWidget(l_val)
        return card

    def change_date(self, delta):
        self.current_date += timedelta(days=delta)
        self.date_label.setText(self.current_date.strftime("%Y-%m-%d"))
        self._update_nav_buttons()
        self.load_data()

    def _update_nav_buttons(self):
        """根据当前日期更新导航按钮状态"""
        today = datetime.now().date()
        # 禁止点向未来
        is_today_or_future = self.current_date >= today
        self.next_btn.setEnabled(not is_today_or_future)
        
        # 更新样式以示区分
        if is_today_or_future:
            self.next_btn.setStyleSheet(f"QPushButton {{ border: 1px solid {BORDER_COLOR}; border-radius: 15px; color: #D8DEE9; background: transparent; }}")
            self.next_btn.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.next_btn.setStyleSheet(f"QPushButton {{ border: 1px solid {BORDER_COLOR}; border-radius: 15px; color: {TEXT_PRIMARY}; }} QPushButton:hover {{ background: #F0F2F5; }}")
            self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def load_data(self):
        """加载数据：数据库优先 -> 本地 JSON 兜底"""
        date_str = self.current_date.strftime("%Y-%m-%d")
        logger.info(f"正在加载 {date_str} 的数据...")
        
        # 1. 优先从数据库读取 (真理来源)
        db_data = self.db.get_huawei_sleep_data(date_str)
        if db_data:
            logger.info(f"✅ 从数据库加载成功: {date_str}")
            report_content = db_data.get("analysis_report", "")
            # 兼容旧代码，确保内部有 analysis 结构
            db_data["analysis"] = {"summary": report_content}
            self._current_sleep_data = db_data
            self._update_ui_with_data(db_data)
            self.analysis_text.setMarkdown(report_content)
            self._refresh_trend_data()
            return

        # 2. 备选：尝试从旧 JSON 文件加载（向下兼容）
        json_path = os.path.join(SKILL_DIR, "huawei_health_data", f"sleep_{date_str}.json")
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._current_sleep_data = data
                    self._update_ui_with_data(data)
                    report_content = data.get("analysis", {}).get("summary", "")
                    self.analysis_text.setMarkdown(report_content)
                    logger.info(f"✅ 从本地 JSON 加载成功: {date_str}")
                    self._refresh_trend_data()
                    return
            except Exception as e:
                logger.error(f"解析本地 JSON 失败: {e}")

        # 3. 都没有，清空显示
        self._current_sleep_data = None
        self._clear_ui()
        logger.info(f"❓ {date_str} 尚无睡眠记录")
        
        # 3. 加载趋势统计数据
        self._refresh_trend_data()
    
    def _refresh_trend_data(self):
        """刷新趋势图表数据"""
        try:
            history = self.db.get_sleep_history(days=14)
            if history:
                self.trend_chart.set_data(history)
                # 更新统计文本
                avg_fall = sum(d.get('fall_asleep_min', 0) or 0 for d in history) / len(history)
                avg_wake = sum(d.get('wake_up_min', 0) or 0 for d in history) / len(history)
                self.trend_info.setText(f"最近 {len(history)} 天平均：入睡 {avg_fall:.1f}分，起床 {avg_wake:.1f}分")
        except Exception as e:
            logger.error(f"刷新趋势图表失败: {e}")

    def _switch_trend_metric(self, key):
        """切换趋势图显示的指标"""
        for k, btn in self.trend_btns.items():
            btn.setChecked(k == key)
        self.trend_chart.set_metric(key)

    def force_refresh_data(self):
        """强制全流程更新：支持重走 OCR 识别和数据同步"""
        date_str = self.current_date.strftime("%Y-%m-%d")
        
        # 1. 寻找已归档的截图 (真理复核)
        attachments_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attachments")
        archived_img = os.path.join(attachments_dir, f"sleep_{date_str}.jpg")
        
        if os.path.exists(archived_img):
            logger.info(f"🔄 发现归档截图: {archived_img}，将触发全流程 OCR 重解析...")
            self._selected_image = archived_img
            self._run_ai_analysis(include_time_analysis=True, force_sync=True)
            return

        # 2. 如果没图，则回退到原有的仅时间同步逻辑
        # 尝试从数据库获取现有的睡眠基础数据
        sleep_data = self.db.get_huawei_sleep_data(date_str)
        
        # 还原 analysis 结构
        if sleep_data:
            report_content = sleep_data.pop("analysis_report", "")
            sleep_data["analysis"] = {"summary": report_content}
        
        if not sleep_data:
            QMessageBox.information(self, "无法刷新", "该日期暂无归档截图或数据库记录，无法进行强制更新。")
            return

        # 3. 启动线程进行强制同步 (无图模式)
        self.sleep_btn.setEnabled(False)
        self.full_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳ 同步中...")
        self.analysis_text.setText("🔄 正在强制同步 aTimeLogger 最新数据并重新分析报告...")

        ai_cfg = self.config.get("ai_model_config", {})
        self._ai_worker = AIWorker(
            ai_cfg=ai_cfg,
            image_path=None,
            sleep_data=sleep_data,
            force_pull=True,
            date_str=self.current_date.strftime("%Y-%m-%d"),
            db=self.db
        )
        self._ai_worker.progress.connect(lambda msg: self.analysis_text.append(f"\n{msg}"))
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_worker.error.connect(self._on_ai_error)
        # 无论成功失败都恢复按钮
        self._ai_worker.finished.connect(lambda: self.refresh_btn.setEnabled(True))
        self._ai_worker.finished.connect(lambda: self.refresh_btn.setText("🔄 强制刷新"))
        self._ai_worker.error.connect(lambda: self.refresh_btn.setEnabled(True))
        self._ai_worker.error.connect(lambda: self.refresh_btn.setText("🔄 强制刷新"))
        self._ai_worker.start()

    def _update_ui_with_data(self, data):
        score = data.get("sleep_score")
        if score is None: score = 0
        self.score_val.setText(str(score))
        if score >= 85: color = GREEN_ACCENT
        elif score >= 70: color = "#81A1C1"
        else: color = RED_ACCENT
        self.score_val.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {color};")

        # 辅助函数：智能格式化数值
        def format_val(v):
            try:
                fv = float(v)
                if fv == int(fv):
                    return str(int(fv))
                # 保留最多两位小数，并去掉末尾多余的0
                return f"{fv:.2f}".rstrip('0').rstrip('.')
            except:
                return str(v)

        # --- 智能补算逻辑 (针对历史数据或 AI 遗漏) ---
        # 如果某些计算型指标缺失，尝试根据原始数据即时推算
        t_min = to_min(data.get("total_sleep_min", 0))
        if t_min > 0:
            if not data.get("sleep_cycles"):
                data["sleep_cycles"] = round(t_min / 90.0, 2)
            
            # 补算清醒时长：(醒来 - 入睡) - 睡眠时长
            s_t = data.get("sleep_start")
            e_t = data.get("sleep_end")
            if s_t and e_t:
                try:
                    def t_to_m(t):
                        if not t or not isinstance(t, str): return 0
                        # 处理中文冒号和空格
                        t = t.replace("：", ":").strip()
                        if ":" not in t: return 0
                        h, m = map(int, t.split(":"))
                        return h * 60 + m
                    m1 = t_to_m(s_t)
                    m2 = t_to_m(e_t)
                    if m2 < m1: m2 += 24 * 60 # 跨天处理
                    
                    # 无论原值是多少，都通过公式动态展示最新的清醒时长
                    data["awake_min"] = max(0, (m2 - m1) - t_min)
                except: pass

        # 遍历指标项，格式化显示
        for key, (label, unit) in self.metrics.items():
            val = data.get(key)
            if val is not None and val != "":
                label.setText(f"{format_val(val)}{unit}")
            else:
                label.setText(f"--{unit}")

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
            self.analysis_text.setMarkdown(str(report))
        else:
            self.analysis_text.setText("数据已加载，点击《📑 完整分析》生成深度复盘报告。")
            
        self._current_sleep_data = data  # 缓存当前数据供 AI 使用

    def _clear_ui(self):
        self.score_val.setText("--")
        self.score_val.setStyleSheet(f"font-size: 48px; font-weight: bold; color: {TEXT_SECONDARY};")
        for label, unit in self.metrics.values():
            label.setText("--")
        self.analysis_text.setText("该日期暂无睡眠记录文件。")

    def _show_calendar_popup(self):
        """弹出深度定制的艺术风日历"""
        if not hasattr(self, "_calendar_widget"):
            from PyQt6.QtWidgets import QCalendarWidget
            self._calendar_widget = QCalendarWidget(self)
            self._calendar_widget.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.FramelessWindowHint)
            self._calendar_widget.setGridVisible(False)
            self._calendar_widget.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
            
            # --- 极致美化：现代艺术风格 CSS ---
            self._calendar_widget.setStyleSheet(f"""
                QCalendarWidget {{
                    background-color: #FFFFFF;
                    border: 1px solid #E5E9F0;
                    border-radius: 15px;
                    font-size: 13px; /* 修复 QFont 警告 */
                }}
                /* 导航栏：白底黑字，加大字号 */
                QCalendarWidget QWidget#qt_calendar_navigationbar {{
                    background-color: #FFFFFF;
                    border-bottom: 1px solid #F0F2F5;
                    border-top-left-radius: 15px;
                    border-top-right-radius: 15px;
                    min-height: 40px;
                }}
                /* 月份/年份按钮：移除系统自带的丑陋下拉箭头 */
                QCalendarWidget QToolButton {{
                    color: #2E3440;
                    font-family: "Segoe UI", "Microsoft YaHei";
                    font-size: 14px;
                    font-weight: bold;
                    background-color: transparent;
                    border: none;
                    margin: 2px;
                    padding: 5px;
                }}
                QCalendarWidget QToolButton::menu-indicator {{
                    image: none; /* 彻底移除那个对不齐的 V 箭头 */
                }}
                QCalendarWidget QToolButton:hover {{
                    background-color: #F8F9FB;
                    border-radius: 8px;
                    color: {GREEN_ACCENT};
                }}
                
                /* 左右箭头按钮 */
                #qt_calendar_prevmonth, #qt_calendar_nextmonth {{
                    qproperty-icon: none;
                    background-color: transparent;
                    width: 30px;
                }}
                
                /* 日期网格 */
                QCalendarWidget QTableView {{
                    outline: 0;
                    background-color: #FFFFFF;
                    selection-background-color: {GREEN_ACCENT};
                    selection-color: #FFFFFF;
                }}
                /* 星期头（周一至周日） */
                QCalendarWidget QWidget {{ alternate-background-color: #FFFFFF; }}
                QCalendarWidget QAbstractItemView:enabled {{
                    color: #4C566A;
                    font-size: 13px;
                    selection-background-color: {GREEN_ACCENT};
                    selection-color: #FFFFFF;
                }}
                /* 禁用日期（非本月） */
                QCalendarWidget QAbstractItemView:disabled {{
                    color: #D8DEE9;
                }}
            """)
            
            # 监听选中
            self._calendar_widget.clicked.connect(self._on_calendar_date_selected)
            self._calendar_widget.activated.connect(self._on_calendar_date_selected)

        # 弹出位置定位
        pos = self.date_label.mapToGlobal(QPoint(0, self.date_label.height() + 10))
        self._calendar_widget.setSelectedDate(self.current_date)
        # 微调位置让日历在按钮下方居中
        self._calendar_widget.move(pos.x() - (self._calendar_widget.width() - self.date_label.width()) // 2, pos.y())
        self._calendar_widget.show()

    def _on_calendar_date_selected(self, qdate):
        """处理日历选择后的跳转"""
        self._calendar_widget.hide()
        new_date = qdate.toPyDate()
        self.current_date = new_date
        self.date_label.setText(self.current_date.strftime("%Y-%m-%d"))
        self._update_nav_buttons() # 关键：同步更新前进/后退按钮状态
        self.load_data()

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

    def _run_ai_analysis(self, force_sync=True, image_path=None, session_id=None, include_time_analysis=False):
        """执行 AI 分析逻辑。若提供了 image_path，则先进行视觉日期解析"""
        if self._ai_worker and self._ai_worker.isRunning():
            return

        ai_cfg = self.config.get("ai_model_config", {})
        v_key = str(ai_cfg.get("vision_api_key") or "").strip()
        t_key = str(ai_cfg.get("text_api_key") or "").strip()
        
        if not v_key or not t_key:
            QMessageBox.warning(self, "请先配置", "请确保「AI 配置」页的「视觉」和「文本」API Key 均已填写。")
            self.tabs.setCurrentIndex(1)
            return

        # 准备的数据：截图或已加载的 JSON
        # 优先使用传入的 image_path (来自手机上传)，否则使用本地手动选择的
        # 注意：PyQt 信号可能会传递布尔值，这里需要做类型检查
        real_img_path = image_path if isinstance(image_path, str) else None
        img_to_use = real_img_path if real_img_path else self._selected_image
        
        has_image = img_to_use and os.path.exists(img_to_use)
        has_data  = bool(self._current_sleep_data)
        
        if not has_image and not has_data:
            if not session_id: # 只有本地手动触发且没数据才弹窗
                QMessageBox.information(self, "无数据", "请先选择截图，或切换日期使 JSON 数据加载。")
            return

        # Step 0: 增量分析优化逻辑 (根据 SKILL.md 指导思想)
        # 如果是完整分析模式，且数据库里已经有数据，且用户没选新图，则检查数据完整性
        is_incremental = False
        if include_time_analysis and self._current_sleep_data and not has_image:
            # 增加完整性校验：只有通过校验的数据才能跳过 OCR
            is_valid, _ = AIWorker.validate_data(self._current_sleep_data)
            if is_valid:
                is_incremental = True
                logger.info(f"检测到 {self.current_date} 已有完整睡眠数据，跳过视觉提取。")
            else:
                logger.info(f"检测到 {self.current_date} 睡眠数据不完整，将重新执行 OCR 流程。")

        self.sleep_btn.setEnabled(False)
        self.full_btn.setEnabled(False)
        self.sleep_btn.setText("⏳ 分析中..." if not include_time_analysis else "🌙 睡眠分析")
        self.full_btn.setText("⏳ 分析中..." if include_time_analysis else "📑 完整分析")
        self.analysis_text.setPlaceholderText("")
        
        if is_incremental:
            self.analysis_text.setText("✅ 已存在完整睡眠数据，正在跳过识别，直接拉取时间数据并生成复盘建议...")
        else:
            if include_time_analysis and self._current_sleep_data and not has_image:
                self.analysis_text.setText("⚠️ 数据库记录不完整，需要重新进行视觉解析，请选择截图...")
                # 这种情况需要让用户选图，所以不能直接启动
                self.sleep_btn.setEnabled(True)
                self.full_btn.setEnabled(True)
                self.sleep_btn.setText("🌙 睡眠分析")
                self.full_btn.setText("📑 完整分析")
                self._pick_image()
                if not self._selected_image: return # 用户取消了选图
                # 选完图后重新调用自己
                self._run_ai_analysis(force_sync=force_sync, image_path=self._selected_image, session_id=session_id, include_time_analysis=include_time_analysis)
                return
            self.analysis_text.setText("🔄 正在同步最新时间数据并开始分析...")

        # 1. 如果是自动触发或强制同步，先触发一次后台同步
        if force_sync:
            try:
                # 尝试通过父窗口的 logic 触发同步
                main_gui = self.window()
                if hasattr(main_gui, 'logic'):
                    logger.info("AI分析前：强制触发一次数据同步...")
                    main_gui.logic.sync_ticktick_tasks() 
            except Exception as e:
                logger.warning(f"同步失败，将使用现有数据: {e}")

        # 2. 启动线程 (AIWorker 内部会根据 image_path 是否为 None 决定是否跑 OCR)
        self._ai_worker = AIWorker(
            ai_cfg=ai_cfg,
            image_path=img_to_use if (has_image and not is_incremental) else None,
            sleep_data=self._current_sleep_data if is_incremental else (None if has_image else self._current_sleep_data),
            date_str=self.current_date.strftime("%Y-%m-%d"),
            force_pull=force_sync,
            session_id=session_id,
            include_time_analysis=include_time_analysis,
            db=self.db
        )
        self._ai_worker.progress.connect(lambda msg: self.analysis_text.append(f"\n{msg}"))
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_worker.error.connect(self._on_ai_error)
        self._ai_worker.start()

    def _on_ai_finished(self, report, sleep_data):
        """AI 分析完成：智能识别日期、自动归档并渲染"""
        self.sleep_btn.setEnabled(True)
        self.full_btn.setEnabled(True)
        self.sleep_btn.setText("🌙 睡眠分析")
        self.full_btn.setText("📑 完整分析")
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 强制刷新")
        
        if not sleep_data: return
        
        # 1. 智能识别日期逻辑
        target_date = self.current_date
        date_str_extracted = sleep_data.get("sleep_date") # 例如 "5月8日" 或 "2026-05-08"
        if date_str_extracted:
            try:
                import re as _re
                current_year = self.current_date.year
                # 已经是 YYYY-MM-DD 格式，直接解析
                if _re.match(r'\d{4}-\d{2}-\d{2}', str(date_str_extracted)):
                    parsed_date = datetime.strptime(str(date_str_extracted), "%Y-%m-%d")
                    # 核心防幻觉补丁：如果 AI 胡编乱造了历史年份（比如图片只有5月12日，AI非要说是2024年），直接拍死，换成本年
                    if parsed_date.year != current_year:
                        logger.warning(f"检测到 AI 提取年份异常({parsed_date.year})，强制修正为本年({current_year})")
                        # 处理闰年2月29日的边缘情况
                        try:
                            parsed_date = parsed_date.replace(year=current_year)
                        except ValueError:
                            parsed_date = parsed_date.replace(year=current_year, day=28)
                else:
                    # 解析 M月D日 格式
                    clean_date = str(date_str_extracted).replace("月", "-").replace("日", "")
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
        
        # 3. 保存到数据库
        save_date_str = target_date.strftime("%Y-%m-%d")
        try:
            # 同时将 report 提出来存入 analysis_report 字段
            db_data = sleep_data.copy()
            db_data["analysis_report"] = report
            self.db.save_huawei_sleep_data(save_date_str, db_data)
            logger.info(f"睡眠数据已保存至数据库 (日期: {save_date_str})")
        except Exception as e:
            logger.error(f"保存睡眠数据到数据库失败: {e}")

        # 3.5 根据识别日期重命名临时截图 → attachments/sleep_YYYY-MM-DD.ext
        self._rename_pending_image(save_date_str)

        # 4. 刷新 UI 指标并渲染 Markdown 报告
        self._update_ui_with_data(sleep_data)
        self.analysis_text.setMarkdown(report) # 使用 Markdown 渲染
        self.analysis_text.setStyleSheet(f"border: none; background: transparent; color: {TEXT_PRIMARY}; font-size: 13px; line-height: 1.5;")
        
        # 5. 刷新趋势数据
        self._refresh_trend_data()

    def _on_ai_error(self, msg):
        self.analysis_text.setText(msg)
        self.sleep_btn.setEnabled(True)
        self.full_btn.setEnabled(True)
        self.sleep_btn.setText("🌙 睡眠分析")
        self.full_btn.setText("📑 完整分析")
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 强制刷新")
        # 失败时也尝试清理临时文件
        self._cleanup_all_pending_images()

    def _cleanup_all_pending_images(self, exclude_path=None):
        """扫描并删除所有 sleep_pending_ 开头的临时文件"""
        try:
            attachments_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attachments")
            if not os.path.exists(attachments_dir): return
            
            for f in os.listdir(attachments_dir):
                if f.startswith("sleep_pending_") and f.endswith(".jpg"):
                    p = os.path.abspath(os.path.join(attachments_dir, f))
                    if exclude_path and p == os.path.abspath(exclude_path):
                        continue
                    try:
                        os.remove(p)
                        logger.info(f"🧹 自动清理残留临时文件: {f}")
                    except: pass
        except Exception as e:
            logger.debug(f"清理临时文件失败: {e}")

    def _rename_pending_image(self, date_str):
        """
        将 _selected_image 中的临时截图转换为 JPG 并归档到 attachments/ 目录，然后清理所有临时文件。
        """
        if not self._selected_image or not os.path.exists(self._selected_image):
            # 即使没选中，也尝试清理一下可能存在的残留
            self._cleanup_all_pending_images()
            return
        
        old_path = os.path.abspath(self._selected_image)
        basename = os.path.basename(old_path)
        
        # 即使不是 pending，我们也尝试按日期重命名备份
        new_name = f"sleep_{date_str}.jpg"
        attachments_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "attachments")
        os.makedirs(attachments_dir, exist_ok=True)
        new_path = os.path.join(attachments_dir, new_name)

        try:
            from PIL import Image
            import shutil
            
            # 1. 转换并归档为标准格式 (JPG)
            with Image.open(old_path) as img:
                img.convert("RGB").save(new_path, "JPEG", quality=90)
            
            # 2. 如果是正在处理的文件，且不是目标路径，则尝试删除它
            if old_path != os.path.abspath(new_path):
                try:
                    os.remove(old_path)
                except: pass
            
            # 3. 强力清理所有残留
            self._cleanup_all_pending_images(exclude_path=new_path)

            self._selected_image = new_path
            self.img_path_label.setText(f"📁 已归档: {new_name}")
            logger.info(f"📸 截图归档成功: {new_name}，临时文件已清空。")
            
        except Exception as e:
            logger.error(f"归档截图失败: {e}")
