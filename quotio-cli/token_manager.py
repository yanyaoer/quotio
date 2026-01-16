#!/usr/bin/env python3
"""
Token Manager - 用于刷新 OAuth 令牌
参考 Swift 实现中的 KiroQuotaFetcher 和 DirectAuthFileService
"""

import json
import urllib.request
import urllib.parse
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any

from credential_store import CredentialStore


class TokenManager:
    """令牌管理器"""

    # Kiro Token Refresh Endpoints
    KIRO_SOCIAL_REFRESH_URL = "https://prod.us-east-1.auth.desktop.kiro.dev/refreshToken"
    # 注意: IdC endpoint 不再硬编码，而是从 token 数据中的 region 字段动态构建

    # 刷新缓冲时间：提前 5 分钟刷新（参考 Swift: KiroQuotaFetcher.swift:116）
    REFRESH_BUFFER_SECONDS = 5 * 60

    def __init__(self):
        self.credential_store = CredentialStore()

    def refresh_all_tokens(self, verbose: bool = False) -> int:
        """刷新所有过期或即将过期的令牌

        Args:
            verbose: 是否输出详细信息

        Returns:
            int: 成功刷新的令牌数量
        """
        files = self.credential_store.list_auth_files(provider="kiro")
        refreshed_count = 0

        for f in files:
            # 补全 IdC 凭证（如果缺失）
            f = self._load_and_complement_credentials(f)

            should_refresh, reason = self._should_refresh(f)
            if verbose:
                identifier = f.get('email') or f.get('_filename', '').replace('.json', '')
                print(f"[{identifier}] {reason}")

            if should_refresh:
                try:
                    identifier = f.get('email') or f.get('_filename', '').replace('.json', '')
                    if self._refresh_token(f, identifier):
                        refreshed_count += 1
                        print(f"✓ 已刷新令牌: {identifier}")
                except Exception as e:
                    print(f"✗ 刷新失败 {f.get('email')}: {e}")

        return refreshed_count

    def _should_refresh(self, token_data: Dict) -> Tuple[bool, str]:
        """检查是否需要刷新

        参考 Swift: KiroQuotaFetcher.swift:145-174

        Returns:
            (should_refresh, reason)
        """
        expires_at = token_data.get('expires_at')
        if not expires_at:
            return (False, "无过期信息")

        try:
            # 处理 'Z' 结尾的 ISO 时间
            if isinstance(expires_at, str):
                if expires_at.endswith('Z'):
                    expires_at = expires_at[:-1]
                exp_date = datetime.fromisoformat(expires_at)
            else:
                return (False, "无法解析过期时间")

            # UTC 时间比较
            now = datetime.utcnow()

            # 计算剩余时间
            remaining = (exp_date - now).total_seconds()

            if remaining <= 0:
                return (True, f"已过期 {int(-remaining)} 秒")
            elif remaining < self.REFRESH_BUFFER_SECONDS:
                return (True, f"{int(remaining)} 秒后过期 (< 5 分钟缓冲)")

            return (False, f"剩余 {int(remaining)} 秒")

        except Exception as e:
            # 解析失败则假设需要刷新
            return (True, f"解析错误: {e}")

    def _refresh_token(self, token_data: Dict, identifier: str) -> bool:
        """刷新单个令牌

        参考 Swift: KiroQuotaFetcher.swift:294-309
        """
        auth_method = token_data.get('auth_method', 'IdC')
        refresh_token = token_data.get('refresh_token')

        if not refresh_token:
            return False

        new_token_data = None

        if auth_method == 'Social':
            new_token_data = self._refresh_kiro_social(refresh_token)
        elif auth_method == 'IdC':
            # IdC 需要 client_id, client_secret 和 region
            client_id = token_data.get('client_id')
            client_secret = token_data.get('client_secret')
            region = token_data.get('region', 'us-east-1')

            if client_id and client_secret:
                new_token_data = self._refresh_kiro_idc(
                    refresh_token, client_id, client_secret, region
                )

        if new_token_data:
            # 更新 token 数据
            token_data['access_token'] = new_token_data['accessToken']

            if 'refreshToken' in new_token_data:
                token_data['refresh_token'] = new_token_data['refreshToken']

            expires_in = new_token_data.get('expiresIn', 3600)
            new_exp = datetime.utcnow() + timedelta(seconds=expires_in)
            token_data['expires_at'] = new_exp.isoformat() + "Z"
            token_data['last_refresh'] = datetime.utcnow().isoformat() + "Z"

            # 移除临时字段
            if '_filename' in token_data:
                del token_data['_filename']
            if '_filepath' in token_data:
                del token_data['_filepath']

            self.credential_store.save_auth_file("kiro", identifier, token_data)
            return True

        return False

    def _refresh_kiro_social(self, refresh_token: str) -> Optional[Dict]:
        """刷新 Kiro Social Token (Google)

        参考 Swift: KiroQuotaFetcher.swift:312-349
        """
        data = json.dumps({
            "refreshToken": refresh_token
        }).encode('utf-8')

        req = urllib.request.Request(
            self.KIRO_SOCIAL_REFRESH_URL,
            data=data,
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            print(f"Social 令牌刷新失败: {e}")
            return None

    def _refresh_kiro_idc(self, refresh_token: str, client_id: str,
                         client_secret: str, region: str = 'us-east-1') -> Optional[Dict]:
        """刷新 Kiro IdC Token (AWS Builder ID / IAM Identity Center)

        参考 Swift: KiroQuotaFetcher.swift:352-405

        修复: 不再硬编码 us-east-1，而是使用传入的 region 参数
        """
        # 动态构建 endpoint（修复硬编码问题）
        endpoint = f"https://oidc.{region}.amazonaws.com/token"

        data = json.dumps({
            "clientId": client_id,
            "clientSecret": client_secret,
            "grantType": "refresh_token",
            "refreshToken": refresh_token
        }).encode('utf-8')

        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Host": f"oidc.{region}.amazonaws.com",
                "Connection": "keep-alive",
                "x-amz-user-agent": "aws-sdk-js/3.738.0 ua/2.1 os/other lang/js md/browser KiroIDE",
                "Accept": "*/*",
                "Accept-Language": "*",
                "User-Agent": "node"
            }
        )

        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            print(f"IdC 令牌刷新失败 (HTTP {e.code}): {error_body}")
            return None
        except Exception as e:
            print(f"IdC 令牌刷新失败: {e}")
            return None

    def _load_and_complement_credentials(self, token_data: Dict) -> Dict:
        """加载并补全 IdC 凭证（如果缺失）

        参考 Swift: DirectAuthFileService.swift:329-339

        这是 Swift 特有的优化，现在添加到 Python 中
        """
        auth_method = token_data.get('auth_method', 'IdC')

        # 仅对 IdC 认证方法补全
        if auth_method != 'IdC':
            return token_data

        # 检查是否缺少凭证
        if token_data.get('client_id') and token_data.get('client_secret'):
            return token_data

        # 尝试从 AWS SSO cache 加载
        client_id, client_secret = self._load_kiro_device_registration()

        if client_id and client_secret:
            print(f"从 AWS SSO cache 补全凭证")
            token_data['client_id'] = client_id
            token_data['client_secret'] = client_secret

            # 持久化到磁盘
            identifier = token_data.get('email') or token_data.get('_filename', '').replace('.json', '')
            if identifier:
                self.credential_store.save_auth_file("kiro", identifier, token_data)

        return token_data

    def _load_kiro_device_registration(self) -> Tuple[Optional[str], Optional[str]]:
        """从 AWS SSO cache 加载 clientId 和 clientSecret

        参考 Swift: DirectAuthFileService.swift:376-416

        Returns:
            (client_id, client_secret)
        """
        cache_path = os.path.expanduser("~/.aws/sso/cache")

        if not os.path.exists(cache_path):
            return (None, None)

        # 方法 1: 尝试从 kiro-auth-token.json 读取 clientIdHash
        kiro_auth_token_path = os.path.join(cache_path, "kiro-auth-token.json")

        if os.path.exists(kiro_auth_token_path):
            try:
                with open(kiro_auth_token_path, 'r') as f:
                    data = json.load(f)
                    client_id_hash = data.get('clientIdHash')

                    if client_id_hash:
                        device_reg_path = os.path.join(cache_path, f"{client_id_hash}.json")

                        if os.path.exists(device_reg_path):
                            with open(device_reg_path, 'r') as df:
                                device_data = json.load(df)
                                client_id = device_data.get('clientId')
                                client_secret = device_data.get('clientSecret')

                                if client_id and client_secret:
                                    return (client_id, client_secret)
            except Exception:
                pass

        # 方法 2: 回退 - 扫描所有 .json 文件
        try:
            for filename in os.listdir(cache_path):
                if not filename.endswith('.json') or filename == 'kiro-auth-token.json':
                    continue

                file_path = os.path.join(cache_path, filename)
                try:
                    with open(file_path, 'r') as f:
                        data = json.load(f)
                        client_id = data.get('clientId')
                        client_secret = data.get('clientSecret')

                        if client_id and client_secret:
                            return (client_id, client_secret)
                except Exception:
                    continue
        except Exception:
            pass

        return (None, None)

