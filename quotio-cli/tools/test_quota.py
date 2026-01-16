#!/usr/bin/env python3
"""
测试 quota 查询功能（使用模拟数据）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quota_fetcher import QuotaFetcher


def test_quota_display():
    """测试 quota 显示格式"""

    # 模拟 API 返回数据
    mock_usage_data = {
        "daysUntilReset": 25,
        "nextDateReset": 1739664000.0,
        "userInfo": {
            "email": "yanyaoer@gmail.com",
            "userId": "d-9a6771b82e.11fba520-40d1-7026-5a92-7cea997b1458"
        },
        "subscriptionInfo": {
            "subscriptionTitle": "Amazon Q Developer Free Tier",
            "type": "FREE_TIER"
        },
        "usageBreakdownList": [
            {
                "usageLimit": 50,
                "currentUsage": 12,
                "usageLimitWithPrecision": 50.0,
                "currentUsageWithPrecision": 12.0,
                "nextDateReset": 1739664000.0,
                "displayName": "Agentic Requests",
                "resourceType": "AGENTIC_REQUEST"
            },
            {
                "usageLimit": 1000,
                "currentUsage": 234,
                "usageLimitWithPrecision": 1000.0,
                "currentUsageWithPrecision": 234.0,
                "nextDateReset": 1739664000.0,
                "displayName": "Code Completions",
                "resourceType": "CODE_COMPLETION"
            }
        ]
    }

    fetcher = QuotaFetcher()
    formatted = fetcher.format_usage_info(mock_usage_data)
    print(formatted)
    print("\n✓ Quota 显示功能测试成功")


if __name__ == '__main__':
    test_quota_display()
