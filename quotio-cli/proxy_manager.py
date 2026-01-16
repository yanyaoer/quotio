#!/usr/bin/env python3
"""
代理管理 - 启动和管理 CLIProxyAPI 代理服务
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import stat
import platform
from pathlib import Path
from typing import Optional, List, Dict

try:
    from token_manager import TokenManager
except ImportError:
    TokenManager = None  # Fallback if file not present yet

class ProxyManager:
    """CLIProxyAPI 代理管理器"""

    GITHUB_REPO = "router-for-me/CLIProxyAPIPlus"
    BINARY_NAME = "CLIProxyAPI"

    def __init__(self, auth_dir: str = "~/.cli-proxy-api"):
        self.auth_dir = Path(auth_dir).expanduser()
        self.config_dir = Path("~/.quotio-cli").expanduser()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.pid_file = self.config_dir / "proxy.pid"
        self._process: Optional[subprocess.Popen] = None

    def _find_proxy_binary(self) -> Optional[str]:
        """查找 CLIProxyAPI 二进制文件"""
        # 优先检查本地配置目录
        local_bin = self.config_dir / self.BINARY_NAME
        if local_bin.exists():
            return str(local_bin)
            
        # 常见位置
        locations = [
            Path("/usr/local/bin") / self.BINARY_NAME,
            Path.home() / ".local/bin" / self.BINARY_NAME,
        ]
        for loc in locations:
            if loc.exists() and os.access(loc, os.X_OK):
                return str(loc)
        return None

    def install(self):
        """下载并安装 CLIProxyAPI"""
        print("Checking for latest CLIProxyAPI Release...")
        
        try:
            # 1. 获取最新 Release
            url = f"https://api.github.com/repos/{self.GITHUB_REPO}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "QuotioCLI"})
            with urllib.request.urlopen(req) as resp:
                release_info = json.loads(resp.read().decode('utf-8'))
                
            tag_name = release_info.get('tag_name', 'latest')
            print(f"Found version: {tag_name}")
            
            # 2. 确定当前平台架构
            system = platform.system().lower() # darwin, linux, windows
            machine = platform.machine().lower() # x86_64, arm64
            
            if system == 'darwin':
                target_asset_pattern = "darwin_arm64" if machine == 'arm64' else "darwin_amd64"
            elif system == 'linux':
                target_asset_pattern = "linux_arm64" if machine == 'aarch64' else "linux_amd64"
            else:
                print(f"Unsupported platform: {system}")
                return

            download_url = None
            asset_name = None
            
            for asset in release_info.get('assets', []):
                name = asset['name'].lower()
                if target_asset_pattern in name and not any(x in name for x in ['windows', 'checksum']):
                    download_url = asset['browser_download_url']
                    asset_name = asset['name']
                    break
            
            if not download_url:
                print(f"No compatible binary found for {target_asset_pattern}")
                return

            # 3. 下载
            print(f"Downloading {asset_name}...")
            print(f"URL: {download_url}")
            
            import tempfile
            import tarfile
            import zipfile
            import shutil

            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                download_path = temp_path / asset_name
                
                # Simple progress hook
                def report(block_num, block_size, total_size):
                    percent = int(block_num * block_size * 100 / total_size)
                    sys.stdout.write(f"\rDownloading... {percent}%")
                    sys.stdout.flush()

                urllib.request.urlretrieve(download_url, download_path, report)
                print("\nDownload complete. Extracting...")

                # 4. 解压
                extract_path = temp_path / "extracted"
                extract_path.mkdir()
                
                if asset_name.endswith('.tar.gz') or asset_name.endswith('.tgz'):
                    with tarfile.open(download_path, "r:gz") as tar:
                        tar.extractall(path=extract_path)
                elif asset_name.endswith('.zip'):
                    with zipfile.ZipFile(download_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_path)
                else:
                    # 假设是直接的二进制
                    print("Unknown format, assuming raw binary.")
                    shutil.copy(download_path, extract_path / self.BINARY_NAME)

                # 5. 查找二进制
                # 递归查找名为 CLIProxyAPI 的文件
                found_binary = None
                for root, dirs, files in os.walk(extract_path):
                    for file in files:
                        if file.lower() in ['cliproxyapi', 'cli-proxy-api', 'proxy']:
                             found_binary = Path(root) / file
                             break
                    if found_binary:
                        break
                
                if not found_binary:
                    # 如果找不到，尝试找任何可执行文件 (排除 .md, .txt 等)
                     for root, dirs, files in os.walk(extract_path):
                        for file in files:
                            if not file.endswith(('.md', '.txt', '.yaml', '.yml')):
                                fp = Path(root) / file
                                if os.access(fp, os.X_OK) or 'proxy' in file.lower():
                                    found_binary = fp
                                    break
                        if found_binary:
                            break

                if not found_binary:
                    print(f"Error: Could not find binary in extracted files.")
                    # list extracted files for debug
                    print("Extracted contents:")
                    for root, dirs, files in os.walk(extract_path):
                        for file in files:
                            print(f" - {file}")
                    return

                print(f"Found binary: {found_binary.name}")

                # 6. 安装
                dest_file = self.config_dir / self.BINARY_NAME
                
                # 如果存在旧的，先删除
                if dest_file.exists():
                    dest_file.unlink()
                
                shutil.copy(found_binary, dest_file)
                
                # 设置执行权限
                st = os.stat(dest_file)
                os.chmod(dest_file, st.st_mode | stat.S_IEXEC)
                print(f"Installed to: {dest_file}")
            
        except Exception as e:
            print(f"Installation failed: {e}")
            import traceback
            traceback.print_exc()

    def start(self, port: int = 8317, management_port: int = 8318):
        """启动代理服务"""
        # 1. 刷新 Token
        if TokenManager:
            print("Checking tokens...")
            try:
                tm = TokenManager()
                count = tm.refresh_all_tokens()
                if count > 0:
                    print(f"Refreshed {count} tokens.")
            except Exception as e:
                print(f"Token refresh warning: {e}")

        # 2. 查找或安装二进制
        binary = self._find_proxy_binary()
        if not binary:
            print("Proxy binary not found. Attempting to install...")
            self.install()
            binary = self._find_proxy_binary()
            if not binary:
                print("Error: Could not find or install CLIProxyAPI.")
                return

        # 检查是否已运行
        if self._is_running():
            print(f"Proxy is already running (Port {port})")
            return

        # 生成配置文件
        config = self._generate_config(port)
        config_file = self.config_dir / "config.yaml"
        
        # 简单的 YAML 生成 (避免 pyyaml 依赖问题，或者依然使用 yaml 如果环境支持)
        try:
            import yaml
            with open(config_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
        except ImportError:
            # 手动生成简单 yaml
            with open(config_file, 'w') as f:
                f.write(f"host: \"0.0.0.0\"\n")
                f.write(f"port: {port}\n")
                f.write(f"auth-dir: \"{self.auth_dir}\"\n")
                f.write(f"debug: false\n")
                f.write("routing:\n  strategy: \"round-robin\"\n")

        # 启动进程
        print(f"Starting proxy on port {port}...")
        cmd = [binary, "-config", str(config_file)]
        
        try:
            log_file = self.config_dir / "proxy.log"
            self._log_fh = open(log_file, "a") # Keep file handle open if needed, or just let Popen use it
            
            # 使用 shell=False 安全启动
            self._process = subprocess.Popen(
                cmd, 
                stdout=self._log_fh,
                stderr=subprocess.STDOUT
            )
            
            # 保存 PID
            with open(self.pid_file, 'w') as f:
                f.write(str(self._process.pid))

            time.sleep(1)
            
            # Check if process is still running
            if self._process.poll() is None:
                print(f"Proxy started successfully!")
                print(f"API Endpoint: http://localhost:{port}/v1")
                print(f"Logging to: {log_file}")
            else:
                print(f"Proxy failed to start immediately. Check log: {log_file}")
                # Read end of log
                with open(log_file, 'r') as f:
                    print(f.read()[-500:])

        except Exception as e:
            print(f"Failed to start proxy: {e}")

    def stop(self):
        """停止代理服务"""
        if not self.pid_file.exists():
            print("Proxy is not running")
            return

        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, 15)  # SIGTERM
            self.pid_file.unlink()
            print("Proxy stopped")
        except ProcessLookupError:
            self.pid_file.unlink()
            print("Proxy process not found (removed pid file)")
        except Exception as e:
            print(f"Stop failed: {e}")

    def restart(self, port: int = 8317):
        """重启代理服务"""
        self.stop()
        time.sleep(1) # Wait for port release
        self.start(port)

    def status(self):
        """检查代理状态"""
        if self._is_running():
            print("Status: RUNNING")
        else:
            print("Status: STOPPED")

    def _is_running(self) -> bool:
        """检查代理是否运行"""
        if not self.pid_file.exists():
            return False
        try:
            with open(self.pid_file, 'r') as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            return False

    def _generate_config(self, port: int) -> Dict:
        """生成代理配置"""
        return {
            "port": port,
            "host": "0.0.0.0",
            "auth-dir": str(self.auth_dir),
            "debug": False,
            "routing": {"strategy": "round-robin"},
            "providers": {
                "antigravity": {
                    "client_id": "1071006060591-tmhssin2h21lcre235vtolojh4g403ep.apps.googleusercontent.com",
                    "client_secret": "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"
                }
            }
        }

    def list_models(self, provider: Optional[str] = None):
        """列出可用模型"""
        if not self._is_running():
            print("Proxy is not running. Start it first.")
            return

        try:
            # 默认端口 8317，或者应该读取配置？这里假设默认
            url = f"http://localhost:8317/v1/models"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))

            models = data.get('data', [])
            if not models:
                print("No models available.")
                return

            print("\nAvailable Models:")
            print("-" * 50)
            for m in models:
                model_id = m.get('id', '')
                owned_by = m.get('owned_by', '')
                if provider and provider.lower() not in owned_by.lower():
                    continue
                print(f"  {model_id:<40} [{owned_by}]")
            print("-" * 50)

        except Exception as e:
            print(f"Failed to list models: {e}")
