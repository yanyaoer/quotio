#!/usr/bin/env python3
"""
Quota Fetcher - 查询 Kiro 账户的剩余 quota 信息
"""

import json
import uuid
import requests
from typing import Optional, Dict, Any
from credential_store import CredentialStore


class QuotaFetcher:
    """Kiro Quota 查询器"""

    CODEWHISPERER_API = "https://codewhisperer.us-east-1.amazonaws.com"
    KIRO_VERSION = "0.6.18"

    def __init__(self, machine_id: Optional[str] = None):
        """
        初始化 Quota Fetcher

        Args:
            machine_id: 机器标识符，如果不提供则自动生成
        """
        self.machine_id = machine_id or str(uuid.uuid4())
        self.session = requests.Session()

    def _generate_invocation_id(self) -> str:
        """生成唯一的调用 ID"""
        return str(uuid.uuid4())

    def get_usage_limits(self, access_token: str) -> Optional[Dict[str, Any]]:
        """
        获取使用限制和用户信息

        Args:
            access_token: Kiro 访问令牌

        Returns:
            使用限制响应数据，失败时返回 None
        """
        url = f"{self.CODEWHISPERER_API}/getUsageLimits"
        params = {
            'isEmailRequired': 'true',
            'origin': 'AI_EDITOR',
            'resourceType': 'AGENTIC_REQUEST'
        }

        # 构建请求头，匹配 Kiro IDE
        x_amz_user_agent = f"aws-sdk-js/1.0.0 KiroIDE-{self.KIRO_VERSION}-{self.machine_id}"
        user_agent = (
            f"aws-sdk-js/1.0.0 ua/2.1 os/windows lang/js md/nodejs#20.16.0 "
            f"api/codewhispererruntime#1.0.0 m/E KiroIDE-{self.KIRO_VERSION}-{self.machine_id}"
        )

        headers = {
            'Authorization': f'Bearer {access_token}',
            'x-amz-user-agent': x_amz_user_agent,
            'User-Agent': user_agent,
            'amz-sdk-invocation-id': self._generate_invocation_id(),
            'amz-sdk-request': 'attempt=1; max=1',
            'Connection': 'close'
        }

        try:
            response = self.session.get(url, params=params, headers=headers, timeout=30)

            if response.status_code != 200:
                print(f"❌ API 返回错误状态码 {response.status_code}")
                print(f"   响应内容: {response.text}")
                return None

            return response.json()

        except requests.RequestException as e:
            print(f"❌ 请求失败: {e}")
            return None
        except json.JSONDecodeError as e:
            print(f"❌ 解析响应失败: {e}")
            return None

    def format_usage_info(self, usage_data: Dict[str, Any]) -> str:
        """
        格式化使用信息为可读文本

        Args:
            usage_data: getUsageLimits 返回的数据

        Returns:
            格式化后的文本
        """
        lines = []
        lines.append("=" * 70)
        lines.append("Kiro 账户使用情况")
        lines.append("=" * 70)

        # 用户信息
        user_info = usage_data.get('userInfo')
        if user_info:
            lines.append("\n📧 用户信息:")
            if user_info.get('email'):
                lines.append(f"   Email: {user_info['email']}")
            if user_info.get('userId'):
                lines.append(f"   User ID: {user_info['userId']}")

        # 订阅信息
        subscription_info = usage_data.get('subscriptionInfo')
        if subscription_info:
            lines.append("\n📦 订阅信息:")
            if subscription_info.get('subscriptionTitle'):
                lines.append(f"   订阅类型: {subscription_info['subscriptionTitle']}")
            if subscription_info.get('type'):
                lines.append(f"   类型: {subscription_info['type']}")

        # 重置时间
        days_until_reset = usage_data.get('daysUntilReset')
        if days_until_reset is not None:
            lines.append(f"\n🔄 距离下次重置: {days_until_reset} 天")

        # 使用明细
        usage_breakdown_list = usage_data.get('usageBreakdownList', [])
        if usage_breakdown_list:
            lines.append("\n📊 使用明细:")
            for breakdown in usage_breakdown_list:
                display_name = breakdown.get('displayName', '未知')
                resource_type = breakdown.get('resourceType', '')

                # 优先使用精确值，否则使用整数值
                current_usage = breakdown.get('currentUsageWithPrecision') or breakdown.get('currentUsage', 0)
                usage_limit = breakdown.get('usageLimitWithPrecision') or breakdown.get('usageLimit', 0)

                lines.append(f"\n   {display_name} ({resource_type}):")
                lines.append(f"      当前使用: {current_usage}")
                lines.append(f"      使用限制: {usage_limit}")

                if usage_limit > 0:
                    percentage = (current_usage / usage_limit) * 100
                    remaining = usage_limit - current_usage
                    lines.append(f"      剩余额度: {remaining} ({100-percentage:.1f}%)")

                    # 进度条
                    bar_width = 30
                    filled = int((current_usage / usage_limit) * bar_width)
                    bar = "█" * filled + "░" * (bar_width - filled)
                    lines.append(f"      进度: [{bar}] {percentage:.1f}%")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    def fetch_and_display_quota(self, account_type: str = 'kiro') -> bool:
        """
        从凭证存储中获取令牌并显示 quota 信息

        Args:
            account_type: 账户类型 (kiro 或 antigravity)

        Returns:
            成功返回 True，失败返回 False
        """
        if account_type != 'kiro':
            print(f"❌ 不支持的账户类型: {account_type}")
            print("   当前仅支持 Kiro 账户的 quota 查询")
            return False

        # 加载凭证
        store = CredentialStore()
        auth_files = store.list_auth_files(provider='kiro')

        if not auth_files:
            print(f"❌ 未找到 {account_type} 认证文件")
            print(f"   请先运行: python3 main.py auth {account_type}")
            return False

        # 使用第一个 kiro 认证文件
        auth_data = auth_files[0]

        access_token = auth_data.get('access_token')
        if not access_token:
            print(f"❌ 认证文件中缺少 access_token")
            return False

        # 获取 quota 信息
        print(f"\n正在查询 {account_type} 账户的 quota 信息...\n")

        usage_data = self.get_usage_limits(access_token)
        if not usage_data:
            print("\n❌ 获取 quota 信息失败")
            print("   可能的原因:")
            print("   1. Access token 已过期，请运行: python3 main.py token refresh")
            print("   2. 网络连接问题")
            print("   3. API 暂时不可用")
            return False

        # 显示格式化信息
        print(self.format_usage_info(usage_data))
        return True


def main():
    """命令行入口"""
    import sys

    account_type = 'kiro'
    if len(sys.argv) > 1:
        account_type = sys.argv[1]

    fetcher = QuotaFetcher()
    success = fetcher.fetch_and_display_quota(account_type)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
