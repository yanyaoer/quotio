#!/usr/bin/env python3
"""
Quotio CLI - 服务器端 OAuth 认证和代理管理工具

支持 Kiro (Google OAuth / AWS Builder ID) 和 Antigravity 的认证流程
在服务器上运行，通过生成回调 URL 让其他设备完成认证
"""

import argparse
import sys
from auth_server import AuthServer
from proxy_manager import ProxyManager
from credential_store import CredentialStore
from token_manager import TokenManager
from quota_fetcher import QuotaFetcher


def main():
    parser = argparse.ArgumentParser(
        description='Quotio CLI - 服务器端 OAuth 认证和代理管理',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 启动 Kiro Google OAuth 认证
  python main.py auth kiro --method google

  # 启动 Kiro AWS Builder ID 认证 (Device Code 流程)
  python main.py auth kiro --method aws

  # 启动企业 IAM Identity Center 认证（指定 Start URL 和区域）
  python main.py auth kiro --method aws --aws-start-url https://your-company.awsapps.com/start --aws-region ap-southeast-1

  # 启动 Antigravity OAuth 认证
  python main.py auth antigravity

  # 刷新所有过期或即将过期的令牌
  python main.py token refresh

  # 查看 Kiro 账户剩余 quota
  python main.py quota

  # 启动代理服务
  python main.py proxy start --port 8317

  # 列出可用模型
  python main.py models list

  # 列出已认证账户
  python main.py accounts list

  # 查看 Kiro 账户剩余 quota
  python main.py quota
'''
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # install 命令
    subparsers.add_parser('install', help='安装/更新代理服务')

    # auth 命令
    auth_parser = subparsers.add_parser('auth', help='账户认证')
    auth_parser.add_argument('provider', choices=['kiro', 'antigravity'],
                            help='认证提供商')
    auth_parser.add_argument('--method', choices=['google', 'aws', 'aws-device-code', 'manual'],
                            default='google', help='认证方式 (仅 Kiro: google/aws/aws-device-code/manual)')
    auth_parser.add_argument('--port', type=int, default=8765,
                            help='OAuth 回调服务器端口')
    auth_parser.add_argument('--host', default='0.0.0.0',
                            help='OAuth 回调服务器绑定地址')
    auth_parser.add_argument('--callback-host',
                            help='回调地址的主机名/IP (默认自动检测)')
    auth_parser.add_argument('--aws-start-url', '--starturl', dest='aws_start_url',
                            help='AWS IAM Identity Center Start URL (企业账户, 如 https://your-company.awsapps.com/start)')
    auth_parser.add_argument('--aws-region', '--region', dest='aws_region', default='us-east-1',
                            help='AWS 区域 (默认 us-east-1)')

    # proxy 命令
    proxy_parser = subparsers.add_parser('proxy', help='代理服务管理')
    proxy_subparsers = proxy_parser.add_subparsers(dest='action')

    start_parser = proxy_subparsers.add_parser('start', help='启动代理')
    start_parser.add_argument('--port', type=int, default=8317,
                             help='代理服务端口')
    start_parser.add_argument('--management-port', type=int, default=8318,
                             help='管理 API 端口')

    stop_parser = proxy_subparsers.add_parser('stop', help='停止代理')
    restart_parser = proxy_subparsers.add_parser('restart', help='重启代理')
    status_parser = proxy_subparsers.add_parser('status', help='查看状态')

    # models 命令
    models_parser = subparsers.add_parser('models', help='模型管理')
    models_subparsers = models_parser.add_subparsers(dest='action')

    list_parser = models_subparsers.add_parser('list', help='列出可用模型')
    list_parser.add_argument('--provider', help='按提供商过滤')

    # accounts 命令
    accounts_parser = subparsers.add_parser('accounts', help='账户管理')
    accounts_subparsers = accounts_parser.add_subparsers(dest='action')
    accounts_subparsers.add_parser('list', help='列出已认证账户')

    # token 命令（新增）
    token_parser = subparsers.add_parser('token', help='令牌管理')
    token_subparsers = token_parser.add_subparsers(dest='action')
    refresh_parser = token_subparsers.add_parser('refresh', help='刷新所有过期或即将过期的令牌')
    refresh_parser.add_argument('--verbose', '-v', action='store_true',
                               help='显示详细信息')

    # quota 命令（新增）
    quota_parser = subparsers.add_parser('quota', help='查看账户剩余 quota')
    quota_parser.add_argument('account', nargs='?', default='kiro',
                             choices=['kiro'],
                             help='账户类型 (默认: kiro)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == 'auth':
        handle_auth(args)
    elif args.command == 'proxy':
        handle_proxy(args)
    elif args.command == 'models':
        handle_models(args)
    elif args.command == 'accounts':
        handle_accounts(args)
    elif args.command == 'token':
        handle_token(args)
    elif args.command == 'quota':
        handle_quota(args)
    elif args.command == 'install':
        handle_install(args)


def handle_install(args):
    """处理安装命令"""
    manager = ProxyManager()
    manager.install()


def handle_auth(args):
    """处理认证命令"""
    server = AuthServer(
        host=args.host,
        port=args.port,
        callback_host=args.callback_host,
        aws_start_url=args.aws_start_url,
        aws_region=args.aws_region
    )

    if args.provider == 'kiro':
        if args.method == 'aws' or args.method == 'aws-device-code':
            server.start_kiro_aws_auth()
        elif args.method == 'manual':
            server.start_kiro_manual_auth()
        else:
            server.start_kiro_google_auth()
    elif args.provider == 'antigravity':
        server.start_antigravity_auth()


def handle_proxy(args):
    """处理代理命令"""
    manager = ProxyManager()

    if args.action == 'start':
        manager.start(port=args.port, management_port=args.management_port)
    elif args.action == 'stop':
        manager.stop()
    elif args.action == 'restart':
        manager.restart()
    elif args.action == 'status':
        manager.status()
    else:
        print("请指定操作: start, stop, status")


def handle_models(args):
    """处理模型命令"""
    manager = ProxyManager()

    if args.action == 'list':
        manager.list_models(provider=args.provider)
    else:
        print("请指定操作: list")


def handle_accounts(args):
    """处理账户命令"""
    store = CredentialStore()

    if args.action == 'list':
        store.list_accounts()
    else:
        print("请指定操作: list")


def handle_token(args):
    """处理令牌管理命令"""
    if args.action == 'refresh':
        manager = TokenManager()
        print("\n开始刷新令牌...")
        print("=" * 60)
        count = manager.refresh_all_tokens(verbose=args.verbose)
        print("=" * 60)
        print(f"\n✓ 已刷新 {count} 个令牌")
    else:
        print("请指定操作: refresh")


def handle_quota(args):
    """处理 quota 查询命令"""
    fetcher = QuotaFetcher()
    success = fetcher.fetch_and_display_quota(args.account)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
