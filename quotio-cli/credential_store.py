#!/usr/bin/env python3
"""
凭据存储 - 管理 OAuth token 和认证文件
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional


class CredentialStore:
    """凭据存储管理"""

    def __init__(self, auth_dir: str = "~/.cli-proxy-api"):
        self.auth_dir = Path(auth_dir).expanduser()
        self.auth_dir.mkdir(parents=True, exist_ok=True)

    def save_auth_file(self, provider: str, identifier: str, data: Dict):
        """保存认证文件"""
        # 清理标识符用于文件名
        safe_id = identifier.replace("@", "_").replace(".", "_")
        filename = f"{provider}-{safe_id}.json"
        filepath = self.auth_dir / filename

        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"凭据已保存: {filepath}")

    def load_auth_file(self, provider: str, identifier: str) -> Optional[Dict]:
        """加载认证文件"""
        safe_id = identifier.replace("@", "_").replace(".", "_")
        filename = f"{provider}-{safe_id}.json"
        filepath = self.auth_dir / filename

        if not filepath.exists():
            return None

        with open(filepath, 'r') as f:
            return json.load(f)

    def list_auth_files(self, provider: Optional[str] = None) -> List[Dict]:
        """列出所有认证文件"""
        files = []
        for filepath in self.auth_dir.glob("*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    data['_filename'] = filepath.name
                    data['_filepath'] = str(filepath)

                    if provider and data.get('type') != provider:
                        continue
                    files.append(data)
            except Exception:
                continue
        return files

    def list_accounts(self):
        """列出已认证账户"""
        files = self.list_auth_files()

        if not files:
            print("没有已认证的账户")
            return

        print("\n已认证账户:")
        print("-" * 50)

        for f in files:
            provider = f.get('type', 'unknown')
            email = f.get('email', '')
            method = f.get('auth_method', '')
            filename = f.get('_filename', '')

            status = "有效"
            if f.get('expires_at'):
                from datetime import datetime
                try:
                    exp = datetime.fromisoformat(f['expires_at'].replace('Z', '+00:00'))
                    if exp < datetime.now(exp.tzinfo):
                        status = "已过期"
                except Exception:
                    pass

            print(f"  [{provider}] {email or filename}")
            print(f"    认证方式: {method}, 状态: {status}")

        print("-" * 50)
