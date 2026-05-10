---
name: time-management
description: |
  时间管理技能 - 整合 aTimeLogger 时间记录和华为运动健康睡眠数据，生成深度分析报告。
  该技能用于自动化收集、分析时间使用数据，提供AI洞察和改善建议。
  **核心工作流程**：用户只需上传一张华为运动健康睡眠截图，大模型自动提取图片数据 → 写入文件 → 提取aTimeLogger数据 → 生成完整报告。
  当用户需要分析时间使用情况、生成日报、或整合睡眠数据时应使用此技能。
---

# 时间管理技能

## 核心设计理念

**唯一输入**：用户上传的华为运动健康睡眠截图

**自动化流程**：
1. 大模型直接读取截图，提取睡眠数据
2. 将数据写入 `D:\WorkBuddySpace\000\huawei_health_data\sleep_YYYY-MM-DD.json`
3. 提取对应日期的 aTimeLogger 数据
4. 计算入睡/醒来时间
5. 生成完整的时间管理分析报告

## 使用场景

该技能应在以下场景使用：
- 用户上传了华为运动健康睡眠截图
- 用户说"生成时间管理报告"、"分析我的时间"或"生成日报"
- 需要整合时间记录和睡眠数据进行综合分析

## 工作流程（最重要）

### 步骤1: 大模型直接读取截图

**关键**：当用户上传华为运动健康截图时，大模型（当前对话的AI）**可以直接读取和理解图片内容**，无需OCR！

大模型应直接从图片中提取以下数据：
- 日期（如：3月20日 周五 或 2026-03-20）
- 入睡时间（如：00:20）
- 醒来时间（如：07:07）
- 夜间睡眠时长（如：6小时2分钟）
- 深睡时长（如：1小时34分钟）
- 浅睡时长（如：2小时51分钟）
- REM睡眠/快速眼动时长（如：1小时37分钟）
- 清醒次数（如：4次）
- 睡眠评分（如：74分）
- 深睡比例、浅睡比例、REM比例（如：26%、47%、27%）
- 深睡连续性评分、呼吸质量评分（如：70分、98分）
- 解读与建议（如果有）

### 步骤2: 计算清醒时长和睡眠周期数

### 睡眠周期数

```
睡眠周期 = 睡眠总时长(分钟) / 90
```

### 清醒时长

清醒时长是指睡眠过程中清醒状态的总时长（不包括入睡前和起床后的清醒时间）。

**计算公式**:
```
清醒时长 = 总在床时间 - 夜间睡眠时长
其中：总在床时间 = 醒来时间 - 入睡时间
```

**注意**:
- 夜间睡眠时长来自华为健康睡眠监测，等于深睡+浅睡+REM，不包含清醒时间
- 清醒时长来自华为健康睡眠监测，表示睡眠过程中醒来但未起床的时间
- 如果清醒次数 > 0 但清醒时长显示为0，可能是清醒时间太短（<1分钟）未被记录
- 典型的清醒时长范围：0-30分钟

### 步骤3: 保存睡眠数据

将提取的睡眠数据保存到 JSON 文件：
- 文件路径：`D:\WorkBuddySpace\000\huawei_health_data\sleep_{date}.json`
- 数据格式见下方"数据结构"部分

### 步骤4: 提取 aTimeLogger 数据

根据截图日期，使用 AtimeloggerExtractor 提取对应日期的时间记录：
- 查找日期对应的活动记录
- 计算入睡用时（华为入睡时间 - aTimeLogger上床时间）
- 计算起床用时（aTimeLogger「睡觉」结束时间 - 华为醒来时间）

### 步骤5: 生成完整报告

调用报告生成模块，输出：
- Markdown 格式报告保存到：`D:\WorkBuddySpace\000\YYYY-MM-DD 周x wWW.md`（例如：`2026-01-01 周四 w01.md`）
- 控制台输出摘要

## 数据结构

### 睡眠数据 (sleep_YYYY-MM-DD.json)

```json
{
  "date": "2026-03-20",
  "sleep_start": "00:20",
  "sleep_end": "07:07",
  "night_sleep_duration": 21720,
  "night_sleep_duration_min": 362.0,
  "deep_sleep": 5640,
  "light_sleep": 10260,
  "rem_sleep": 5820,
  "awake_time": 2700,
  "awake_count": 4,
  "sleep_score": 74,
  "fall_asleep_time": 24,
  "wake_up_time": 98,
  "sleep_cycles": 4.02,
  "deep_sleep_ratio": 26,
  "light_sleep_ratio": 47,
  "rem_sleep_ratio": 27,
  "deep_sleep_continuity": 70,
  "breath_quality": 98,
  "analysis": {
    "summary": "睡眠质量一般...",
    "suggestions": ["建议..."],
    "issues": ["问题..."]
  },
  "raw_text": "原始截图文本（可选）",
  "saved_at": "2026-03-20T10:00:00"
}
```

### 数据字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| date | string | 日期 (YYYY-MM-DD) | "2026-03-20" |
| sleep_start | string | 入睡时间 (HH:MM) | "00:20" |
| sleep_end | string | 醒来时间 (HH:MM)，对应华为健康显示的"醒来"时间 | "07:07" |
| night_sleep_duration | int | 夜间睡眠时长（秒），即华为健康显示的睡眠时长 | 21720 |
| night_sleep_duration_min | float | 夜间睡眠时长（分钟） | 362.0 |
| deep_sleep | int | 深睡时长（秒） | 5640 |
| light_sleep | int | 浅睡时长（秒） | 10260 |
| rem_sleep | int | REM睡眠时长（秒） | 5820 |
| awake_time | int | 清醒时长（秒） | 2700 |
| awake_count | int | 清醒次数 | 4 |
| sleep_score | int | 睡眠评分 (0-100) | 74 |
| fall_asleep_time | int | 入睡需要的时间（分钟） | 24 |
| wake_up_time | int | 起床需要的时间（分钟） | 98 |
| sleep_cycles | float | 睡眠周期数 | 4.02，大于5才合格，这是重点指标 |
| deep_sleep_ratio | int | 深睡比例 (%) | 26 |
| light_sleep_ratio | int | 浅睡比例 (%) | 47 |
| rem_sleep_ratio | int | REM比例 (%) | 27 |
| deep_sleep_continuity | int | 深睡连续性评分 | 70 |
| breath_quality | int | 呼吸质量评分 | 98 |
| analysis | dict | 解读与建议 | {...} |
| raw_text | string | 原始文本（可选） | "..." |
| saved_at | string | 保存时间 | "..." |

## 关键计算公式

### 睡眠周期数
```
睡眠周期 = 睡眠总时长(分钟) / 90
```

### 清醒时长
```
清醒时长 = (华为健康醒来时间 - 华为健康入睡时间) - 夜间睡眠时间
```

### 入睡需要的时间（需要aTimeLogger数据）
```
入睡用时 = 华为健康入睡时间 - aTimeLogger「睡觉」开始时间
```

### 起床需要的时间（需要aTimeLogger数据）
```
起床用时 = aTimeLogger「睡觉」结束时间 - 华为健康醒来时间
```

## 评价标准

### 入睡用时
| 范围 | 评价 |
|------|------|
| ≤20分钟 | 正常 |
| 21-40分钟 | 较长 |
| >40分钟 | 过长 |

### 起床用时
| 范围 | 评价 |
|------|------|
| ≤10分钟 | 正常 |
| 11-20分钟 | 较长 |
| >20分钟 | 过长 |

### 睡眠评分
| 范围 | 评价 |
|------|------|
| ≥85 | 优秀 |
| 70-84 | 良好 |
| 60-69 | 一般 |
| <60 | 较差 |

## 代码使用方式

### 从大模型读取的图片数据生成报告

当大模型已经读取了用户上传的截图并提取了数据后，可以直接调用 Python 脚本生成报告：

```bash
# 使用日期参数
python generate_full_report.py 2026-03-20

# 或使用交互模式
python interactive_report.py
```

### Python 模块调用

```python
from time_management.modules.screenshot_parser import ScreenshotParser
from time_management.modules.atimelogger_extractor import AtimeloggerExtractor

# 1. 解析睡眠数据（如果已经有文本）
parser = ScreenshotParser()
sleep_data = parser.parse_sleep_data(text_content, image_date="2026-03-20")
parser.save_sleep_data(sleep_data)

# 2. 提取 aTimeLogger 数据
atimelogger = AtimeloggerExtractor(config)
atimelogger_data = atimelogger.extract_daily_data("2026-03-20")

# 3. 计算入睡/起床时间
fall_asleep_min, wake_up_min = parser.calculate_sleep_transition_times(sleep_data, activities)

# 4. 生成报告
# 调用 report_generator 模块...
```

## 文件结构

```
time-management/
├── SKILL.md                      # 本文件
├── generate_full_report.py        # 报告生成主程序
├── interactive_report.py         # 交互式报告生成
├── config.json                   # 配置文件
├── modules/
│   ├── atimelogger_extractor.py  # aTimeLogger API 提取
│   ├── screenshot_parser.py      # 睡眠数据解析
│   ├── ai_analyzer.py           # AI 分析
│   ├── report_generator.py      # 报告生成
│   └── wechat_notifier.py       # 微信通知
├── huawei_health_data/          # 睡眠数据存储
│   └── sleep_YYYY-MM-DD.json
└── reports/                      # 报告输出目录
    └── comprehensive_report_YYYY-MM-DD.md
```

## 配置说明

config.json 格式：

```json
{
  "atimelogger": {
    "base_url": "https://app.atimelogger.pro",
    "username": "your_username",
    "password": "your_password"
  },
  "huawei_health": {
    "data_directory": "./huawei_health_data"
  },
  "wechat": {
    "webhook_url": "",
    "enabled": false
  }
}
```

## 重要提示

1. **大模型直接读取图片**：当用户上传华为运动健康截图时，大模型可以直接读取图片内容进行解析，**不需要OCR**
2. **aTimeLogger 账号需要提前配置**：在 config.json 中配置用户名和密码
3. **入睡/起床时间计算需要同时有 aTimeLogger 和华为健康数据**
4. **报告生成后会自动保存到 reports/ 目录**
5. **时间格式处理**：注意跨天情况（如23:00入睡，07:00起床）
