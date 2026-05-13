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
import httpx
from openai import OpenAI

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
    
    # 1. 提取 aTimeLogger 数据
    atimelogger_data = None
    # 核心改进：只要有睡眠数据注入（正在进行 AI 分析），就必须拉取 aTimeLogger 以计算入睡/起床用时
    need_atm = include_time_analysis or (injected_sleep_data is not None)
    
    if need_atm:
        if db and not force_pull and include_time_analysis:
            atimelogger_data = db.get_atm_data(date_str)
        
        if not atimelogger_data:
            extractor = AtimeloggerExtractor(config.get('atimelogger', {}))
            atimelogger_data = extractor.extract_daily_data(date_str)
            # 仅在完整模式下才落库保存 aTimeLogger
            if atimelogger_data and db and include_time_analysis:
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

        # ====== 核心步骤: 数据计算 (Data Calculation) ======
        # 强制按公式计算派生指标，确保逻辑一致
        try:
            print("[数据计算] 正在根据原始数据计算派生指标...")
            s_t = sleep_data.get('sleep_start')
            e_t = sleep_data.get('sleep_end')
            t_min = float(sleep_data.get('total_sleep_min', 0))
            
            if s_t and e_t:
                sh, sm = map(int, s_t.split(':'))
                eh, em = map(int, e_t.split(':'))
                start_total = sh * 60 + sm
                end_total = eh * 60 + em
                if end_total < start_total: 
                    end_total += 24 * 60
                
                # 1. 总在床时长
                in_bed_min = end_total - start_total
                # 2. 清醒时长 = 总在床时长 - 夜间睡眠时长 (total_sleep_min)
                sleep_data['awake_min'] = max(0, in_bed_min - t_min)
                
            # 3. 睡眠周期 = 夜间睡眠时长 / 90
            if t_min > 0:
                sleep_data['sleep_cycles'] = round(t_min / 90.0, 2)
                
        except Exception as e:
            print(f"  [数据计算] 异常: {e}")
        # ====================================================

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
    """
    根据 SKILL.md 的指导思想，调用文本大模型进行深度复盘。
    如果没有配置 AI，则回退到基础统计逻辑。
    """
    import json
    import os
    
    # 1. 尝试加载 AI 配置
    config = {}
    try:
        # 定位到根目录的 config.json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(os.path.dirname(current_dir))
        cfg_path = os.path.join(root_dir, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                config = json.load(f).get("ai_model_config", {})
    except: pass
    
    # 2. 从 SKILL.md 读取分析指令
    prompt_tpl = ""
    try:
        skill_path = os.path.join(os.path.dirname(__file__), "SKILL.md")
        if os.path.exists(skill_path):
            with open(skill_path, "r", encoding="utf-8") as f:
                content = f.read()
                if "```analysis_prompt" in content:
                    prompt_tpl = content.split("```analysis_prompt")[1].split("```")[0].strip()
    except: pass
    
    # 3. 如果有 AI 配置且有提示词，发起请求
    api_key = config.get("text_api_key")
    if api_key and prompt_tpl:
        try:
            base_url = config.get("text_base_url")
            model = config.get("text_model", "glm-4-flash")
            
            # 准备脱敏数据
            input_data = {
                "sleep_metrics": data.get("sleep", {}),
                "time_stats": data.get("summary", {})
            }
            
            client = OpenAI(api_key=api_key, base_url=base_url, http_client=httpx.Client(verify=False))
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": prompt_tpl},
                    {"role": "user", "content": f"请基于以下数据生成分析结果：\n{json.dumps(input_data, ensure_ascii=False)}"}
                ],
                temperature=0.7,
                # 某些模型支持 json_object，不支持的也会因为 prompt 要求返回 JSON
            )
            
            content = resp.choices[0].message.content
            if not content:
                raise Exception("大模型返回分析内容为空")
            raw_content = content.strip()
            # 清理可能的 markdown 标签
            if "```json" in raw_content:
                raw_content = raw_content.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_content:
                raw_content = raw_content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(raw_content)
            print(f"✅ AI 深度分析完成 (Model: {model})")
            return result
        except Exception as e:
            print(f"⚠️ AI 分析调用失败，回退到基础逻辑: {e}")

    # 4. 基础兜底逻辑 (计算得分)
    activity_breakdown = data.get('summary', {}).get('activity_breakdown', {})
    productive_hrs = activity_breakdown.get('生产', 0) / 3600
    sleep_score = data.get('sleep', {}).get('sleep_score', 0)
    
    score = 60
    if productive_hrs > 3: score += 20
    if sleep_score > 80: score += 20
    
    return {
        'efficiency_score': min(100, score),
        'summary': "今天表现不错，继续保持！" if score >= 80 else "还有提升空间，加油！",
        'insights': ["保持专注是提升效率的关键。", "合理的睡眠能显著提升次日状态。"],
        'recommendations': ["建议睡前 1 小时放下手机。", "明天尝试增加一个番茄钟的生产时间。"],
        'issues': ["睡眠时长略显不足"] if sleep_score < 70 else []
    }

def generate_full_report_file(data, analysis, date_str, include_time_analysis=True):
    """生成完整报告文件"""
    sleep = data.get('sleep', {})
    summary = data.get('summary', {})
    activities = data.get('atimelogger', {}).get('activities', []) if data.get('atimelogger') else []
    
    model_info = sleep.get('extracted_by', '未知模型')
    lines = [
        f"# 📔 深度复盘报告 - {date_str}",
        "",
        f"> **生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | **解析模型**: `{model_info}`",
        "",
        "---",
        "",
        "## 📈 [复盘摘要]",
        "",
        f"**效率评分**: `{analysis.get('efficiency_score', '--')}` / 100",
        f"**今日总结**: {analysis.get('summary', '数据已汇总')}",
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
            f"| 🔄 **睡眠周期** | {format_val(sleep.get('sleep_cycles', 0))} 个 | {'✅ 达标' if float(sleep.get('sleep_cycles',0)) >= 5 else '⚠️ 略少'} |",
            f"| 💤 **深睡时长** | {sleep.get('deep_sleep_min', '--')} min | {'参考: 60-120' if float(sleep.get('deep_sleep_min',0)) > 0 else '-'} |",
            f"| 🌙 **入睡用时** | {sleep.get('fall_asleep_min', '--')} min | {'✅ 极快' if float(sleep.get('fall_asleep_min',0)) < 20 else '正常'} |",
            f"| ☀️ **起床用时** | {sleep.get('wake_up_min', '--')} min | {'✅ 迅速' if float(sleep.get('wake_up_min',0)) < 15 else '赖床'} |",
            f"| 😲 **清醒次数** | {sleep.get('awake_count', '--')} 次 | {'优秀' if int(sleep.get('awake_count',0)) <= 1 else '正常'} |",
            f"| ☕ **清醒时长** | {sleep.get('awake_min', '--')} min | {'参考: < 15' if float(sleep.get('awake_min',0)) > 0 else '-'} |",
            f"| 📉 **深睡比例** | {sleep.get('deep_sleep_ratio', '--')} % | {'20%-60% 达标' if sleep.get('deep_sleep_ratio') else '-'} |",
            f"| 🕯️ **浅睡时长** | {sleep.get('light_sleep_min', '--')} min | {'参考: 20%-60%' if sleep.get('light_sleep_min') else '-'} |",
            f"| 🌀 **REM时长** | {sleep.get('rem_sleep_min', '--')} min | {'参考: 10%-30%' if sleep.get('rem_sleep_min') else '-'} |",
            f"| 📊 **浅睡比例** | {sleep.get('light_sleep_ratio', '--')} % | - |",
            f"| 📈 **REM比例** | {sleep.get('rem_sleep_ratio', '--')} % | - |",
            f"| 🔗 **睡眠连续性** | {sleep.get('sleep_continuity', '--')} 分 | {'> 70 分' if sleep.get('sleep_continuity') else '-'} |",
            f"| 🫁 **呼吸质量** | {sleep.get('breathing_score', '--')} 分 | {'> 90 分' if sleep.get('breathing_score') else '-'} |",
            f"| 🛌 **入睡时刻** | {sleep.get('sleep_start', '--')} | - |",
            f"| ⏰ **醒来时刻** | {sleep.get('sleep_end', '--')} | - |",
            f"| 🕒 **总时长** | {format_val(float(sleep.get('total_sleep_min', 0))/60)} 小时 | {'✅ 达标' if float(sleep.get('total_sleep_min',0)) >= 420 else '⚠️ 偏少'} |",
            f"| 📊 **睡眠评分** | {sleep.get('sleep_score', '--')} 分 | {'优秀' if int(sleep.get('sleep_score',0)) >= 85 else '良好'} |",
            f"| 📅 **记录日期** | {date_str} | - |",
            "",
            "### 1.2 睡眠自我评价",
        ])
        
        refl = sleep.get('sleep_reflection', '').strip()
        lines.append(f"> {refl if refl else '*今日未记录主观评价*'}")
        
        interp = sleep.get('analysis_report', '').strip()
        
        lines.extend([
            "",
            "### 1.3 华为健康建议",
            f"> {interp if interp else '暂无官方建议'}",
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

    # AI 深度建议 (Insight & Recommendations)
    lines.extend([
        "",
        "---",
        "",
        "## 💡 [AI 深度洞察]",
        "",
    ])
    for insight in analysis.get('insights', []):
        lines.append(f"**{insight}**" if insight.startswith('⚠️') else f"- {insight}")
        
    lines.extend([
        "",
        "### 🎯 行动建议",
        "",
    ])
    for rec in analysis.get('recommendations', []):
        lines.append(f"- {rec}")

    # 增加问题点提示
    issues = analysis.get('issues', [])
    if issues:
        lines.extend([
            "",
            "### ⚠️ 核心问题点",
            "",
        ])
        for issue in issues:
            lines.append(f"- {issue}")

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
