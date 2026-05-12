# -*- coding: utf-8 -*-
import os
import json
import base64
import logging
import shutil
import traceback
from datetime import datetime, timedelta, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QPushButton, QFrame, QStackedWidget, QGridLayout,
    QLineEdit, QTextEdit, QTabWidget, QGraphicsOpacityEffect,
    QMessageBox, QFileDialog, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize, QThread, QRectF, QPointF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush, QLinearGradient, QPainterPath

from config import save_config
from utils import resource_path
from database import StudyLogger

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

    def __init__(self, ai_cfg, image_path=None, sleep_data=None, force_pull=False, date_str=None, session_id=None):
        super().__init__()
        self.ai_cfg = ai_cfg
        self.image_path = image_path
        self.sleep_data = sleep_data
        self.force_pull = force_pull
        self.date_str = date_str
        self.session_id = session_id # 用于 SSE 推送

    def update_progress(self, msg):
        """同时更新本地 UI 和 Web 推送"""
        self.progress.emit(msg)
        if self.session_id:
            try:
                from sleep_server import broker
                broker.push(self.session_id, {"status": "progress", "msg": msg})
            except: pass

    def validate_data(self, data):
        """校验华为睡眠数据完整性"""
        required = ["sleep_score", "deep_sleep_min", "sleep_cycles"]
        for key in required:
            val = data.get(key)
            if val is None or (isinstance(val, (int, float)) and val <= 0):
                return False
        # 检查额外指标是否大部分提取成功 (允许部分缺失但不能全是0)
        extra = ["light_sleep_min", "rem_sleep_min", "awake_count"]
        extracted_count = sum(1 for k in extra if data.get(k) and data.get(k) > 0)
        return extracted_count >= 1

    def run(self):
        max_retries = 2
        attempt = 0
        
        try:
            while attempt <= max_retries:
                attempt += 1
                try:
                    from openai import OpenAI
                    import time
                    
                    # ── 步骤 1: 视觉解析 ──
                    if not self.image_path or not os.path.exists(self.image_path):
                        self.error.emit("❌ 未找到图片文件。")
                        return

                    msg_prefix = f"📸 正在解析截图 ({attempt}/{max_retries+1})..." if attempt > 1 else "📸 正在解析截图内容..."
                    self.update_progress(msg_prefix)
                    
                    v_url = clean_url(self.ai_cfg.get("vision_base_url", ""))
                    v_key = self.ai_cfg.get("vision_api_key", "")
                    v_model = self.ai_cfg.get("vision_model", "glm-4v-flash")
                    client_v = OpenAI(api_key=v_key, base_url=v_url)
                    
                    # 图片预处理
                    final_img_path = self.image_path
                    temp_img_path = None
                    try:
                        from PIL import Image
                        with Image.open(self.image_path) as img:
                            w, h = img.size
                            if h > 2048:
                                new_h = 2048
                                new_w = int(w * (new_h / h))
                                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                                temp_img_path = self.image_path + ".v.jpg"
                                img.convert("RGB").save(temp_img_path, "JPEG", quality=90)
                                final_img_path = temp_img_path
                    except: pass

                    with open(final_img_path, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode()
                    if temp_img_path and os.path.exists(temp_img_path): os.remove(temp_img_path)

                    # 视觉 Prompt (V4.2 完整版)
                    prompt = """提取以下字段并以 JSON 返回：
1. sleep_date: 截图中的日期 (YYYY-MM-DD)
2. sleep_score: 睡眠得分 (整数)
3. sleep_cycles: 睡眠周期个数 (数字)
4. deep_sleep_min: 深睡时长 (分钟)
5. light_sleep_min: 浅睡时长 (分钟)
6. rem_sleep_min: 快速眼动时长 (分钟)
7. awake_count: 清醒次数 (整数)
8. awake_time_min: 清醒时长 (分钟)
9. fall_asleep_min: 入睡用时 (分钟)
10. wake_up_min: 起床用时 (分钟)
11. official_interpretation: 华为运动健康的解读与建议 (详细文本)
12. sleep_start: 入睡时间 (HH:mm)
13. sleep_end: 醒来时间 (HH:mm)
14. total_sleep_min: 总睡眠时长 (分钟)
注意：务必提取完整。只返回纯 JSON 块。"""

                    vision_resp = client_v.chat.completions.create(
                        model=v_model,
                        messages=[{"role": "user", "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                            {"type": "text", "text": prompt}
                        ]}],
                        temperature=0.1
                    )
                    raw = vision_resp.choices[0].message.content.strip()
                    if "```" in raw: raw = raw.split("```")[1].replace("json", "").strip()
                    self.sleep_data = json.loads(raw)
                    
                    # 数据校验
                    if self.validate_data(self.sleep_data):
                        break # 校验通过，退出重试循环
                    
                    if attempt <= max_retries:
                        self.update_progress(f"⚠️ 提取不完整，正在进行第 {attempt} 次重试...")
                        time.sleep(1)
                    else:
                        self.update_progress("⚠️ 已达到最大重试次数，将使用现有提取结果。")
                        
                except Exception as loop_e:
                    if attempt > max_retries:
                        raise loop_e
                    self.update_progress(f"⚠️ 分析出错，正在进行第 {attempt} 次重试... ({loop_e})")
                    time.sleep(1)

            # ── 步骤 2: 定日期并实时同步数据 (移出循环，确保识别完成后执行) ──
            if not self.sleep_data:
                raise Exception("未获取到睡眠数据，分析中止。")

            target_date = self.sleep_data.get("sleep_date")
            if not target_date or len(target_date) < 8:
                target_date = datetime.now().strftime("%Y-%m-%d")
            
            self.sleep_data['date'] = target_date
            self.update_progress(f"📅 日期: {target_date}，正在拉取数据...")

            import sys
            skill_dir = os.path.join(os.path.dirname(__file__), "document", "skills", "time-management")
            if skill_dir not in sys.path:
                sys.path.insert(0, skill_dir)
            from generate_full_report import generate_comprehensive_report

            # 核心改进：即时分析不包含 Part 2
            report_path = generate_comprehensive_report(
                target_date, 
                injected_sleep_data=self.sleep_data,
                force_pull=True,
                include_time_analysis=False
            )
            
            if report_path and os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as f:
                    report = f.read()
            else:
                report = "生成报告失败，请检查同步配置。"
                
            # ── 步骤 3: 结果分发 ──
            self.update_progress("✨ 分析完成，正在同步结果...")
            
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
                    broker.push(self.session_id, {"status": "progress", "msg": f"❌ 错误: {str(e)}"})
                except: pass
            self.error.emit(f"❌ 分析失败：{e}")

        except Exception as e:
            logger.error(f"AIWorker Error: {e}")
            if self.session_id:
                try:
                    from sleep_server import broker
                    broker.push(self.session_id, {"status": "progress", "msg": f"❌ 错误: {str(e)}"})
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

    def _on_image_received(self, temp_path, session_id="default"):
        """当 HTTP 服务接收到图片时触发"""
        logger.info(f"SleepStatisticsWindow: 收到图片信号 -> {temp_path} (Session: {session_id})")
        # 核心绑定：确保归档函数能找到当前图片
        self._selected_image = temp_path
        self._run_ai_analysis(force_sync=True, image_path=temp_path, session_id=session_id)
        fname = os.path.basename(temp_path)
        self.img_path_label.setText(f"📱 手机上传: {fname}")
        
        # 1. 确保窗口可见
        if not self.isVisible():
            self.show()
            self.raise_()
            self.activateWindow()
            
        # 2. 自动触发 AI 分析 (内部会自动识别日期并同步数据)
        self._run_ai_analysis()

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
        # 重新定义指标顺序：周期和深睡排在最前面，并设为 priority (橙色)
        metric_names = [
            ("睡眠周期", "sleep_cycles", " 个", "priority"),
            ("深睡时长", "deep_sleep_min", " min", "priority"),
            ("入睡用时", "fall_asleep_min", " min", "highlight"),
            ("起床用时", "wake_up_min", " min", "highlight"),
            ("清醒次数", "awake_count", " 次", "normal"),
            ("清醒时长", "awake_min", " min", "normal"),
            ("浅睡", "light_sleep_min", " min", "normal"),
            ("快速眼动", "rem_sleep_min", " min", "normal")
        ]
        for i, (label, key, unit, mode) in enumerate(metric_names):
            card = self._create_metric_card(label, mode)
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

    def _create_metric_card(self, title, mode="normal"):
        card = QFrame()
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
        
        # 1. 优先尝试从数据库加载
        data = self.db.get_huawei_sleep_data(date_str)
        
        if data:
            # 还原 analysis 结构
            report_content = data.pop("analysis_report", "")
            data["analysis"] = {"summary": report_content}
            self._update_ui_with_data(data)
            self.analysis_text.setMarkdown(report_content)
        else:
            # 2. 备选：尝试从旧 JSON 文件加载（向下兼容）
            data_path = resource_path(os.path.join("document", "skills", "time-management", "huawei_health_data", f"sleep_{date_str}.json"))
            if os.path.exists(data_path):
                try:
                    with open(data_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        self._update_ui_with_data(data)
                        report_content = data.get("analysis", {}).get("summary", "")
                        self.analysis_text.setMarkdown(report_content)
                except Exception as e:
                    logger.error(f"加载睡眠数据失败: {e}")
                    self._clear_ui()
            else:
                self._clear_ui()
        
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
        """强制重新拉取网站数据并更新报告"""
        date_str = self.current_date.strftime("%Y-%m-%d")
        
        # 1. 尝试从数据库获取现有的睡眠基础数据
        sleep_data = self.db.get_huawei_sleep_data(date_str)
        
        # 还原 analysis 结构
        if sleep_data:
            report_content = sleep_data.pop("analysis_report", "")
            sleep_data["analysis"] = {"summary": report_content}
        
        if not sleep_data:
            # 如果数据库没有，再看看有没有旧 JSON
            data_path = resource_path(os.path.join("document", "skills", "time-management", "huawei_health_data", f"sleep_{date_str}.json"))
            if os.path.exists(data_path):
                try:
                    with open(data_path, 'r', encoding='utf-8') as f:
                        sleep_data = json.load(f)
                except: pass
        
        if not sleep_data:
            QMessageBox.information(self, "无法刷新", "该日期暂无睡眠基础数据，请先上传截图进行 AI 分析。")
            return

        # 2. 启动 AI Worker 进行强制同步
        self.ai_btn.setEnabled(False)
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⏳ 同步中...")
        self.analysis_text.setText("🔄 正在强制同步 aTimeLogger 网站最新数据并重新生成报告...")

        ai_cfg = self.config.get("ai_model_config", {})
        self._ai_worker = AIWorker(
            ai_cfg=ai_cfg,
            image_path=None,
            sleep_data=sleep_data,
            force_pull=True,
            date_str=self.current_date.strftime("%Y-%m-%d")
        )
        self._ai_worker.progress.connect(lambda msg: self.analysis_text.append(f"\n{msg}"))
        self._ai_worker.finished.connect(self._on_ai_finished)
        self._ai_worker.error.connect(self._on_ai_error)
        # 无论成功失败都恢复按钮
        self._ai_worker.finished.connect(lambda: self.refresh_btn.setEnabled(True))
        self._ai_worker.finished.connect(lambda: self.refresh_btn.setText("🔄 刷新"))
        self._ai_worker.error.connect(lambda: self.refresh_btn.setEnabled(True))
        self._ai_worker.error.connect(lambda: self.refresh_btn.setText("🔄 刷新"))
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

    def _run_ai_analysis(self, force_sync=True, image_path=None, session_id=None):
        """执行 AI 分析逻辑。若提供了 image_path，则先进行视觉日期解析"""
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

        self.ai_btn.setEnabled(False)
        self.ai_btn.setText("⏳ 分析中...")
        self.analysis_text.setPlaceholderText("")
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

        # 2. 启动线程 (AIWorker 内部会调用 generate_comprehensive_report)
        self._ai_worker = AIWorker(
            ai_cfg=ai_cfg,
            image_path=img_to_use if has_image else None,
            sleep_data=None if has_image else self._current_sleep_data,
            date_str=self.current_date.strftime("%Y-%m-%d"),
            force_pull=force_sync,
            session_id=session_id
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
        date_str_extracted = sleep_data.get("sleep_date") # 例如 "5月8日" 或 "2026-05-08"
        if date_str_extracted:
            try:
                import re as _re
                current_year = self.current_date.year
                # 已经是 YYYY-MM-DD 格式，直接解析
                if _re.match(r'\d{4}-\d{2}-\d{2}', str(date_str_extracted)):
                    parsed_date = datetime.strptime(str(date_str_extracted), "%Y-%m-%d")
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
        self.ai_btn.setEnabled(True)
        self.ai_btn.setText("🚀 AI 分析")

    def _rename_pending_image(self, date_str):
        """
        将 _selected_image 中的临时截图转换为 JPG 并归档到 attachments/ 目录，然后清理所有临时文件。
        """
        if not self._selected_image or not os.path.exists(self._selected_image):
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
            
            # 3. 强力清理：扫描 attachments 目录，删除所有多余的 pending 临时文件
            try:
                for f in os.listdir(attachments_dir):
                    if f.startswith("sleep_pending_") and f.endswith(".jpg"):
                        p = os.path.join(attachments_dir, f)
                        # 只要不是刚生成的新文件，全部删掉
                        if os.path.abspath(p) != os.path.abspath(new_path):
                            os.remove(p)
                            logger.info(f"🧹 自动清理残留临时文件: {f}")
            except Exception as ce:
                logger.debug(f"清理临时文件时出现小插曲: {ce}")

            self._selected_image = new_path
            self.img_path_label.setText(f"📁 已归档: {new_name}")
            logger.info(f"📸 截图归档成功: {new_name}，临时文件已清空。")
            
        except Exception as e:
            logger.error(f"归档截图失败: {e}")
