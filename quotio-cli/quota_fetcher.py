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

    def _fetch_antigravity_quota(self) -> bool:
        """
        获取 Antigravity 账户 Quota 信息
        参考 Swift: AntigravityQuotaFetcher.swift
        """
        store = CredentialStore()
        auth_files = store.list_auth_files(provider='antigravity')
        
        if not auth_files:
            print(f"❌ 未找到 antigravity 认证文件")
            print(f"   请先运行: python3 main.py auth antigravity")
            return False
            
        print(f"\n找到 {len(auth_files)} 个 Antigravity 账户\n")
        
        for i, auth_data in enumerate(auth_files, 1):
            access_token = auth_data.get('access_token')
            email = auth_data.get('email', 'Unknown')
            
            print(f"[{i}/{len(auth_files)}] 正在查询账户: {email} ...")
            
            if not access_token:
                 print(f"❌ 认证文件中缺少 access_token")
                 continue
    
            # 1. 获取 Project ID
            project_id = self._fetch_antigravity_project_id(access_token)
            if not project_id:
                print("❌ 获取 Project ID 失败")
                continue
                
            # 2. 获取 Quota
            quota_data = self._fetch_antigravity_models(access_token, project_id)
            if not quota_data:
                print("❌ 获取 Quota 信息失败")
                continue
                
            # 3. 显示结果
            self._display_antigravity_quota(email, quota_data)
            
        return True

    def _fetch_antigravity_project_id(self, access_token: str) -> Optional[str]:
        """获取 Antigravity Project ID"""
        url = "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'antigravity/1.11.3 Darwin/arm64',
            'Content-Type': 'application/json'
        }
        payload = {"metadata": {"ideType": "ANTIGRAVITY"}}
        
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                return data.get('cloudaicompanionProject')
            else:
                print(f"⚠️  获取 Project ID 失败 (HTTP {response.status_code}): {response.text}")
                return None
        except Exception as e:
            print(f"⚠️  获取 Project ID 异常: {e}")
            return None

    def _fetch_antigravity_models(self, access_token: str, project_id: str) -> Optional[Dict]:
        """获取 Antigravity 模型及 Quota"""
        url = "https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'User-Agent': 'antigravity/1.11.3 Darwin/arm64',
            'Content-Type': 'application/json'
        }
        payload = {"project": project_id}
        
        try:
            response = self.session.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 403:
                print("❌ 访问被拒绝 (403 Forbidden)")
                return None
            else:
                print(f"⚠️  获取 Quota 失败 (HTTP {response.status_code}): {response.text}")
                return None
        except Exception as e:
            print(f"⚠️  获取 Quota 异常: {e}")
            return None

    def _display_antigravity_quota(self, email: str, quota_data: Dict):
        """显示 Antigravity Quota"""
        print("=" * 70)
        print("Antigravity (Gemini) 账户使用情况")
        print("=" * 70)
        print(f"\n📧 用户: {email}")
        
        models = quota_data.get('models', {})
        if not models:
            print("\n⚠️  未找到模型信息")
        else:
            print("\n📊 模型额度:")
            
            # 过滤并显示感兴趣的模型
            relevant_keys = [k for k in models.keys() if 'gemini' in k.lower() or 'claude' in k.lower()]
            
            if not relevant_keys:
                print("   (无 Gemini/Claude 相关模型)")
            
            for name in relevant_keys:
                info = models[name]
                quota_info = info.get('quotaInfo')
                
                if quota_info:
                    remaining_fraction = quota_info.get('remainingFraction', 0)
                    reset_time = quota_info.get('resetTime', '未知')
                    
                    percentage = remaining_fraction * 100
                    used_percentage = 100 - percentage
                    
                    # 格式化显示名称
                    display_name = name.replace("gemini-", "Gemini ").replace("claude-", "Claude ").title()
                    
                    # 进度条
                    bar_width = 30
                    filled = int((used_percentage / 100) * bar_width)
                    # 确保 filled 不超过 bar_width
                    filled = min(filled, bar_width)
                    bar = "█" * filled + "░" * (bar_width - filled)
                    
                    print(f"\n   {display_name}:")
                    print(f"      剩余: {percentage:.1f}%")
                    print(f"      重置: {reset_time}")
                    print(f"      使用: [{bar}] {used_percentage:.1f}%")

        print("\n" + "=" * 70)

    def fetch_and_display_quota(self, account_type: str = 'kiro') -> bool:
        """
        从凭证存储中获取令牌并显示 quota 信息

        Args:
            account_type: 账户类型 (kiro 或 antigravity)

        Returns:
            成功返回 True，失败返回 False
        """
        if account_type == 'antigravity':
            return self._fetch_antigravity_quota()

        if account_type != 'kiro':
            print(f"❌ 不支持的账户类型: {account_type}")
            print("   当前仅支持 Kiro 和 Antigravity 账户的 quota 查询")
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
