#!/usr/bin/env python3
"""
生成完整的时间管理分析报告 (V4.2)
优化：支持仅生成睡眠报告模式。
"""

import sys
import os
import json
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

def format_val(v):
    if v is None: return "N/A"
    try:
        fv = float(v)
        if fv == int(fv): return str(int(fv))
        return f"{fv:.2f}".rstrip('0').rstrip('.')
    except: return str(v)

# 路径配置
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SKILL_DIR)

project_root = os.path.abspath(os.path.join(SKILL_DIR, "..", "..", ".."))
if project_root not in sys.path: sys.path.append(project_root)

try:
    from database import StudyLogger
except ImportError:
    StudyLogger = None

from modules.atimelogger_extractor import AtimeloggerExtractor
from modules.screenshot_parser import ScreenshotParser

SLEEP_DATA_DIR = os.path.join(SKILL_DIR, "huawei_health_data")

def generate_comprehensive_report(date_str, injected_sleep_data=None, force_pull=False, include_time_analysis=True):
    """
    生成综合分析报告
    include_time_analysis: 是否包含 Part 2 时间管理部分
    """
    print(f"\n📊 开始生成 {date_str} 深度复盘报告 (模式: {'完整' if include_time_analysis else '仅睡眠'})...")
    
    config_path = os.path.join(SKILL_DIR, 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    db = StudyLogger(config) if StudyLogger else None
    
    # 1. 提取 aTimeLogger 数据 (仅在需要时)
    atimelogger_data = None
    if include_time_analysis:
        if db and not force_pull:
            atimelogger_data = db.get_atm_data(date_str)
        
        if not atimelogger_data:
            extractor = AtimeloggerExtractor(config.get('atimelogger', {}))
            atimelogger_data = extractor.extract_daily_data(date_str)
            if atimelogger_data and db:
                db.save_atm_data(date_str, atimelogger_data)
    
    # 2. 加载华为健康睡眠数据
    sleep_data = injected_sleep_data
    if not sleep_data and db:
        sleep_data = db.get_huawei_sleep_data(date_str)
        if sleep_data:
            report_content = sleep_data.pop("analysis_report", "")
            sleep_data["analysis"] = {"summary": report_content}
    
    if sleep_data:
        # 归一化计算
        total_min = float(sleep_data.get('total_sleep_min', 0))
        if total_min > 0:
            sleep_data['sleep_cycles'] = round(total_min / 90.0, 2)
        
        parser = ScreenshotParser()
        activities = atimelogger_data.get('activities', []) if atimelogger_data else []
        fall_asleep_min, wake_up_min = parser.calculate_sleep_transition_times(sleep_data, activities)
        sleep_data['fall_asleep_min'] = round(float(fall_asleep_min), 2)
        sleep_data['wake_up_min'] = round(float(wake_up_min), 2)

    # 3. 分析
    combined_data = combine_data(atimelogger_data, sleep_data, date_str)
    analysis = perform_deep_analysis(combined_data)
    
    # 4. 生成报告文件
    report_path = generate_full_report_file(combined_data, analysis, date_str, include_time_analysis)
    
    # 5. 回写数据库
    if sleep_data and db and os.path.exists(report_path):
        with open(report_path, 'r', encoding='utf-8') as f:
            full_content = f.read()
        db_data = sleep_data.copy()
        db_data["analysis_report"] = full_content
        db.save_huawei_sleep_data(date_str, db_data)
        
    return report_path

def combine_data(atimelogger_data, sleep_data, date_str):
    activities = atimelogger_data.get('activities', []) if atimelogger_data else []
    type_durations = defaultdict(int)
    for act in activities:
        type_durations[act['type']] += act['duration']
    
    return {
        'date': date_str,
        'atimelogger': atimelogger_data,
        'sleep': sleep_data,
        'summary': {
            'total_tracked_time': sum(type_durations.values()),
            'activity_breakdown': dict(type_durations)
        }
    }

def perform_deep_analysis(data):
    summary = data.get('summary', {})
    activity_breakdown = summary.get('activity_breakdown', {})
    productive_hrs = activity_breakdown.get('生产', 0) / 3600
    
    score = 60
    if productive_hrs > 3: score += 20
    if data.get('sleep', {}).get('sleep_score', 0) > 80: score += 20
    
    return {
        'summary': {'efficiency_score': min(100, score)},
        'insights': ["保持专注是提升效率的关键。"],
        'recommendations': ["建议睡前 1 小时放下手机。"]
    }

def generate_full_report_file(data, analysis, date_str, include_time_analysis=True):
    """生成完整报告文件"""
    sleep = data.get('sleep', {})
    summary = data.get('summary', {})
    activities = data.get('atimelogger', {}).get('activities', []) if data.get('atimelogger') else []
    
    lines = [
        f"# 📔 深度复盘报告 - {date_str}",
        "",
        f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | **状态**: `{'全天复盘' if include_time_analysis else '晨间速报'}`",
        "",
        "---",
        "",
        "## 🌙 [Part 1: 睡眠健康报告]",
        "",
    ]
    
    if sleep:
        lines.extend([
            "### 1.1 核心数据",
            "",
            "| 指标 | 详细数据 | 状态评估 |",
            "| :--- | :--- | :--- |",
            f"| 📊 **睡眠评分** | {sleep.get('sleep_score', '--')} 分 | {'优秀' if int(sleep.get('sleep_score',0)) >= 85 else '良好'} |",
            f"| 🔄 **睡眠周期** | {format_val(sleep.get('sleep_cycles', 0))} 个 | {'✅ 达标' if float(sleep.get('sleep_cycles',0)) >= 5 else '⚠️ 略少'} |",
            f"| 💤 **深睡时长** | {sleep.get('deep_sleep_min', '--')} min | - |",
            f"| 🌙 **入睡用时** | {sleep.get('fall_asleep_min', '--')} min | {'✅ 极快' if float(sleep.get('fall_asleep_min',0)) < 15 else '正常'} |",
            f"| ☀️ **起床用时** | {sleep.get('wake_up_min', '--')} min | {'✅ 迅速' if float(sleep.get('wake_up_min',0)) < 15 else '赖床'} |",
            f"| 📅 **记录日期** | {date_str} | - |",
            "",
            "### 1.2 睡眠自我评价",
        ])
        
        refl = sleep.get('sleep_reflection', '').strip()
        lines.append(f"> {refl if refl else '*今日未记录主观评价*'}")
        
        lines.extend([
            "",
            "### 1.3 华为健康建议",
            f"> {sleep.get('official_interpretation', '暂无官方建议')}",
            "",
        ])
    else:
        lines.append("> ⚠️ 今日未同步睡眠数据\n")

    if include_time_analysis:
        lines.extend([
            "---",
            "",
            "## ⏱️ [Part 2: 时间管理报告]",
            "",
            "### 2.1 时间分配图",
            "",
        ])
        
        activity_breakdown = summary.get('activity_breakdown', {})
        total_seconds = sum(activity_breakdown.values())
        if total_seconds > 0:
            lines.append("```")
            for activity_type, seconds in sorted(activity_breakdown.items(), key=lambda x: x[1], reverse=True):
                percentage = (seconds / total_seconds) * 100
                bar = '█' * int(percentage / 3)
                lines.append(f"{activity_type:8s} {bar:30s} {seconds/3600:5.1f}h ({percentage:4.1f}%)")
            lines.append("```")
            
        lines.extend([
            "",
            "### 2.2 详细时间记录",
            "",
            "| # | 类别 | 时间段 | 时长 | 备注 |",
            "| :-- | :--- | :--- | :--- | :--- |",
        ])
        
        for i, act in enumerate(activities, 1):
            st = str(act.get('start'))
            st = st.split(' ')[1][:5] if ' ' in st else (st.split('T')[1][:5] if 'T' in st else st[:5])
            et = str(act.get('finish'))
            et = et.split(' ')[1][:5] if ' ' in et else (et.split('T')[1][:5] if 'T' in et else et[:5])
            dur = f"{act.get('duration', 0)//3600:02d}:{(act.get('duration', 0)%3600)//60:02d}"
            lines.append(f"| {i} | {act.get('type')} | {st} - {et} | {dur} | {act.get('comment', '')} |")

    lines.extend([
        "",
        "---",
        "",
        "## 💡 深度建议",
        "",
    ])
    for insight in analysis.get('insights', []): lines.append(f"- {insight}")
    for rec in analysis.get('recommendations', []): lines.append(f"- {rec}")

    lines.append(f"\n\n---\n*Generated by MyTimeLogger v4.2*")

    report_path = generate_report_filename(date_str)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return str(report_path)

def generate_report_filename(date_str):
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    weekday_cn = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][date_obj.weekday()]
    week_number = date_obj.isocalendar()[1]
    filename = f"{date_str} {weekday_cn} w{week_number:02d}.md"
    reports_dir = os.path.join(project_root, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return os.path.join(reports_dir, filename)

if __name__ == '__main__':
    d_str = sys.argv[1] if len(sys.argv) > 1 else (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    generate_comprehensive_report(d_str)
