#!/usr/bin/env python3
"""
OAuth 认证服务器 - 处理 OAuth 回调和 Device Code 流程
"""

import http.server
import json
import os
import socket
import socketserver
import threading
import time
import urllib.parse
import urllib.request
import ssl
from typing import Optional, Dict, Any

from credential_store import CredentialStore


class AuthServer:
    """OAuth 认证服务器"""

    # Antigravity OAuth 配置 (Google OAuth)
    # 从环境变量读取，如未设置则使用空字符串（需要用户自行配置）
    ANTIGRAVITY_CLIENT_ID = os.getenv("ANTIGRAVITY_CLIENT_ID", "")
    ANTIGRAVITY_CLIENT_SECRET = os.getenv("ANTIGRAVITY_CLIENT_SECRET", "")
    ANTIGRAVITY_SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/cloud_code.assistants",
        "https://www.googleapis.com/auth/cloudaicompanion"
    ]

    # Kiro Google OAuth 配置
    # 从环境变量读取，如未设置则使用空字符串（需要用户自行配置）
    KIRO_GOOGLE_CLIENT_ID = os.getenv("KIRO_GOOGLE_CLIENT_ID", "")
    KIRO_GOOGLE_CLIENT_SECRET = os.getenv("KIRO_GOOGLE_CLIENT_SECRET", "")
    KIRO_GOOGLE_SCOPES = ["openid", "email", "profile"]

    # Kiro Web 认证配置 (PKCE 流程)
    KIRO_AUTH_URL = "https://app.kiro.dev/signin"

    # Kiro AWS Builder ID 配置
    KIRO_AWS_REGION = "us-east-1"
    KIRO_AWS_START_URL = "https://view.awsapps.com/start"  # 默认个人 Builder ID

    def __init__(self, host: str = "0.0.0.0", port: int = 8765,
                 callback_host: Optional[str] = None,
                 aws_start_url: Optional[str] = None,
                 aws_region: Optional[str] = None):
        self.host = host
        self.port = port
        self.callback_host = callback_host or self._detect_ip()
        self.credential_store = CredentialStore()
        self._auth_result: Optional[Dict[str, Any]] = None
        self._auth_event = threading.Event()
        self._pkce_verifier: Optional[str] = None  # PKCE code verifier

        # 支持自定义 AWS 配置（企业 IAM Identity Center）
        if aws_start_url:
            self.KIRO_AWS_START_URL = aws_start_url
        if aws_region:
            self.KIRO_AWS_REGION = aws_region

    def _detect_ip(self) -> str:
        """检测服务器的公网/局域网 IP"""
        try:
            # 尝试获取公网 IP
            with urllib.request.urlopen('https://api.ipify.org', timeout=5) as resp:
                return resp.read().decode('utf-8').strip()
        except Exception:
            pass

        # 回退到局域网 IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    def _get_callback_url(self) -> str:
        """生成回调 URL"""
        return f"http://{self.callback_host}:{self.port}/callback"

    def _generate_pkce(self) -> tuple:
        """生成 PKCE code_verifier 和 code_challenge"""
        import hashlib
        import base64
        import secrets

        # 生成 code_verifier (43-128 字符)
        code_verifier = secrets.token_urlsafe(32)

        # 生成 code_challenge = BASE64URL(SHA256(code_verifier))
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('ascii')).digest()
        ).decode('ascii').rstrip('=')

        return code_verifier, code_challenge

    def _generate_state(self) -> str:
        """生成随机 state 参数"""
        import secrets
        return secrets.token_urlsafe(8)[:10]  # 类似 Kiro CLI 的格式

    def _build_google_auth_url(self, client_id: str, scopes: list,
                                redirect_uri: str, state: str) -> str:
        """构建 Google OAuth 授权 URL"""
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    def _exchange_code_for_token(self, code: str, client_id: str,
                                  client_secret: str, redirect_uri: str) -> Dict[str, Any]:
        """用授权码交换 access token"""
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }).encode('utf-8')

        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """获取用户信息"""
        req = urllib.request.Request(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _create_callback_handler(self, provider: str, client_id: str,
                                  client_secret: str):
        """创建 OAuth 回调处理器"""
        server = self

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == '/callback':
                    self._handle_callback(parsed)
                elif parsed.path == '/health':
                    self._send_text(200, "OK")
                else:
                    self._send_text(404, "Not Found")

            def _handle_callback(self, parsed):
                params = urllib.parse.parse_qs(parsed.query)
                code = params.get('code', [None])[0]
                error = params.get('error', [None])[0]

                if error:
                    server._auth_result = {"error": error}
                    self._send_html(f"认证失败: {error}")
                elif code:
                    try:
                        token_data = server._exchange_code_for_token(
                            code, client_id, client_secret,
                            server._get_callback_url()
                        )
                        user_info = server._get_user_info(token_data['access_token'])
                        server._auth_result = {
                            "provider": provider,
                            "token_data": token_data,
                            "user_info": user_info
                        }
                        self._send_html("认证成功! 可以关闭此页面。")
                    except Exception as e:
                        server._auth_result = {"error": str(e)}
                        self._send_html(f"Token 交换失败: {e}")
                else:
                    self._send_html("缺少授权码")
                server._auth_event.set()

            def _send_text(self, code, msg):
                self.send_response(code)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(msg.encode('utf-8'))

            def _send_html(self, msg):
                html = f"<html><body><h2>{msg}</h2></body></html>"
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))

        return CallbackHandler

    def start_antigravity_auth(self):
        """启动 Antigravity Google OAuth 认证"""
        import secrets
        state = secrets.token_urlsafe(16)
        callback_url = self._get_callback_url()

        auth_url = self._build_google_auth_url(
            self.ANTIGRAVITY_CLIENT_ID,
            self.ANTIGRAVITY_SCOPES,
            callback_url, state
        )

        print("\n" + "="*60)
        print("Antigravity OAuth 认证")
        print("="*60)
        print(f"\n回调服务器: {callback_url}")
        print(f"\n请在浏览器中访问以下链接完成认证:\n")
        print(auth_url)
        print("\n" + "="*60)
        print("等待认证完成...")

        self._run_callback_server(
            "antigravity",
            self.ANTIGRAVITY_CLIENT_ID,
            self.ANTIGRAVITY_CLIENT_SECRET
        )

    def start_kiro_google_auth(self):
        """启动 Kiro Google OAuth 认证"""
        import secrets
        state = secrets.token_urlsafe(16)
        callback_url = self._get_callback_url()

        auth_url = self._build_google_auth_url(
            self.KIRO_GOOGLE_CLIENT_ID,
            self.KIRO_GOOGLE_SCOPES,
            callback_url, state
        )

        print("\n" + "="*60)
        print("Kiro Google OAuth 认证")
        print("="*60)
        print(f"\n回调服务器: {callback_url}")
        print(f"\n请在浏览器中访问以下链接完成认证:\n")
        print(auth_url)
        print("\n" + "="*60)
        print("等待认证完成...")

        self._run_callback_server(
            "kiro",
            self.KIRO_GOOGLE_CLIENT_ID,
            self.KIRO_GOOGLE_CLIENT_SECRET
        )

    def start_kiro_aws_auth(self):
        """启动 Kiro AWS Builder ID 认证 (Device Code 流程)

        注意: AWS OIDC 对公开客户端要求 redirect_uri 必须是 localhost,
        因此在服务器环境下使用 Device Code 流程是最佳选择。
        """
        print("\n" + "="*60)
        print("Kiro AWS Builder ID / IAM Identity Center 认证")
        print("="*60)
        print(f"\nStart URL: {self.KIRO_AWS_START_URL}")
        print(f"Region: {self.KIRO_AWS_REGION}")

        # 1. 注册设备客户端
        print("\n正在注册设备...")
        reg_data = self._aws_register_client_device()
        if not reg_data:
            print("设备注册失败")
            return

        client_id = reg_data['clientId']
        client_secret = reg_data['clientSecret']

        # 2. 启动设备授权
        print("正在获取设备码...")
        auth_data = self._aws_start_device_auth(client_id, client_secret)
        if not auth_data:
            print("获取设备码失败")
            return

        device_code = auth_data['deviceCode']
        user_code = auth_data['userCode']
        verify_uri = auth_data['verificationUriComplete']
        interval = auth_data.get('interval', 5)

        print(f"\n用户码: {user_code}")
        print(f"\n请在任意设备的浏览器中访问:\n{verify_uri}")
        print("\n" + "="*60)
        print("等待认证完成...")

        # 3. 轮询 token
        self._aws_poll_token(client_id, client_secret, device_code, interval)

    def _try_aws_browser_auth(self):
        """尝试 AWS Browser 认证 (仅供参考，通常会失败)

        AWS OIDC 对于公开客户端要求 redirect_uri 必须是 loopback 地址。
        此方法仅用于测试目的。
        """
        import secrets
        state = secrets.token_urlsafe(16)
        callback_url = self._get_callback_url()

        print("\n" + "="*60)
        print("Kiro AWS Builder ID 认证 (Browser 流程)")
        print("="*60)
        print("\n注意: AWS 要求公开客户端使用 localhost 重定向，")
        print("此方法在远程服务器上可能无法工作。")

        # 1. 注册 OIDC 客户端
        print("\n正在注册客户端...")
        reg_data = self._aws_register_client_browser(callback_url)
        if not reg_data:
            print("客户端注册失败 (预期行为: AWS 要求使用 localhost)")
            print("请使用 --method aws 来使用 Device Code 流程")
            return

        client_id = reg_data['clientId']
        client_secret = reg_data['clientSecret']

        auth_url = self._build_aws_auth_url(client_id, callback_url, state)

        print(f"\n回调服务器: {callback_url}")
        print(f"\n请在浏览器中访问以下链接完成认证:\n")
        print(auth_url)
        print("\n" + "="*60)
        print("等待认证完成...")

        self._run_aws_callback_server(client_id, client_secret, callback_url)

    def start_kiro_aws_auth_device_code(self):
        """启动 Kiro AWS Builder ID 认证 (Device Code 流程) - 别名方法"""
        self.start_kiro_aws_auth()

    def _aws_register_client_browser(self, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """注册 AWS OIDC 客户端 (Browser 流程)"""
        url = f"https://oidc.{self.KIRO_AWS_REGION}.amazonaws.com/client/register"
        data = json.dumps({
            "clientName": "Kiro",
            "clientType": "public",
            "scopes": ["codewhisperer:completions", "codewhisperer:analysis"],
            "grantTypes": ["authorization_code", "refresh_token"],
            "redirectUris": [redirect_uri],
            "issuerUrl": self.KIRO_AWS_START_URL
        }).encode('utf-8')

        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            print(f"注册失败: {e} - {body}")
            return None
        except Exception as e:
            print(f"注册失败: {e}")
            return None

    def _aws_register_client_device(self) -> Optional[Dict[str, Any]]:
        """注册 AWS OIDC 设备客户端 (Device Code 流程)"""
        url = f"https://oidc.{self.KIRO_AWS_REGION}.amazonaws.com/client/register"

        # 根据 start URL 判断是个人 Builder ID 还是企业 IAM Identity Center
        is_builder_id = "view.awsapps.com" in self.KIRO_AWS_START_URL

        scopes = ["codewhisperer:completions", "codewhisperer:analysis"]
        if not is_builder_id:
            scopes.append("sso:account:access")

        data = json.dumps({
            "clientName": "Kiro",
            "clientType": "public",
            "scopes": scopes,
            "grantTypes": ["urn:ietf:params:oauth:grant-type:device_code", "refresh_token"],
            "issuerUrl": self.KIRO_AWS_START_URL
        }).encode('utf-8')

        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode('utf-8'))
                print(f"注册成功:")
                print(f"  clientId: {result.get('clientId', 'N/A')[:30]}...")
                print(f"  scopes: {scopes}")
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            print(f"注册失败: {e} - {body}")
            return None
        except Exception as e:
            print(f"注册失败: {e}")
            return None

    def _build_aws_auth_url(self, client_id: str, redirect_uri: str, state: str) -> str:
        """构建 AWS SSO 授权 URL"""
        # AWS SSO 使用 OIDC 授权端点
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scopes": "codewhisperer:completions codewhisperer:analysis",
            "state": state
        }
        base_url = f"{self.KIRO_AWS_START_URL}/#/authorize"
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    def _run_aws_callback_server(self, client_id: str, client_secret: str, redirect_uri: str):
        """运行 AWS OAuth 回调服务器"""
        server = self

        class AWSCallbackHandler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == '/callback':
                    self._handle_callback(parsed)
                elif parsed.path == '/health':
                    self._send_text(200, "OK")
                else:
                    self._send_text(404, "Not Found")

            def _handle_callback(self, parsed):
                params = urllib.parse.parse_qs(parsed.query)
                code = params.get('code', [None])[0]
                error = params.get('error', [None])[0]

                if error:
                    server._auth_result = {"error": error}
                    self._send_html(f"认证失败: {error}")
                elif code:
                    try:
                        token_data = server._aws_exchange_code_for_token(
                            code, client_id, client_secret, redirect_uri
                        )
                        server._save_kiro_aws_token(token_data, client_id, client_secret)
                        server._auth_result = {"success": True, "token_data": token_data}
                        self._send_html("认证成功! 可以关闭此页面。")
                    except Exception as e:
                        server._auth_result = {"error": str(e)}
                        self._send_html(f"Token 交换失败: {e}")
                else:
                    self._send_html("缺少授权码")
                server._auth_event.set()

            def _send_text(self, code, msg):
                self.send_response(code)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(msg.encode('utf-8'))

            def _send_html(self, msg):
                html = f"<html><body><h2>{msg}</h2></body></html>"
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(html.encode('utf-8'))

        with socketserver.TCPServer((self.host, self.port), AWSCallbackHandler) as httpd:
            httpd.timeout = 300  # 5 分钟超时
            self._auth_event.clear()

            while not self._auth_event.is_set():
                httpd.handle_request()

            if self._auth_result:
                if "error" in self._auth_result:
                    print(f"\n认证失败: {self._auth_result['error']}")
                else:
                    print("\n认证成功!")

    def _aws_exchange_code_for_token(self, code: str, client_id: str,
                                      client_secret: str, redirect_uri: str) -> Dict[str, Any]:
        """用授权码交换 AWS access token"""
        url = f"https://oidc.{self.KIRO_AWS_REGION}.amazonaws.com/token"
        data = json.dumps({
            "clientId": client_id,
            "clientSecret": client_secret,
            "code": code,
            "redirectUri": redirect_uri,
            "grantType": "authorization_code"
        }).encode('utf-8')

        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _aws_start_device_auth(self, client_id: str, client_secret: str) -> Optional[Dict[str, Any]]:
        """启动 AWS 设备授权"""
        url = f"https://oidc.{self.KIRO_AWS_REGION}.amazonaws.com/device_authorization"
        request_data = {
            "clientId": client_id,
            "clientSecret": client_secret,
            "startUrl": self.KIRO_AWS_START_URL
        }
        print(f"请求 URL: {url}")
        print(f"请求数据: {json.dumps(request_data, indent=2)}")

        data = json.dumps(request_data).encode('utf-8')

        req = urllib.request.Request(url, data=data,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            print(f"设备授权失败: {e} - {body}")
            return None
        except Exception as e:
            print(f"设备授权失败: {e}")
            return None

    def _aws_poll_token(self, client_id: str, client_secret: str,
                        device_code: str, interval: int):
        """轮询 AWS token"""
        url = f"https://oidc.{self.KIRO_AWS_REGION}.amazonaws.com/token"

        for _ in range(60):  # 最多等待 5 分钟
            time.sleep(interval)
            data = json.dumps({
                "clientId": client_id,
                "clientSecret": client_secret,
                "deviceCode": device_code,
                "grantType": "urn:ietf:params:oauth:grant-type:device_code"
            }).encode('utf-8')

            req = urllib.request.Request(url, data=data,
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req) as resp:
                    token_data = json.loads(resp.read().decode('utf-8'))
                    self._save_kiro_aws_token(token_data, client_id, client_secret)
                    print("\n认证成功!")
                    return
            except urllib.error.HTTPError as e:
                body = e.read().decode('utf-8')
                if 'authorization_pending' in body:
                    print(".", end="", flush=True)
                    continue
                elif 'slow_down' in body:
                    interval += 5
                    continue
                else:
                    print(f"\n认证失败: {body}")
                    return
        print("\n认证超时")

    def _save_kiro_aws_token(self, token_data: Dict, client_id: str, client_secret: str):
        """保存 Kiro AWS token"""
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=token_data.get('expiresIn', 3600))

        auth_file = {
            "type": "kiro",
            "auth_method": "IdC",
            "access_token": token_data['accessToken'],
            "refresh_token": token_data.get('refreshToken'),
            "expires_at": expires_at.isoformat() + "Z",
            "client_id": client_id,
            "client_secret": client_secret,
            "start_url": self.KIRO_AWS_START_URL,
            "region": self.KIRO_AWS_REGION
        }
        
        # 尝试获取并保存 profileArn (用于 Kiro/CodeWhisperer API)
        profile_arn = self._fetch_kiro_profile_arn(token_data['accessToken'])
        if profile_arn:
            auth_file["profileArn"] = profile_arn
            
        self.credential_store.save_auth_file("kiro", "aws-builder-id", auth_file)

    def _fetch_kiro_profile_arn(self, access_token: str) -> Optional[str]:
        """获取 Kiro (CodeWhisperer) Profile ARN

        注意: 某些企业 IAM Identity Center 账户可能无权访问此 API,
        或者返回空的 profiles 列表。这不影响核心功能（额度查询）。
        """
        # CodeWhisperer API 通常在 us-east-1
        region = "us-east-1"
        host = f"codewhisperer.{region}.amazonaws.com"
        url = f"https://{host}/listProfiles"

        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {access_token}")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-amzn-codewhisperer-optout", "true")

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                # 解析 profiles
                if "profiles" in data and len(data["profiles"]) > 0:
                    profile_arn = data["profiles"][0].get("arn")
                    if profile_arn:
                        print(f"  ✓ 获取到 profileArn: {profile_arn[:50]}...")
                        return profile_arn
                    else:
                        print(f"  ⚠️  profiles 数组中无 ARN 字段")
                else:
                    print(f"  ⚠️  未返回 profiles（可能是企业账户权限限制）")
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8')
            print(f"  ⚠️  获取 profileArn 失败 (HTTP {e.code}): {error_body[:100]}")
        except Exception as e:
            print(f"  ⚠️  获取 profileArn 失败: {e}")

        print(f"  ℹ️  ProfileARN 缺失不影响额度查询功能")
        return None

    def _run_callback_server(self, provider: str, client_id: str, client_secret: str):
        """运行 OAuth 回调服务器"""
        handler = self._create_callback_handler(provider, client_id, client_secret)

        with socketserver.TCPServer((self.host, self.port), handler) as httpd:
            httpd.timeout = 300  # 5 分钟超时
            self._auth_event.clear()

            while not self._auth_event.is_set():
                httpd.handle_request()

            if self._auth_result:
                if "error" in self._auth_result:
                    print(f"\n认证失败: {self._auth_result['error']}")
                else:
                    self._save_google_token(self._auth_result)
                    print("\n认证成功!")

    def _save_google_token(self, result: Dict):
        """保存 Google OAuth token"""
        from datetime import datetime, timedelta
        token = result['token_data']
        user = result['user_info']
        provider = result['provider']

        expires_at = datetime.utcnow() + timedelta(seconds=token.get('expires_in', 3600))

        auth_file = {
            "type": provider,
            "auth_method": "Social",
            "provider": "Google",
            "access_token": token['access_token'],
            "refresh_token": token.get('refresh_token'),
            "expires_at": expires_at.isoformat() + "Z",
            "email": user.get('email', '')
        }

        email = user.get('email', 'unknown')
        self.credential_store.save_auth_file(provider, email, auth_file)

    def start_kiro_manual_auth(self):
        """启动 Kiro Manual Auth (适用于无头服务器)"""
        # 1. 生成 PKCE
        verifier, challenge = self._generate_pkce()
        state = self._generate_state()
        
        # 2. 构建 URL
        # 使用随机端口或固定端口均可，这里使用随机端口模拟 IDE 行为
        import random
        port = random.randint(49152, 65535)
        redirect_uri = f"http://localhost:{port}"
        
        params = {
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "redirect_uri": redirect_uri,
            "redirect_from": "kirocli",
            "response_type": "code"
        }
        
        auth_url = f"{self.KIRO_AUTH_URL}?{urllib.parse.urlencode(params)}"
        
        print("\n" + "="*60)
        print("Kiro Manual Authentication (No Browser)")
        print("="*60)
        print(f"\n1. Please open the following URL in your browser on a local device:")
        print(f"\n{auth_url}\n")
        print("2. Login and authorize.")
        print("3. The browser will redirect to a localhost URL (which may fail to load).")
        print("4. Copy the entire 'failed' URL from the browser address bar.")
        print("5. Paste the URL below:\n")
        
        try:
            callback_url = input("Callback URL: ").strip()
        except EOFError:
            return
        
        if not callback_url:
            print("Error: Empty URL provided.")
            return

        try:
            parsed = urllib.parse.urlparse(callback_url)
            query_params = urllib.parse.parse_qs(parsed.query)

            # Check for AWS IdC redirection
            login_option = query_params.get('login_option', [None])[0]
            if login_option == 'awsidc':
                 issuer_url = query_params.get('issuer_url', [None])[0]
                 region = query_params.get('idc_region', [None])[0]
                 
                 print("\nDetected AWS Identity Center login.")
                 print(f"Switching to Device Code flow for {issuer_url}...")
                 
                 if issuer_url:
                     self.KIRO_AWS_START_URL = issuer_url
                 if region:
                     self.KIRO_AWS_REGION = region
                     
                 self.start_kiro_aws_auth()
                 return
            
            error = query_params.get('error', [None])[0]
            code = query_params.get('code', [None])[0]
            
            if error:
                print(f"\nAuth failed: {error}")
                return
                
            if not code:
                print(f"\nError: No 'code' found in the URL. Ensure you copied the full redirected URL.")
                return
                
            print("\nExchanging code for token...")
            token_data = self._exchange_kiro_code(code, verifier, redirect_uri)
            
            # 解析 Token 获取邮箱 (Social 登录通常没有直接的用户信息 endpoint，尝试从 id_token 解析)
            email = "unknown"
            if 'id_token' in token_data:
                try:
                    # 简单的 JWT 解析 (不验证签名，仅提取信息)
                    parts = token_data['id_token'].split('.')
                    if len(parts) > 1:
                        import base64
                        #补全 padding
                        padding = len(parts[1]) % 4
                        if padding > 0:
                            parts[1] += '=' * (4 - padding)
                        payload = json.loads(base64.urlsafe_b64decode(parts[1]).decode('utf-8'))
                        email = payload.get('email', email)
                except Exception:
                    pass
            
            self._save_kiro_token(token_data, email)
            print(f"\nSuccessfully authenticated as: {email}")
            print("Authentication completed!")
            
        except Exception as e:
            print(f"\nError during authentication: {e}")

    def _exchange_kiro_code(self, code: str, verifier: str, redirect_uri: str) -> Dict[str, Any]:
        """交换 Kiro 授权码"""
        url = "https://prod.us-east-1.auth.desktop.kiro.dev/token"
        
        data = json.dumps({
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }).encode('utf-8')
        
        req = urllib.request.Request(
            url, 
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "KiroCLI/0.1.0"
            }
        )
        
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            raise Exception(f"HTTP {e.code}: {body}")

    def _save_kiro_token(self, token_data: Dict, email: str):
        """保存 Kiro Token"""
        from datetime import datetime, timedelta
        
        expires_in = token_data.get('expires_in', 3600)
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        
        auth_file = {
            "type": "kiro",
            "auth_method": "Social", 
            "access_token": token_data['access_token'],
            "refresh_token": token_data.get('refresh_token'),
            "expires_at": expires_at.isoformat() + "Z",
            "email": email
        }
        
        self.credential_store.save_auth_file("kiro", email, auth_file)
