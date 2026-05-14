# -*- coding: utf-8 -*-
"""
Pure Python sleep analysis pipeline.

This module intentionally has no PyQt dependency so it can be reused by the
desktop worker and the cloud FastAPI service.
"""

import base64
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime

import httpx
from openai import OpenAI


logger = logging.getLogger(__name__)


def clean_url(url):
    """Normalize OpenAI-compatible base URLs."""
    if not url or not isinstance(url, str):
        return ""
    url = url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        url = url[:-len("/chat/completions")].rstrip("/")
    return url


def to_min(val):
    """Convert duration values such as '1小时20分' or '80min' to minutes."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).lower()
    h_match = re.search(r"(\d+)\s*(?:h|小时|时)", s)
    m_match = re.search(r"(\d+)\s*(?:m|分钟|分)", s)
    total = 0
    if h_match:
        total += int(h_match.group(1)) * 60
    if m_match:
        total += int(m_match.group(1))
    if total > 0:
        return total
    try:
        clean_s = re.sub(r"[^\d.]", "", s)
        if not clean_s:
            return 0
        return int(float(clean_s))
    except Exception:
        return 0


def clean_num(val):
    """Extract a numeric value from model output."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return val
    try:
        clean_s = re.sub(r"[^\d.]", "", str(val))
        if not clean_s:
            return 0
        num = float(clean_s)
        return int(num) if num == int(num) else num
    except Exception:
        return 0


@dataclass
class SleepAnalysisResult:
    date: str = ""
    sleep_data: dict | None = None
    analysis_report: str = ""
    report_path: str = ""
    status: str = "error"
    error: str = ""

    def to_dict(self):
        return asdict(self)


class SleepAnalyzer:
    """Reusable sleep screenshot analyzer for desktop and cloud execution."""

    def __init__(
        self,
        ai_cfg,
        image_path=None,
        sleep_data=None,
        date_str=None,
        include_time_analysis=False,
        db=None,
        progress_callback=None,
    ):
        self.ai_cfg = ai_cfg or {}
        self.image_path = image_path
        self.sleep_data = sleep_data
        self.date_str = date_str
        self.include_time_analysis = include_time_analysis
        self.db = db
        self.progress_callback = progress_callback

    def progress(self, msg):
        if self.progress_callback:
            self.progress_callback(msg)

    @staticmethod
    def validate_data(data):
        """Validate raw Huawei sleep OCR fields."""
        required = [
            "sleep_score",
            "deep_sleep_min",
            "deep_sleep_ratio",
            "sleep_start",
            "sleep_end",
            "total_sleep_min",
        ]
        missing = []
        for key in required:
            val = data.get(key)
            if val is None or val == "":
                missing.append(key)

        if missing:
            msg = f"缺失核心原始指标: {', '.join(missing)}"
            print(f"  [校验失败] {msg}")
            return False, msg

        try:
            total = to_min(data.get("total_sleep_min", 0))
            deep = to_min(data.get("deep_sleep_min", 0))
            light = to_min(data.get("light_sleep_min", 0))
            rem = to_min(data.get("rem_sleep_min", 0))
            sum_stages = deep + light + rem
            if total != sum_stages:
                msg = f"数学校验失败: 总时长({total}) != 阶段之和({sum_stages}) [深{deep}+浅{light}+REM{rem}]"
                print(f"  [校验失败] {msg}")
                return False, msg
            print(f"  [校验通过] 数学逻辑自洽: {total} == {sum_stages}")
        except Exception as exc:
            print(f"  [校验跳过] 数学检查异常: {exc}")

        return True, ""

    @staticmethod
    def normalize_data(data):
        if not data or not isinstance(data, dict):
            return data

        time_fields = [
            "deep_sleep_min",
            "light_sleep_min",
            "rem_sleep_min",
            "awake_min",
            "fall_asleep_min",
            "wake_up_min",
            "total_sleep_min",
        ]
        for field in time_fields:
            if field in data:
                data[field] = to_min(data[field])

        num_fields = [
            "sleep_score",
            "sleep_cycles",
            "awake_count",
            "deep_sleep_ratio",
            "light_sleep_ratio",
            "rem_sleep_ratio",
            "sleep_continuity",
            "breathing_score",
        ]
        for field in num_fields:
            if field in data:
                data[field] = clean_num(data[field])

        total = data.get("total_sleep_min", 0)
        if total and total > 0:
            if data.get("deep_sleep_ratio") is None and data.get("deep_sleep_min") is not None:
                data["deep_sleep_ratio"] = round(to_min(data["deep_sleep_min"]) / total * 100)
            if data.get("light_sleep_ratio") is None and data.get("light_sleep_min") is not None:
                data["light_sleep_ratio"] = round(to_min(data["light_sleep_min"]) / total * 100)
            if data.get("rem_sleep_ratio") is None and data.get("rem_sleep_min") is not None:
                data["rem_sleep_ratio"] = round(to_min(data["rem_sleep_min"]) / total * 100)

        return data

    @staticmethod
    def extract_json(text):
        if not text:
            return None
        if "```" in text:
            try:
                json_part = text.split("```")[1].replace("json", "").strip()
                return json.loads(json_part)
            except Exception:
                pass
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            candidate = match.group(1)
            try:
                return json.loads(candidate)
            except Exception:
                pass
        brace_count = 0
        first_brace = -1
        for idx, char in enumerate(text):
            if char == "{":
                if first_brace == -1:
                    first_brace = idx
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0 and first_brace != -1:
                    try:
                        return json.loads(text[first_brace : idx + 1])
                    except Exception:
                        continue
        return None

    def _load_prompt(self):
        skill_path = os.path.join(os.path.dirname(__file__), "skills", "time-management", "SKILL.md")
        try:
            if os.path.exists(skill_path):
                with open(skill_path, "r", encoding="utf-8") as file:
                    content = file.read()
                if "```vision_prompt" in content:
                    return content.split("```vision_prompt")[1].split("```")[0].strip()
                if "```text" in content:
                    return content.split("```text")[1].split("```")[0].strip()
        except Exception:
            logger.exception("读取睡眠视觉 Prompt 失败")

        return (
            "请从睡眠截图中精确提取以下 13 个原始指标并以纯 JSON 格式返回。严禁任何开场白、Markdown 符号或额外计算：\n"
            "1. sleep_date (日期, YYYY-MM-DD)\n"
            "2. sleep_score (睡眠评分)\n"
            "3. total_sleep_min (夜间睡眠时长, 对应'夜间睡眠')\n"
            "4. deep_sleep_min (深睡时长)\n"
            "5. light_sleep_min (浅睡时长)\n"
            "6. rem_sleep_min (快速眼动/REM时长)\n"
            "7. awake_count (清醒次数)\n"
            "8. sleep_start (入睡时刻, e.g. 23:30)\n"
            "9. sleep_end (醒来时刻, e.g. 07:00)\n"
            "10. deep_sleep_ratio (深睡比例 %)\n"
            "11. light_sleep_ratio (浅睡比例 %)\n"
            "12. rem_sleep_ratio (快速眼动比例 %)\n"
            "13. sleep_continuity (深睡连续性)\n"
            "14. breathing_score (呼吸质量)\n"
            "15. analysis_report (解读与建议文本)\n\n"
            "注意：严禁提取或计算 sleep_cycles, awake_min, fall_asleep_min, wake_up_min，这些将由系统公式处理。\n"
            "必须确保 total_sleep_min 对应截图中的'夜间睡眠'数值。\n"
            "重要：必须核对数值，确保 total_sleep_min = deep_sleep_min + light_sleep_min + rem_sleep_min。"
        )

    def _prepare_image(self):
        final_img_path = self.image_path
        temp_img_path = None
        try:
            from PIL import Image

            with Image.open(self.image_path) as img:
                _w, h = img.size
                if h > 2048:
                    new_h = 2048
                    new_w = int(img.size[0] * (new_h / h))
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    temp_img_path = self.image_path + ".v.jpg"
                    img.convert("RGB").save(temp_img_path, "JPEG", quality=90)
                    final_img_path = temp_img_path
        except Exception:
            logger.exception("图片预处理失败，将使用原图")
        return final_img_path, temp_img_path

    def _extract_sleep_data(self):
        total_attempts = 6
        for attempt in range(1, total_attempts + 1):
            try:
                has_backup = bool(self.ai_cfg.get("backup_api_key"))
                use_backup = attempt % 2 == 0 and has_backup
                use_type = "backup" if use_backup else "main"
                model_type = "备用" if use_backup else "主"

                v_url = clean_url(self.ai_cfg.get("backup_base_url" if use_type == "backup" else "vision_base_url", ""))
                v_key = self.ai_cfg.get("backup_api_key" if use_type == "backup" else "vision_api_key", "")
                v_model = self.ai_cfg.get("backup_model" if use_type == "backup" else "vision_model", "glm-4v-flash")

                if not v_key:
                    raise ValueError("视觉模型 API Key 为空")

                self.progress(f"{model_type}模型解析中 ({attempt}/{total_attempts})...")

                http_client = httpx.Client(
                    verify=False,
                    timeout=httpx.Timeout(60.0, connect=10.0),
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                )
                client_v = OpenAI(api_key=v_key, base_url=v_url, http_client=http_client)

                hint_year = str(datetime.now().year)
                try:
                    basename = os.path.basename(self.image_path)
                    match = re.search(r"(20[2-3]\d)", basename)
                    if match:
                        hint_year = match.group(1)
                        print(f"文件名识别到年份建议: {hint_year}")
                except Exception:
                    pass

                final_img_path, temp_img_path = self._prepare_image()
                try:
                    with open(final_img_path, "rb") as file:
                        img_b64 = base64.b64encode(file.read()).decode()
                finally:
                    if temp_img_path and os.path.exists(temp_img_path):
                        os.remove(temp_img_path)

                prompt = self._load_prompt()
                if hint_year:
                    prompt += f"\n\n注意：当前上下文年份为 {hint_year}。请将此年份与截图中识别到的月、日组合成完整的 sleep_date。"

                vision_resp = client_v.chat.completions.create(
                    model=v_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                    temperature=0.1,
                )
                content = vision_resp.choices[0].message.content
                if not content:
                    raise ValueError("模型返回内容为空")

                sleep_data = self.extract_json(content.strip())
                if not sleep_data:
                    raise ValueError(f"模型输出不符合 JSON 格式，请检查模型稳定性。输出内容: {content[:50]}...")

                sleep_data = self.normalize_data(sleep_data)
                extracted_date = sleep_data.get("sleep_date")
                if extracted_date and self.date_str:
                    try:
                        target_dt = datetime.strptime(self.date_str, "%Y-%m-%d")
                        ext_dt = datetime.strptime(extracted_date, "%Y-%m-%d")
                        if abs((target_dt - ext_dt).days) > 1:
                            raise ValueError(f"日期不匹配！截图日期是 {extracted_date}，而当前处理日期是 {self.date_str}。请确认是否选错了图。")
                    except Exception as exc:
                        if "日期不匹配" in str(exc):
                            raise

                is_valid, reason = self.validate_data(sleep_data)
                if is_valid:
                    sleep_data["extracted_by"] = v_model
                    return sleep_data

                self.progress(f"{v_model} 识别异常: {reason}")
                if attempt < total_attempts:
                    self.progress(f"提取不完整，正在进行第 {attempt} 次重试...")
                    time.sleep(2)
                else:
                    self.progress("已达到最大重试次数，将使用现有提取结果。")
                    sleep_data["extracted_by"] = v_model
                    return sleep_data
            except Exception as exc:
                if attempt >= total_attempts:
                    raise
                err_msg = str(exc)
                if "Connection error" in err_msg:
                    err_msg = "网络连接失败，请检查 API 地址或网络环境"
                self.progress(f"分析出错，正在重试({attempt})... {err_msg}")
                time.sleep(3)
        raise RuntimeError("未获取到睡眠数据，分析中止。")

    def analyze(self):
        try:
            if not self.image_path or not os.path.exists(self.image_path):
                if self.sleep_data:
                    self.progress("检测到已有睡眠数据，跳过识别环节...")
                else:
                    raise FileNotFoundError("未找到截图文件，且数据库中无今日数据。")
            else:
                self.sleep_data = self._extract_sleep_data()

            if not self.sleep_data:
                raise RuntimeError("未获取到睡眠数据，分析中止。")

            target_date = self.sleep_data.get("sleep_date")
            if not target_date or len(str(target_date)) < 8:
                target_date = datetime.now().strftime("%Y-%m-%d")
            else:
                current_year = str(datetime.now().year)
                if not str(target_date).startswith(current_year):
                    target_date = current_year + str(target_date)[4:]
                    self.sleep_data["sleep_date"] = target_date

            self.sleep_data["date"] = target_date
            self.progress(f"日期: {target_date}，正在拉取数据...")

            skill_dir = os.path.join(os.path.dirname(__file__), "skills", "time-management")
            if skill_dir not in sys.path:
                sys.path.insert(0, skill_dir)
            from generate_full_report import generate_comprehensive_report

            report_path = generate_comprehensive_report(
                target_date,
                injected_sleep_data=self.sleep_data,
                force_pull=True,
                include_time_analysis=self.include_time_analysis,
                db=self.db,
            )

            if report_path and os.path.exists(report_path):
                with open(report_path, "r", encoding="utf-8") as file:
                    report = file.read()
            else:
                report = "生成报告失败，请检查同步配置。"

            self.progress("分析完成，正在同步结果...")
            return SleepAnalysisResult(
                date=target_date,
                sleep_data=self.sleep_data,
                analysis_report=report,
                report_path=report_path or "",
                status="done",
                error="",
            )
        except Exception as exc:
            logger.error(f"SleepAnalyzer Error: {exc}")
            return SleepAnalysisResult(
                date="",
                sleep_data=self.sleep_data,
                analysis_report="",
                report_path="",
                status="error",
                error=str(exc),
            )
