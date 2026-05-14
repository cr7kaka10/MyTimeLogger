#!/usr/bin/env python3
"""
微信通知模块 - 发送微信消息提醒
"""

import requests
import json
from datetime import datetime


class WechatNotifier:
    """微信通知器"""
    
    def __init__(self, config=None):
        """
        初始化微信通知器
        
        Args:
            config: 微信配置字典
                - webhook_url: 企业微信机器人webhook地址
                - enabled: 是否启用通知
        """
        self.config = config or {}
        self.webhook_url = self.config.get('webhook_url', '')
        self.enabled = self.config.get('enabled', False)
    
    def send_message(self, message, msg_type='text'):
        """
        发送微信消息
        
        Args:
            message: 消息内容
            msg_type: 消息类型 (text/markdown)
            
        Returns:
            bool: 是否发送成功
        """
        if not self.enabled:
            print(f"[微信通知已禁用] {message[:50]}...")
            return True
        
        if not self.webhook_url:
            print("[微信通知] 未配置webhook_url")
            return False
        
        try:
            if msg_type == 'markdown':
                data = {
                    "msgtype": "markdown",
                    "markdown": {
                        "content": message
                    }
                }
            else:
                data = {
                    "msgtype": "text",
                    "text": {
                        "content": message
                    }
                }
            
            response = requests.post(
                self.webhook_url,
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    return True
                else:
                    print(f"[微信通知错误] {result}")
                    return False
            else:
                print(f"[微信通知HTTP错误] {response.status_code}")
                return False
                
        except Exception as e:
            print(f"[微信通知异常] {e}")
            return False
    
    def send_reminder(self, date, reminder_type='health_data'):
        """
        发送特定类型的提醒
        
        Args:
            date: 日期字符串
            reminder_type: 提醒类型
            
        Returns:
            bool: 是否发送成功
        """
        if reminder_type == 'health_data':
            message = f"""📊 时间管理提醒

请上传 {date} 的华为运动健康数据

操作步骤：
1️⃣ 打开华为运动健康APP
2️⃣ 进入「睡眠」页面
3️⃣ 截图保存睡眠数据
4️⃣ 上传到指定目录：./huawei_health_data/

⏰ 上传截止时间：23:59
🤖 系统将在00:01自动分析数据"""
            
        elif reminder_type == 'analysis_complete':
            message = f"✅ {date} 的时间管理分析报告已生成，请查看！"
            
        else:
            message = f"📌 提醒：{reminder_type}"
        
        return self.send_message(message)
    
    def send_analysis_summary(self, date, summary, report_path):
        """
        发送分析摘要
        
        Args:
            date: 日期
            summary: 摘要字典
            report_path: 报告路径
            
        Returns:
            bool: 是否发送成功
        """
        message = f"""📊 {date} 时间管理分析报告

【数据概览】
• 时间记录：{summary.get('total_activities', 0)} 条
• 总时长：{summary.get('total_time', 'N/A')}
• 睡眠：{summary.get('sleep_time', 'N/A')}
• 生产：{summary.get('productive_time', 'N/A')}
• 效率评分：{summary.get('efficiency_score', 0)}/100

【今日建议】
{summary.get('top_recommendation', '继续保持！')}

📄 详细报告：{report_path}"""
        
        return self.send_message(message)
