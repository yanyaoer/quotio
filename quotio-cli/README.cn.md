
# Quotio CLI

Quotio CLI 是一个辅助工具，用于管理本地 AI 代理和认证，旨在将 Kiro (AWS CodeWhisperer) 和 Gemini 的认证桥接到标准的 OpenAI 兼容接口。

## 功能特性

- **认证管理**: 支持 Kiro (Google OAuth & AWS Builder ID/Identity Center) 和 Gemini 认证。
- **本地代理**: 运行本地 OpenAI 兼容服务器 (`cli-proxy-api`)，将请求转发到对应提供商 API。
- **Token 刷新**: 自动处理持久会话的 Token 刷新。
- **跨平台**: 专为 macOS 设计 (通过 Python 兼容 Linux/Windows)。

## 环境要求

- Python 3.8+
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPIPlus) (自动安装)

## 安装步骤

1. 克隆仓库:
   ```bash
   git clone https://github.com/your-repo/quotio-cli.git
   cd quotio-cli
   ```

2. 安装依赖 (目前仅需标准库，或检查 requirements.txt):
   ```bash
   pip3 install requests
   ```

3. 安装代理二进制文件:
   ```bash
   python3 main.py install
   ```

## 使用指南

### 1. 认证 (Authentication)

认证 Kiro (AWS CodeWhisperer/Amazon Q Developer)。

**选项 A: 手动流程 (Manual Flow) —— 推荐用于无头服务器/远程环境**
如果你在远程服务器上或需要手动确认 Start URL，请使用此模式。
```bash
python3 main.py auth kiro --method manual
```
跟随屏幕提示复制 URL 并在浏览器登录，然后将回调 URL 粘贴回终端。

**选项 B: AWS 流程 (Standard)**
自动打开默认浏览器进行认证。
```bash
python3 main.py auth kiro --method aws
```

### 2. 启动代理 (Start Proxy)

启动本地代理服务器。启动时会自动刷新过期的 Token。

```bash
python3 main.py proxy start
```

- **停止代理**: `python3 main.py proxy stop`
- **重启代理**: `python3 main.py proxy restart`
- **检查状态**: `python3 main.py proxy status`

### 3. 检查模型 (Check Models)

验证代理是否工作正常并列出可用模型。

```bash
python3 main.py models list
```

## 客户端配置

### Claude Code (`claude`)

要让 `claude` CLI 使用 Quotio 代理，你需要编辑配置文件 `~/.claude/settings.json`。

**重要提示**: 
1. 设置 `ANTHROPIC_BASE_URL` 为你的本地代理地址。
2. **移除 (REMOVE)** 任何原生的 `_model` 隐藏配置项 (例如 `_model: claude-3-opus...`)，如果存在的话。
3. 必须设置顶层的 `"model"` 字段为代理支持的模型名称。

**`~/.claude/settings.json` 配置示例:**

```json
{
  "model": "gemini-claude-opus-4-5-thinking",
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:8317",
    "ANTHROPIC_AUTH_TOKEN": "sk-dummy",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "gemini-claude-opus-4-5-thinking",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "gemini-claude-sonnet-4-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "gemini-3-flash-preview"
  }
}
```

### Curl 测试

```bash
curl http://localhost:8317/v1/chat/completions \
  -H "Authorization: Bearer sk-dummy" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-claude-opus-4-5-thinking",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

## 常见问题 (Troubleshooting)

- **代理启动失败**: 检查日志 `~/.quotio-cli/proxy.log`。
- **403 Forbidden**: Token 可能缺少权限范围 (Scopes)。请重新运行 `auth kiro --method manual` 进行认证。
- **Profile ARN missing**: 确保你使用的是最新版的 `auth_server.py`，它会在登录时自动获取 Profile ARN。

### 企业 IAM Identity Center 账户

针对企业 AWS IAM Identity Center 账户：

1. **认证**:
   ```bash
   python3 main.py auth kiro --method aws \
     --aws-start-url https://your-company.awsapps.com/start \
     --aws-region us-east-2
   ```

2. **修复 Profile ARN** (如需要):
   ```bash
   python3 tools/fix_enterprise_profile.py
   ```

3. **刷新 Token**:
   ```bash
   python3 main.py token refresh
   ```

**已知问题**:
- ⚠️ **CLIProxyAPI 集成问题**: 企业 IAM Identity Center 账户目前与 CLIProxyAPI 存在兼容性问题。认证流程本身工作正常，但代理可能无法正确识别凭证。此问题正在调查中。
- 详细的故障排查信息请参见 `docs/ENTERPRISE_GUIDE.md` 和 `docs/FIXES_SUMMARY.md`

## 工具 (Tools)

`tools/` 目录下提供了额外的诊断和维护工具：

- `diagnose_kiro.py` - 诊断 Kiro 认证问题
- `fix_enterprise_profile.py` - 修复企业账户的 ProfileARN
- `test_fixes.py` - 测试 Token 管理修复
- `verify_fixes.py` - 验证所有修复是否正常工作

直接运行工具：
```bash
python3 tools/<tool_name>.py
```
