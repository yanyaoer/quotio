
# Quotio CLI

Quotio CLI is a companion tool for managing local AI proxies and authentication, specifically designed to bridge Kiro (AWS CodeWhisperer) and Gemini authentication to standard OpenAI-compatible endpoints.

## Features

- **Authentication Management**: Supports Kiro (Google OAuth & AWS Builder ID/Identity Center) and Gemini authentication.
- **Local Proxy**: Runs a local OpenAI-compatible server (`cli-proxy-api`) that translates requests to provider APIs.
- **Token Refresh**: Automatically handles token refresh for persistent sessions.
- **Cross-Platform**: Designed for macOS (and Linux/Windows compatible via Python).

## Prerequisites

- Python 3.8+
- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPIPlus) (Automatically installed)

## Installation

1. Clone authentication logic:
   ```bash
   git clone https://github.com/your-repo/quotio-cli.git
   cd quotio-cli
   ```

2. Install dependencies (standard library only for now, or check requirements.txt):
   ```bash
   pip3 install requests  # If applicable
   ```

3. Install the Proxy Binary:
   ```bash
   python3 main.py install
   ```

## Usage

### 1. Authentication

Authenticate with Kiro (AWS CodeWhisperer/Amazon Q Developer).

**Option A: Manual Flow (Recommended for Headless/Remote)**
Use this if you are on a remote server or need to verify the start URL manually.
```bash
python3 main.py auth kiro --method manual
```
Follow the on-screen prompts to copy the URL and paste the callback.

**Option B: AWS Flow (Standard)**
Opens the default browser for authentication.
```bash
python3 main.py auth kiro --method aws
```

### 2. Start Proxy

Start the local proxy server. This will also refresh any existing tokens.

```bash
python3 main.py proxy start
```

- **Stop proxy**: `python3 main.py proxy stop`
- **Restart proxy**: `python3 main.py proxy restart`
- **Check status**: `python3 main.py proxy status`

### 3. Check Models

Verify the proxy is working and list available models.

```bash
python3 main.py models list
```

## Client Configuration

### Claude Code (`claude`)

To use `claude` CLI with Quotio, you must configure `~/.claude/settings.json`.

**Important**: 
1. Set `ANTHROPIC_BASE_URL` to your local proxy.
2. **REMOVE** any native `_model` hidden preferences if they exist (e.g., `_model: claude-3-opus...`).
3. Set the top-level `"model"` field to a supported proxy model.

**Example `~/.claude/settings.json`:**

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

### Curl Test

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

## Troubleshooting

- **Proxy fails to start**: Check `~/.quotio-cli/proxy.log`.
- **403 Forbidden**: Your token might be missing scopes. Re-run `auth kiro --method manual`.
- **Profile ARN missing**: Ensure you run the latest version of `auth_server.py` which automatically fetches the profile ARN during login.

### Enterprise IAM Identity Center Accounts

For enterprise AWS IAM Identity Center accounts:

1. **Authentication**:
   ```bash
   python3 main.py auth kiro --method aws \
     --aws-start-url https://your-company.awsapps.com/start \
     --aws-region us-east-2
   ```

2. **Profile ARN Fix** (if needed):
   ```bash
   python3 tools/fix_enterprise_profile.py
   ```

3. **Token Refresh**:
   ```bash
   python3 main.py token refresh
   ```

**Known Issues**:
- ⚠️ **CLIProxyAPI Integration**: Enterprise IAM Identity Center accounts currently have compatibility issues with CLIProxyAPI. The authentication works correctly, but the proxy may not properly recognize the credentials. This is being investigated.
- For troubleshooting, see `docs/ENTERPRISE_GUIDE.md` and `docs/FIXES_SUMMARY.md`

## Tools

Additional diagnostic and maintenance tools are available in the `tools/` directory:

- `diagnose_kiro.py` - Diagnose Kiro authentication issues
- `fix_enterprise_profile.py` - Fix ProfileARN for enterprise accounts
- `test_fixes.py` - Test token management fixes
- `verify_fixes.py` - Verify all fixes are working

Run tools directly:
```bash
python3 tools/<tool_name>.py
```
