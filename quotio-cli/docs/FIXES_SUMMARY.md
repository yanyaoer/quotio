# Python CLI Kiro 企业账户处理修复总结

## 📋 概述

本次修复参考 Swift 实现，对 Python CLI 版本进行了全面改进，修复了企业 IAM Identity Center 账户处理中的关键问题。

---

## ✅ 已修复的问题

### 1. 区域硬编码问题（严重）

**问题描述**:
- Token Manager 中硬编码了 `us-east-1` 作为 IdC 令牌刷新端点
- 导致非 us-east-1 区域的企业账户无法刷新令牌

**修复内容**:
```python
# 修复前 (token_manager.py:20)
KIRO_IDC_Token_URL = "https://oidc.us-east-1.amazonaws.com/token"

# 修复后 (token_manager.py:119-180)
region = token_data.get('region', 'us-east-1')
endpoint = f"https://oidc.{region}.amazonaws.com/token"
```

**影响范围**:
- 所有非 us-east-1 区域的企业 IAM Identity Center 用户
- 例如：ap-southeast-1、eu-west-1 等区域的企业客户

---

### 2. 缺少令牌刷新功能

**问题描述**:
- Python CLI 没有实现令牌刷新逻辑
- Swift 实现中有完整的前置刷新（5分钟缓冲）和响应式刷新

**修复内容**:
- ✅ 创建了完整的 `TokenManager` 类
- ✅ 实现了过期检测和刷新缓冲逻辑（5分钟提前刷新）
- ✅ 支持 Social (Google OAuth) 和 IdC (AWS Builder ID/IAM Identity Center) 两种认证方式
- ✅ 添加了 `python main.py token refresh` 命令

**参考代码**:
- Swift: `KiroQuotaFetcher.swift:116-174` (过期检测)
- Swift: `KiroQuotaFetcher.swift:294-405` (令牌刷新)

---

### 3. 缺少 AWS SSO Cache 凭证补全

**问题描述**:
- Swift 实现有自动从 `~/.aws/sso/cache/` 补全 IdC 凭证的功能
- Python CLI 缺少这个优化

**修复内容**:
- ✅ 实现了 `_load_kiro_device_registration()` 方法
- ✅ 自动从 AWS CLI/IDE 的 SSO cache 中补全缺失的 `client_id` 和 `client_secret`
- ✅ 支持两种加载方式：
  1. 从 `kiro-auth-token.json` 读取 `clientIdHash`
  2. 回退扫描所有 JSON 文件

**参考代码**:
- Swift: `DirectAuthFileService.swift:376-416`

---

### 4. ProfileARN 获取失败提示不友好

**问题描述**:
- 某些企业账户无法访问 `listProfiles` API
- 原有错误提示不够清晰

**修复内容**:
- ✅ 增强了错误提示信息
- ✅ 明确说明 ProfileARN 缺失不影响核心功能（额度查询）
- ✅ 区分不同的失败场景（HTTP 错误、空 profiles、缺少 ARN 字段等）

**修复位置**: `auth_server.py:591-627`

---

## 🎯 新增功能

### 令牌管理命令

```bash
# 刷新所有过期或即将过期的令牌
python main.py token refresh

# 显示详细信息
python main.py token refresh --verbose
```

### 企业账户认证示例

```bash
# 企业 IAM Identity Center 认证（指定区域）
python main.py auth kiro --method aws \
  --aws-start-url https://your-company.awsapps.com/start \
  --aws-region ap-southeast-1
```

---

## 📊 测试结果

运行 `python test_fixes.py` 的结果：

```
✓ 测试 1: 区域动态读取 - 通过
✓ 测试 2: 令牌过期检测 - 通过
✓ 测试 3: AWS SSO 凭证加载 - 通过
✓ 测试 4: 凭证补全逻辑 - 通过

测试结果: 4/4 通过
```

---

## 🔧 技术细节

### Token Manager 核心逻辑

1. **过期检测**（`_should_refresh`）
   - 5 分钟缓冲时间（300秒）
   - 返回 `(should_refresh: bool, reason: str)`
   - 详细说明过期原因

2. **令牌刷新**（`_refresh_token`）
   - Social: 调用 `prod.us-east-1.auth.desktop.kiro.dev/refreshToken`
   - IdC: 动态构建 `https://oidc.{region}.amazonaws.com/token`
   - 自动持久化到磁盘

3. **凭证补全**（`_load_and_complement_credentials`）
   - 仅对 IdC 账户生效
   - 从 `~/.aws/sso/cache/` 加载
   - 自动保存到认证文件

---

## 📝 与 Swift 实现的对比

| 功能 | Swift | Python (修复前) | Python (修复后) |
|------|-------|----------------|----------------|
| **令牌刷新** | ✅ | ❌ | ✅ |
| **区域动态读取** | ❌ (硬编码) | ❌ | ✅ |
| **凭证补全** | ✅ | ❌ | ✅ |
| **5分钟缓冲** | ✅ | ❌ | ✅ |
| **详细错误提示** | ⚠️ | ⚠️ | ✅ |

**结论**: Python CLI 现在在企业账户处理上**优于 Swift 实现**，因为同时修复了区域硬编码问题。

---

## 🚀 建议后续改进

1. **Swift 端修复**
   - 同步修复 `KiroQuotaFetcher.swift:67` 的区域硬编码问题
   - 从 `tokenData.extras["region"]` 动态读取

2. **多 Profile 支持**
   - 当前只取第一个 Profile
   - 可考虑支持用户选择或显示所有 Profile

3. **自动刷新集成**
   - 在 Proxy 启动时自动刷新令牌
   - 添加后台定时刷新任务

4. **诊断工具改进**
   - 扩展 `diagnose_kiro.py` 支持企业账户
   - 添加区域检测和验证

---

## 📚 参考文件

### 修改的文件
- `token_manager.py` - 令牌管理器（完整重写）
- `auth_server.py` - ProfileARN 获取优化
- `main.py` - 添加 token 命令

### 新增文件
- `test_fixes.py` - 修复验证测试

### Swift 参考
- `Quotio/Services/QuotaFetchers/KiroQuotaFetcher.swift`
- `Quotio/Services/DirectAuthFileService.swift`

---

## ✨ 总结

本次修复完全参考了 Swift 实现的最佳实践，并修复了 Swift 中存在的区域硬编码问题。Python CLI 现在对企业 IAM Identity Center 账户的支持更加完备和健壮。

**关键改进**:
1. ✅ 修复区域硬编码（严重问题）
2. ✅ 添加令牌刷新功能
3. ✅ 实现凭证自动补全
4. ✅ 优化错误提示
5. ✅ 添加测试验证

所有测试通过，代码已准备投入生产使用。
