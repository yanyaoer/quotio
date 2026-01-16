#!/usr/bin/env python3
"""
企业账户 ProfileARN 修复工具

由于企业 IAM Identity Center 账户不支持 listProfiles API,
我们需要尝试其他方法来获取或构造 profileArn。
"""

import json
import os
import urllib.request
import urllib.error


AUTH_FILE = os.path.expanduser("~/.cli-proxy-api/kiro-aws-builder-id.json")


def load_auth_file():
    """加载认证文件"""
    if not os.path.exists(AUTH_FILE):
        print(f"❌ 认证文件不存在: {AUTH_FILE}")
        return None

    with open(AUTH_FILE, 'r') as f:
        return json.load(f)


def save_auth_file(data):
    """保存认证文件"""
    with open(AUTH_FILE, 'w') as f:
        json.dump(data, f, indent=2, sort_keys=True)
    print(f"✅ 已更新认证文件: {AUTH_FILE}")


def get_user_info(access_token):
    """从 getUsageLimits 获取 userInfo"""
    url = "https://codewhisperer.us-east-1.amazonaws.com/getUsageLimits?isEmailRequired=true&origin=AI_EDITOR"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-amzn-codewhisperer-optout", "true")

    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('userInfo')
    except Exception as e:
        print(f"❌ 获取用户信息失败: {e}")
        return None


def construct_profile_arn(user_id, region="us-east-1"):
    """
    根据 userId 构造 profileArn

    企业账户的 userId 通常格式为: d-xxxxxxxxxx.xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    可能的 ProfileARN 格式:
    1. arn:aws:codewhisperer:us-east-1::profile/{userId}
    2. arn:aws:codewhisperer::{accountId}:profile/{profileId}
    3. arn:aws:sso:::profile/{userId}
    """

    # 尝试多种格式
    formats = [
        f"arn:aws:codewhisperer:{region}::profile/{user_id}",
        f"arn:aws:codewhisperer::{user_id.split('.')[0]}:profile/{user_id}",
        f"arn:aws:sso:::profile/{user_id}",
    ]

    return formats


def try_generate_completion(access_token, profile_arn):
    """测试 profileArn 是否可以用于代码补全请求"""
    url = "https://codewhisperer.us-east-1.amazonaws.com/generateCompletions"

    payload = {
        "fileContext": {
            "leftFileContent": "def hello_world():\n    print(",
            "rightFileContent": ")\n",
            "filename": "test.py",
            "programmingLanguage": {"languageName": "python"}
        },
        "profileArn": profile_arn
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "x-amzn-codewhisperer-optout": "true"
        }
    )

    try:
        with urllib.request.urlopen(req) as resp:
            print(f"  ✅ ProfileARN 有效！HTTP {resp.status}")
            return True
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"  ❌ ProfileARN 无效: HTTP {e.code}")
        print(f"     {error_body[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ 请求失败: {e}")
        return False


def main():
    print("="*70)
    print("企业账户 ProfileARN 修复工具")
    print("="*70)

    # 1. 加载认证文件
    print("\n📁 步骤 1: 加载认证文件")
    auth_data = load_auth_file()
    if not auth_data:
        return

    access_token = auth_data.get('access_token')
    if not access_token:
        print("❌ access_token 不存在")
        return

    print(f"✅ 已加载认证文件")
    print(f"   认证方式: {auth_data.get('auth_method')}")
    print(f"   区域: {auth_data.get('region')}")
    print(f"   Start URL: {auth_data.get('start_url')}")

    # 2. 检查是否已有 profileArn
    if auth_data.get('profileArn'):
        print(f"\n✅ 已有 profileArn: {auth_data['profileArn']}")

        # 测试是否有效
        print("\n🧪 测试 profileArn 是否有效...")
        if try_generate_completion(access_token, auth_data['profileArn']):
            print("\n✅ 现有 profileArn 可以正常使用，无需修复！")
            return
        else:
            print("\n⚠️  现有 profileArn 无效，尝试重新获取...")

    # 3. 获取 userInfo
    print("\n📋 步骤 2: 获取用户信息")
    user_info = get_user_info(access_token)

    if not user_info:
        print("❌ 无法获取用户信息")
        return

    user_id = user_info.get('userId')
    email = user_info.get('email')

    print(f"✅ 用户信息:")
    print(f"   userId: {user_id}")
    print(f"   email: {email or '(未提供)'}")

    # 4. 尝试构造 profileArn
    print("\n🔧 步骤 3: 尝试构造 profileArn")

    region = auth_data.get('region', 'us-east-1')
    possible_arns = construct_profile_arn(user_id, region)

    print(f"生成了 {len(possible_arns)} 种可能的 profileArn 格式:")
    for i, arn in enumerate(possible_arns, 1):
        print(f"  {i}. {arn}")

    # 5. 测试每个 profileArn
    print("\n🧪 步骤 4: 测试 profileArn 有效性")

    valid_arn = None
    for i, arn in enumerate(possible_arns, 1):
        print(f"\n测试格式 {i}: {arn}")
        if try_generate_completion(access_token, arn):
            valid_arn = arn
            break

    # 6. 如果没有找到有效的 ARN，尝试不使用 profileArn
    if not valid_arn:
        print("\n⚠️  所有 profileArn 格式都无效")
        print("\n🔧 步骤 5: 尝试不使用 profileArn 直接调用")

        # 某些配置下可能不需要 profileArn
        print("测试不带 profileArn 的请求...")
        url = "https://codewhisperer.us-east-1.amazonaws.com/generateCompletions"

        payload = {
            "fileContext": {
                "leftFileContent": "def hello_world():\n    print(",
                "rightFileContent": ")\n",
                "filename": "test.py",
                "programmingLanguage": {"languageName": "python"}
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "x-amzn-codewhisperer-optout": "true"
            }
        )

        try:
            with urllib.request.urlopen(req) as resp:
                print(f"  ✅ 不需要 profileArn！HTTP {resp.status}")
                print(f"\n💡 建议: 将 profileArn 设置为空字符串或删除该字段")

                # 删除 profileArn 字段
                if 'profileArn' in auth_data:
                    del auth_data['profileArn']
                save_auth_file(auth_data)

                print("\n✅ 修复完成！请重启代理服务")
                return
        except Exception as e:
            print(f"  ❌ 仍然失败: {e}")
            print(f"\n❌ 无法找到有效的 profileArn 配置")
            print(f"\n💡 建议:")
            print(f"   1. 检查企业账户权限配置")
            print(f"   2. 联系 IT 管理员确认 CodeWhisperer 访问权限")
            print(f"   3. 检查是否需要额外的 Scope")
            return

    # 7. 保存有效的 profileArn
    print(f"\n✅ 找到有效的 profileArn!")
    print(f"   {valid_arn}")

    # 使用下划线命名（CLIProxyAPI 期望的格式）
    auth_data['profile_arn'] = valid_arn
    # 删除驼峰命名（如果存在）
    if 'profileArn' in auth_data:
        del auth_data['profileArn']
    save_auth_file(auth_data)

    print("\n" + "="*70)
    print("✅ 修复完成！")
    print("="*70)
    print("\n📝 后续步骤:")
    print("1. 重启代理服务:")
    print("   pkill CLIProxyAPI")
    print("   python main.py proxy start")
    print("\n2. 测试代码补全:")
    print("   curl http://localhost:8317/v1/chat/completions \\")
    print("     -H 'Authorization: Bearer <your-key>' \\")
    print("     -d '{...}'")


if __name__ == '__main__':
    main()
