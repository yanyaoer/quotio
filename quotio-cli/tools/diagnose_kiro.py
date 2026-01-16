
import json
import urllib.request
import urllib.error
import os
import sys

# Define path
AUTH_FILE = os.path.expanduser("~/.cli-proxy-api/kiro-aws-builder-id.json")

def cprint(msg, color="white"):
    colors = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "white": "\033[0m",
        "cyan": "\033[96m"
    }
    print(f"{colors.get(color, '')}{msg}\033[0m")

def main():
    cprint(f"--- Kiro Auth Diagnostics ---", "cyan")
    cprint(f"Checking file: {AUTH_FILE}")

    if not os.path.exists(AUTH_FILE):
        cprint(f"[FAIL] Auth file not found at {AUTH_FILE}", "red")
        return

    try:
        with open(AUTH_FILE, 'r') as f:
            data = json.load(f)
    except Exception as e:
        cprint(f"[FAIL] Failed to parse JSON: {e}", "red")
        return

    # 1. Inspect Content
    cprint("\n1. Inspecting File Contents:", "cyan")
    
    # Check Token
    token = data.get('access_token')
    if token:
        cprint(f"  [OK] access_token found (len={len(token)})", "green")
    else:
        cprint(f"  [FAIL] access_token missing", "red")

    # Check Region
    region = data.get('region')
    cprint(f"  Result Region: {region} (Should be where your IdC is)", "white")

    # Check Scopes (inferred or saved?)
    # Note: Kiro auth file structure is flat, scopes usually not saved explicitly unless custom field
    # But we can try to decode the token roughly to see scopes?
    pass

    # Check Profile ARN
    profile_arn = data.get('profileArn')
    if profile_arn:
        cprint(f"  [OK] profileArn found: {profile_arn}", "green")
    else:
        cprint(f"  [FAIL] profileArn MISSING", "red")

    # 2. Test API Connectivity
    cprint("\n2. Testing CodeWhisperer API (us-east-1):", "cyan")
    if not token:
        cprint("Skipping API test due to missing token", "yellow")
        return

    api_host = "codewhisperer.us-east-1.amazonaws.com"
    
    # Test 2.1: getUsageLimits (Known working endpoint from Swift code)
    # GET /getUsageLimits?isEmailRequired=true&origin=AI_EDITOR
    url = f"https://{api_host}/getUsageLimits?isEmailRequired=true&origin=AI_EDITOR"
    cprint(f"  Requesting: {url} ...", "white")
    
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "aws-sdk-js/3.0.0") # Mimic Swift client
    req.add_header("x-amzn-codewhisperer-optout", "true")

    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode('utf-8')
            cprint(f"  [OK] getUsageLimits HTTP {resp.status}", "green")
            # cprint(f"  Response: {resp_body[:200]}...", "white")
    except urllib.error.HTTPError as e:
        cprint(f"  [FAIL] getUsageLimits HTTP {e.code}", "red")
        cprint(f"  Response: {e.read().decode('utf-8')}", "red")

    # Test 2.2: AWS JSON 1.1 Discovery
    cprint("\n  Testing AWS JSON 1.1 Targets...", "white")
    
    # We suspect ListProfiles might be named differently or unavailable.
    # Let's try CreateProfile with empty body again, implying default profile.
    
    potential_targets = [
        "com.amazonaws.codewhisperer.service.v1.CodeWhispererService.ListProfiles",
        "com.amazonaws.codewhisperer.service.v1.CodeWhispererService.CreateProfile",
        # Maybe it's just 'CodeWhispererService'?
        "CodeWhispererService.ListProfiles",
        # Maybe lowerCamel?
        "com.amazonaws.codewhisperer.service.v1.CodeWhispererService.listProfiles",
    ]
    
    found_working_target = False

    for target in potential_targets:
        url = f"https://{api_host}/"
        # cprint(f"  Target: {target}", "white")
        
        req = urllib.request.Request(url, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/x-amz-json-1.1")
        req.add_header("X-Amz-Target", target)
        req.add_header("x-amzn-codewhisperer-optout", "true")
        req.data = b"{}" 

        try:
            with urllib.request.urlopen(req) as resp:
                resp_body = resp.read().decode('utf-8')
                cprint(f"  [OK] Target '{target}' HTTP {resp.status}", "green")
                cprint(f"  Response: {resp_body[:300]}", "white")
                found_working_target = True
                
                # If we got profiles, print them!
                if "ListProfiles" in target:
                     parsed = json.loads(resp_body)
                     print(json.dumps(parsed, indent=2))

        except urllib.error.HTTPError as e:
            if e.code == 404:
                pass # Unknown Operation
            else:
                cprint(f"  [FAIL] Target '{target}' HTTP {e.code}", "red")
                if e.code != 404:
                    cprint(f"  Response: {e.read().decode('utf-8')}", "white")

    if not found_working_target:
        cprint("  [WARN] Could not find any working JSON 1.1 targets for Profiles.", "yellow")

if __name__ == "__main__":
    main()
