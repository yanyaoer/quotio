# Quota Command Example

## Command

```bash
python3 main.py quota
```

## Expected Output

```
正在查询 kiro 账户的 quota 信息...

======================================================================
Kiro 账户使用情况
======================================================================

📧 用户信息:
   Email: user@example.com
   User ID: d-xxxxx.xxxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

📦 订阅信息:
   订阅类型: Amazon Q Developer Free Tier
   类型: FREE_TIER

🔄 距离下次重置: 25 天

📊 使用明细:

   Agentic Requests (AGENTIC_REQUEST):
      当前使用: 12.0
      使用限制: 50.0
      剩余额度: 38.0 (76.0%)
      进度: [███████░░░░░░░░░░░░░░░░░░░░░░░] 24.0%

   Code Completions (CODE_COMPLETION):
      当前使用: 234.0
      使用限制: 1000.0
      剩余额度: 766.0 (76.6%)
      进度: [███████░░░░░░░░░░░░░░░░░░░░░░░] 23.4%

======================================================================
```

## Features

- **User Information**: Shows email and user ID from AWS account
- **Subscription Type**: Displays current subscription tier (Free/Pro)
- **Usage Breakdown**: Shows detailed usage for each resource type
- **Visual Progress Bars**: Easy-to-read progress indicators
- **Remaining Quota**: Calculates and displays remaining quota percentage
- **Reset Time**: Shows days until quota reset

## Error Handling

If the access token is expired:

```
❌ 获取 quota 信息失败
   可能的原因:
   1. Access token 已过期，请运行: python3 main.py token refresh
   2. 网络连接问题
   3. API 暂时不可用
```

## API Details

This command calls the CodeWhisperer API endpoint:

```
GET https://codewhisperer.us-east-1.amazonaws.com/getUsageLimits
```

With parameters:
- `isEmailRequired=true`
- `origin=AI_EDITOR`
- `resourceType=AGENTIC_REQUEST`

The API returns detailed usage information for all resource types associated with your account.
