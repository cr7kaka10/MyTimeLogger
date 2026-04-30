#!/usr/bin/env python3
"""
生成完整的时间管理分析报告
结合 aTimeLogger 和华为运动健康数据
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.atimelogger_extractor import AtimeloggerExtractor
from modules.ai_analyzer import AIAnalyzer
from modules.report_generator import ReportGenerator
from modules.screenshot_parser import ScreenshotParser
import json
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path

# 工作空间根目录
WORKSPACE_ROOT = r"D:\WorkBuddySpace\000"

def generate_comprehensive_report(date_str):
    """生成综合分析报告"""
    
    print(f"\n{'='*70}")
    print(f"📊 生成 {date_str} 完整时间管理分析报告")
    print(f"{'='*70}\n")
    
    # 1. 加载配置
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 2. 提取 aTimeLogger 数据
    print("📱 提取 aTimeLogger 数据...")
    atimelogger = AtimeloggerExtractor(config.get('atimelogger', {}))
    atimelogger_data = atimelogger.extract_daily_data(date_str)
    
    if not atimelogger_data:
        print(f"❌ 未获取到 {date_str} 的 aTimeLogger 数据")
        return None
    
    print(f"✅ 获取到 {len(atimelogger_data.get('activities', []))} 条时间记录")
    
    # 3. 加载华为健康睡眠数据
    print("\n⌚ 加载华为运动健康睡眠数据...")
    sleep_data = None
    sleep_file = os.path.join(WORKSPACE_ROOT, 'huawei_health_data', f'sleep_{date_str}.json')
    
    if os.path.exists(sleep_file):
        with open(sleep_file, 'r', encoding='utf-8') as f:
            sleep_data = json.load(f)
        print(f"✅ 已加载睡眠数据")
        
        # 4. 重新计算清醒时长
        print("\n🧮 计算睡眠数据...")
        parser = ScreenshotParser()
        awake_time = parser._calculate_awake_time(sleep_data)
        sleep_data['awake_time'] = awake_time
        print(f"  清醒时长: {awake_time / 60:.0f} 分钟")
        
        # 5. 计算入睡用时和醒来用时
        activities = atimelogger_data.get('activities', [])
        fall_asleep_min, wake_up_min = parser.calculate_sleep_transition_times(sleep_data, activities)
        
        # 更新睡眠数据
        if fall_asleep_min > 0:
            sleep_data['fall_asleep_time'] = fall_asleep_min
            print(f"  入睡需要的时间: {fall_asleep_min} 分钟")
        if wake_up_min > 0:
            sleep_data['wake_up_time'] = wake_up_min
            print(f"  起床需要的时间: {wake_up_min} 分钟")
        
        # 保存更新后的睡眠数据
        with open(sleep_file, 'w', encoding='utf-8') as f:
            json.dump(sleep_data, f, ensure_ascii=False, indent=2)
    else:
        print(f"⚠️ 未找到睡眠数据文件: {sleep_file}")
    
    # 4. 合并数据
    print("\n🔄 合并数据...")
    combined_data = combine_data(atimelogger_data, sleep_data, date_str)
    
    # 5. AI 深度分析
    print("\n🤖 进行 AI 深度分析...")
    ai_analysis = perform_deep_analysis(combined_data)
    
    # 6. 生成完整报告
    print("\n📝 生成完整报告...")
    report_path = generate_full_report_file(combined_data, ai_analysis, date_str)
    
    print(f"\n{'='*70}")
    print(f"✅ 报告生成完成!")
    print(f"📄 报告路径: {report_path}")
    print(f"{'='*70}\n")
    
    return report_path

def combine_data(atimelogger_data, sleep_data, date_str):
    """合并 aTimeLogger 和睡眠数据"""
    
    activities = atimelogger_data.get('activities', [])
    
    # 计算时间统计
    type_durations = defaultdict(int)
    total_duration = 0
    
    for activity in activities:
        activity_type = activity['type']
        duration = activity['duration']
        type_durations[activity_type] += duration
        total_duration += duration
    
    combined = {
        'date': date_str,
        'atimelogger': atimelogger_data,
        'sleep': sleep_data,
        'summary': {
            'total_tracked_time': total_duration,
            'activity_breakdown': dict(type_durations),
            'total_activities': len(activities)
        }
    }
    
    # 添加睡眠对比数据
    if sleep_data:
        night_sleep_duration = sleep_data.get('night_sleep_duration', 0)
        atimelogger_sleep = type_durations.get('睡觉', 0)
        
        combined['summary']['sleep_comparison'] = {
            'huawei_sleep_duration': night_sleep_duration,
            'atimelogger_sleep_duration': atimelogger_sleep,
            'difference': abs(night_sleep_duration - atimelogger_sleep),
            'sleep_score': sleep_data.get('sleep_score'),
            'sleep_cycles': sleep_data.get('sleep_cycles'),
            'awake_time': sleep_data.get('awake_time'),
            'awake_count': sleep_data.get('awake_count')
        }
    
    return combined

def perform_deep_analysis(data):
    """执行深度 AI 分析"""
    
    summary = data.get('summary', {})
    sleep = data.get('sleep', {})
    activities = data.get('atimelogger', {}).get('activities', [])
    
    # 基础统计
    total_hours = summary.get('total_tracked_time', 0) / 3600
    activity_breakdown = summary.get('activity_breakdown', {})
    
    # 各类时间统计
    productive_hours = activity_breakdown.get('生产', 0) / 3600
    entertainment_hours = activity_breakdown.get('娱乐', 0) / 3600
    squirrel_hours = activity_breakdown.get('松鼠病', 0) / 3600
    family_hours = activity_breakdown.get('家庭', 0) / 3600
    sleep_hours = activity_breakdown.get('睡觉', 0) / 3600
    
    # 睡眠分析
    sleep_analysis = {}
    if sleep:
        night_sleep_duration = sleep.get('night_sleep_duration_min', 0) / 60
        sleep_score = sleep.get('sleep_score', 0)
        awake_count = sleep.get('awake_count', 0)
        sleep_cycles = sleep.get('sleep_cycles', 0)
        
        sleep_analysis = {
            'duration_status': '充足' if night_sleep_duration >= 7 else '不足' if night_sleep_duration < 6 else '正常',
            'quality_status': '优秀' if sleep_score >= 85 else '良好' if sleep_score >= 70 else '一般' if sleep_score >= 60 else '较差',
            'continuity_status': '良好' if awake_count <= 1 else '一般' if awake_count <= 3 else '较差',
            'cycles_status': '✅ 合格' if sleep_cycles >= 5 else '⚠️ 接近合格' if sleep_cycles >= 4 else '❌ 不足'
        }
    
    # 生成洞察
    insights = []
    
    # 睡眠洞察
    if sleep:
        if night_sleep_duration < 6:
            insights.append(f"⚠️ 睡眠时间严重不足（{night_sleep_duration:.1f}小时），长期睡眠不足会影响身体健康和认知功能")
        elif night_sleep_duration < 7:
            insights.append(f"⚡ 睡眠时间偏少（{night_sleep_duration:.1f}小时），建议增加30-60分钟睡眠")
        
        if awake_count > 3:
            insights.append(f"⚠️ 夜间清醒次数较多（{awake_count}次），睡眠质量一般，易醒问题明显")
        
        if sleep_score < 70:
            insights.append(f"📉 睡眠评分偏低（{sleep_score}分），建议改善睡眠环境和习惯")
        
        # 入睡时间分析
        fall_asleep_time = sleep.get('fall_asleep_time', 0)
        if fall_asleep_time > 30:
            insights.append(f"🐢 入睡时间较长（{fall_asleep_time}分钟），可能存在入睡困难，建议睡前放松或减少屏幕时间")
        elif fall_asleep_time > 0:
            insights.append(f"😴 入睡时间正常（{fall_asleep_time}分钟），上床后能较快入睡")
        
        # 醒来时间分析
        wake_up_time = sleep.get('wake_up_time', 0)
        if wake_up_time > 20:
            insights.append(f"🛏️ 醒来需要的时间较长（{wake_up_time}分钟），醒来后赖床时间较长，建议设定闹钟后立刻起床")
        elif wake_up_time > 0:
            insights.append(f"☀️ 醒来效率良好（{wake_up_time}分钟），醒来后能快速起床")
    
    # 生产时间洞察
    if productive_hours < 1:
        insights.append(f"⏰ 生产时间极少（{productive_hours:.1f}小时），严重缺乏专注工作时间")
    elif productive_hours < 2:
        insights.append(f"📊 生产时间较少（{productive_hours:.1f}小时），建议每天至少专注工作2小时")
    elif productive_hours > 4:
        insights.append(f"🎯 生产时间充足（{productive_hours:.1f}小时），效率较高")
    
    # 松鼠病洞察
    if squirrel_hours > 3:
        insights.append(f"🐿️ 松鼠病时间较长（{squirrel_hours:.1f}小时），注意力严重分散，建议减少干扰")
    elif squirrel_hours > 1.5:
        insights.append(f"⚡ 松鼠病时间（{squirrel_hours:.1f}小时）影响工作效率，建议使用番茄工作法")
    
    # 娱乐时间洞察
    if entertainment_hours > 3:
        insights.append(f"🎮 娱乐时间较长（{entertainment_hours:.1f}小时），可适当减少以平衡时间分配")
    
    # 时间追踪完整性
    if total_hours < 20:
        insights.append(f"📋 时间追踪不完整（仅{total_hours:.1f}小时），建议更全面地记录时间")
    
    # 生成建议
    recommendations = []
    
    if sleep and night_sleep_duration < 7:
        recommendations.append("🛏️ 提前30分钟上床，建立规律的睡眠时间表")
    
    if sleep and awake_count > 2:
        recommendations.append("😴 睡前避免使用电子设备，尝试白噪音或冥想改善睡眠质量")
    
    # 入睡时间建议
    fall_asleep_time = sleep.get('fall_asleep_time', 0) if sleep else 0
    if fall_asleep_time > 30:
        recommendations.append("🌙 入睡困难建议：睡前1小时停止使用电子设备，尝试阅读纸质书或冥想")
    elif fall_asleep_time > 20:
        recommendations.append("📖 尝试建立睡前仪式（如泡脚、拉伸），帮助更快进入睡眠状态")
    
    # 醒来时间建议
    wake_up_time = sleep.get('wake_up_time', 0) if sleep else 0
    if wake_up_time > 20:
        recommendations.append("⏰ 建议将闹钟放在离床较远的地方，强迫自己起床关闭闹钟")
    elif wake_up_time > 10:
        recommendations.append("☀️ 醒来后立即拉开窗帘接触自然光，有助于快速清醒")
    
    if productive_hours < 2:
        recommendations.append("🍅 使用番茄工作法（25分钟专注+5分钟休息），每天完成4-6个番茄")
    
    if squirrel_hours > 1:
        recommendations.append("🚫 工作时关闭手机通知，使用专注模式减少干扰")
    
    if not recommendations:
        recommendations.append("🌟 时间管理良好，继续保持！")
    
    # 计算效率评分
    efficiency_score = calculate_efficiency_score(
        productive_hours, 
        night_sleep_duration if sleep else 0, 
        squirrel_hours, 
        entertainment_hours,
        awake_count if sleep else 0
    )
    
    return {
        'date': data.get('date'),
        'summary': {
            'total_activities': len(activities),
            'total_tracked_hours': round(total_hours, 1),
            'productive_hours': round(productive_hours, 1),
            'entertainment_hours': round(entertainment_hours, 1),
            'squirrel_hours': round(squirrel_hours, 1),
            'family_hours': round(family_hours, 1),
            'sleep_hours': round(sleep_hours, 1),
            'efficiency_score': efficiency_score
        },
        'sleep_analysis': sleep_analysis,
        'insights': insights,
        'recommendations': recommendations,
        'activity_breakdown': activity_breakdown
    }

def calculate_efficiency_score(productive, sleep, squirrel, entertainment, awake_count):
    """计算效率评分"""
    score = 50
    
    # 生产时间加分
    if productive >= 4:
        score += 20
    elif productive >= 2:
        score += 10
    elif productive >= 1:
        score += 5
    
    # 睡眠时间加分
    if 7 <= sleep <= 9:
        score += 15
    elif 6 <= sleep < 7:
        score += 5
    
    # 松鼠病减分
    if squirrel > 3:
        score -= 15
    elif squirrel > 2:
        score -= 10
    elif squirrel > 1:
        score -= 5
    
    # 娱乐时间减分
    if entertainment > 4:
        score -= 10
    elif entertainment > 3:
        score -= 5
    
    # 清醒次数减分
    if awake_count > 3:
        score -= 10
    elif awake_count > 1:
        score -= 5
    
    return max(0, min(100, score))

def generate_full_report_file(data, analysis, date_str):
    """生成完整报告文件"""
    
    atimelogger = data.get('atimelogger', {})
    sleep = data.get('sleep', {})
    summary = data.get('summary', {})
    
    activities = atimelogger.get('activities', [])
    
    lines = [
        f"# 📊 时间管理深度分析报告 - {date_str}",
        "",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**分析日期**: {date_str}",
        "",
        "---",
        "",
        "## 📈 执行摘要",
        "",
        f"**效率评分**: {analysis['summary']['efficiency_score']}/100",
        "",
        "### 核心指标",
        "",
        "| 指标 | 数值 | 评价 |",
        "|------|------|------|",
    ]
    
    # 添加核心指标
    summary_data = analysis['summary']
    lines.append(f"| 时间记录总数 | {summary_data['total_activities']} 条 | - |")
    lines.append(f"| 总追踪时长 | {summary_data['total_tracked_hours']:.1f} 小时 | {'完整' if summary_data['total_tracked_hours'] >= 20 else '不完整'} |")
    lines.append(f"| 生产时间 | {summary_data['productive_hours']:.1f} 小时 | {'充足' if summary_data['productive_hours'] >= 2 else '不足'} |")
    lines.append(f"| 娱乐时间 | {summary_data['entertainment_hours']:.1f} 小时 | {'正常' if summary_data['entertainment_hours'] <= 3 else '偏多'} |")
    lines.append(f"| 松鼠病时间 | {summary_data['squirrel_hours']:.1f} 小时 | {'正常' if summary_data['squirrel_hours'] <= 1 else '偏多'} |")
    lines.append(f"| 家庭时间 | {summary_data['family_hours']:.1f} 小时 | - |")
    
    if sleep:
        night_sleep_hours = sleep.get('night_sleep_duration_min', 0) / 60
        sleep_score = sleep.get('sleep_score', 'N/A')
        sleep_cycles = sleep.get('sleep_cycles', 0)
        awake_time = sleep.get('awake_time', 0) / 60  # 转换为分钟
        fall_asleep_time = sleep.get('fall_asleep_time', 0)
        wake_up_time = sleep.get('wake_up_time', 0)
        
        lines.append(f"| 夜间睡眠 | {night_sleep_hours:.1f} 小时 | {'充足' if night_sleep_hours >= 7 else '不足' if night_sleep_hours < 6 else '正常'} |")
        lines.append(f"| 睡眠评分 | {sleep_score} 分 | {'优秀' if sleep_score >= 85 else '良好' if sleep_score >= 70 else '一般'} |")
        lines.append(f"| 睡眠周期数 | {sleep_cycles:.1f} 个 | {'✅ 合格' if sleep_cycles >= 5 else '⚠️ 接近合格' if sleep_cycles >= 4 else '❌ 不足'} |")
        lines.append(f"| 清醒时长 | {awake_time:.0f} 分钟 | {'✅ 正常' if awake_time <= 20 else '⚠️ 略长' if awake_time <= 40 else '❌ 过长'} |")
        # 入睡用时评价（支持负数）
        if fall_asleep_time < 0:
            fall_asleep_eval = "⚠️ 延迟入睡"
        elif fall_asleep_time <= 20:
            fall_asleep_eval = "✅ 正常"
        elif fall_asleep_time <= 40:
            fall_asleep_eval = "⚠️ 较长"
        else:
            fall_asleep_eval = "❌ 过长"
        
        # 醒来用时评价（支持负数）
        if wake_up_time < 0:
            wake_up_eval = "✅ 早起"
        elif wake_up_time <= 10:
            wake_up_eval = "✅ 正常"
        elif wake_up_time <= 20:
            wake_up_eval = "⚠️ 较长"
        else:
            wake_up_eval = "❌ 过长"
        
        lines.append(f"| 入睡用时 | {fall_asleep_time} 分钟 | {fall_asleep_eval} |")
        lines.append(f"| 醒来用时 | {wake_up_time} 分钟 | {wake_up_eval} |")
    
    lines.extend([
        "",
        "---",
        "",
        "## 🛏️ 睡眠分析",
        "",
    ])
    
    if sleep:
        sleep_analysis = analysis.get('sleep_analysis', {})
        
        lines.extend([
            "### 睡眠数据概览",
            "",
            "| 指标 | 数值 | 状态 |",
            "|------|------|------|",
            f"| 入睡时间 | {sleep.get('sleep_start', 'N/A')} | - |",
            f"| 醒来时间 | {sleep.get('sleep_end', 'N/A')} | - |",
            f"| 夜间睡眠 | {sleep.get('night_sleep_duration_min', 0)/60:.1f} 小时 | {sleep_analysis.get('duration_status', 'N/A')} |",
            f"| 深睡时长 | {sleep.get('deep_sleep', 0)/60:.0f} 分钟 | - |",
            f"| 浅睡时长 | {sleep.get('light_sleep', 0)/60:.0f} 分钟 | - |",
            f"| REM睡眠 | {sleep.get('rem_sleep', 0)/60:.0f} 分钟 | - |",
            f"| 清醒时长 | {sleep.get('awake_time', 0)/60:.0f} 分钟 | - |",
            f"| 清醒次数 | {sleep.get('awake_count', 0)} 次 | {sleep_analysis.get('continuity_status', 'N/A')} |",
            f"| 睡眠评分 | {sleep.get('sleep_score', 'N/A')} 分 | {sleep_analysis.get('quality_status', 'N/A')} |",
            f"| 睡眠周期 | {sleep.get('sleep_cycles', 0):.1f} 个 | {'✅ 合格' if sleep.get('sleep_cycles', 0) >= 5 else '⚠️ 接近合格' if sleep.get('sleep_cycles', 0) >= 4 else '❌ 不足'} |",
            f"| 入睡用时 | {sleep.get('fall_asleep_time', 0)} 分钟 | {'⚠️ 延迟入睡' if sleep.get('fall_asleep_time', 0) < 0 else '✅ 正常' if sleep.get('fall_asleep_time', 0) <= 20 else '⚠️ 较长' if sleep.get('fall_asleep_time', 0) <= 40 else '❌ 过长'} |",
            f"| 醒来用时 | {sleep.get('wake_up_time', 0)} 分钟 | {'✅ 早起' if sleep.get('wake_up_time', 0) < 0 else '✅ 正常' if sleep.get('wake_up_time', 0) <= 10 else '⚠️ 较长' if sleep.get('wake_up_time', 0) <= 20 else '❌ 过长'} |",
            "",
            "### 睡眠质量评估",
            "",
        ])
        
        # 添加睡眠分析
        if sleep.get('analysis'):
            sleep_ana = sleep.get('analysis', {})
            if sleep_ana.get('summary'):
                lines.append(f"**总结**: {sleep_ana['summary']}")
                lines.append("")
            
            if sleep_ana.get('issues'):
                lines.append("**存在的问题**:")
                for issue in sleep_ana['issues']:
                    lines.append(f"- ⚠️ {issue}")
                lines.append("")
            
            if sleep_ana.get('suggestions'):
                lines.append("**改善建议**:")
                for suggestion in sleep_ana['suggestions']:
                    lines.append(f"- 💡 {suggestion}")
                lines.append("")
    else:
        lines.append("*未获取到睡眠数据*")
    
    lines.extend([
        "",
        "---",
        "",
        "## ⏱️ 时间使用分析",
        "",
        "### 时间分配",
        "",
    ])
    
    # 添加时间分配图表
    activity_breakdown = analysis.get('activity_breakdown', {})
    total_seconds = sum(activity_breakdown.values())
    
    if total_seconds > 0:
        lines.append("```")
        for activity_type, seconds in sorted(
            activity_breakdown.items(), 
            key=lambda x: x[1], 
            reverse=True
        ):
            percentage = (seconds / total_seconds) * 100
            bar_length = int(percentage / 2)
            bar = '█' * bar_length
            hours = seconds / 3600
            lines.append(f"{activity_type:8s} {bar:50s} {hours:5.1f}h ({percentage:5.1f}%)")
        lines.append("```")
    
    lines.extend([
        "",
        "### 详细时间记录",
        "",
        "| 序号 | 类别 | 开始时间 | 结束时间 | 时长 | 备注 |",
        "|------|------|----------|----------|------|------|",
    ])
    
    for i, activity in enumerate(activities, 1):
        start = activity.get('start', '')
        finish = activity.get('finish', '')
        
        if hasattr(start, 'strftime'):
            start_str = start.strftime('%H:%M')
        else:
            start_str = str(start)
        
        if hasattr(finish, 'strftime'):
            finish_str = finish.strftime('%H:%M')
        else:
            finish_str = str(finish)
        
        duration = activity.get('duration', 0)
        duration_str = f"{duration // 3600:02d}:{(duration % 3600) // 60:02d}"
        
        comment = activity.get('comment', '')
        if comment is None:
            comment = ''
        
        lines.append(
            f"| {i} | {activity.get('type', '未知')} | "
            f"{start_str} | {finish_str} | {duration_str} | {comment} |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## 💡 深度洞察",
        "",
    ])
    
    for i, insight in enumerate(analysis.get('insights', []), 1):
        lines.append(f"{i}. {insight}")
    
    if not analysis.get('insights'):
        lines.append("暂无特别洞察")
    
    lines.extend([
        "",
        "---",
        "",
        "## 🎯 行动建议",
        "",
    ])
    
    for i, rec in enumerate(analysis.get('recommendations', []), 1):
        lines.append(f"{i}. {rec}")
    
    if not analysis.get('recommendations'):
        lines.append("继续保持良好的时间管理习惯！")
    
    lines.extend([
        "",
        "---",
        "",
        "## 📊 数据对比",
        "",
    ])
    
    # 添加睡眠数据对比
    sleep_comparison = summary.get('sleep_comparison', {})
    if sleep_comparison:
        lines.extend([
            "### aTimeLogger vs 华为健康睡眠数据",
            "",
            "| 来源 | 睡眠时长 | 差异 |",
            "|------|----------|------|",
            f"| aTimeLogger | {sleep_comparison.get('atimelogger_sleep_duration', 0)/3600:.1f} 小时 | - |",
            f"| 华为健康 | {sleep_comparison.get('huawei_sleep_duration', 0)/3600:.1f} 小时 | - |",
            f"| 差异 | - | {sleep_comparison.get('difference', 0)/3600:.1f} 小时 |",
            "",
            "**说明**: aTimeLogger 记录的是主观感受的睡眠时间，华为健康是通过设备监测的实际睡眠数据。",
            "",
        ])
    
    lines.extend([
        "---",
        "",
        f"*报告由时间管理技能自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ])
    
    # 写入文件 - 新格式：YYYY-MM-DD ddd [w]ww.md
    report_path = generate_report_filename(date_str)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    return str(report_path)


def generate_report_filename(date_str):
    """
    生成报告文件名，格式：YYYY-MM-DD 周x wWW.md
    例如：2026-01-01 周四 w01.md
    
    Args:
        date_str: 日期字符串 (YYYY-MM-DD)
        
    Returns:
        Path: 完整的报告文件路径
    """
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    
    # 星期几中文名称
    weekday_names = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    weekday_cn = weekday_names[date_obj.weekday()]
    
    # 计算周数（ISO周数）
    week_number = date_obj.isocalendar()[1]
    
    # 生成文件名：YYYY-MM-DD 周x wWW.md
    filename = f"{date_str} {weekday_cn} w{week_number:02d}.md"
    
    # 完整路径
    report_path = Path(WORKSPACE_ROOT) / filename
    
    return report_path

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        date_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    generate_comprehensive_report(date_str)
