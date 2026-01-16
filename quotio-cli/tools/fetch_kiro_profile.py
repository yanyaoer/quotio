
import json
import urllib.request
import urllib.error
import os

AUTH_FILE = os.path.expanduser("~/.cli-proxy-api/kiro-aws-builder-id.json")

def main():
    if not os.path.exists(AUTH_FILE):
        print(f"Error: {AUTH_FILE} not found.")
        return

    with open(AUTH_FILE, 'r') as f:
        data = json.load(f)

    access_token = data.get('access_token')
    if not access_token:
        print("Error: access_token not found in auth file.")
        return

    # region = data.get('region', 'us-east-1')
    # CodeWhisperer API usually lives in us-east-1
    region = "us-east-1"
    host = f"codewhisperer.{region}.amazonaws.com"
    
    print(f"Using region: {region}")
    print(f"Using host: {host}")

    # Try listProfiles
    print("\nAttempting to list profiles...")
    # It might be /listProfiles or /GetProfile
    # Based on open source investigations, CodeWhisperer API often has CreateProfile
    
    # 1. CreateProfile (idempotent?)
    call_api(host, "/createProfile", access_token, method="POST", data={})

    # 2. ListProfiles
    call_api(host, "/listProfiles", access_token, method="GET")

    # 3. GetUsageLimits (known working)
    call_api(host, "/getUsageLimits", access_token, method="GET")

def call_api(host, path, token, method="GET", data=None):
    url = f"https://{host}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "x-amzn-codewhisperer-optout": "true" # Required sometimes
    }
    
    body = None
    if data is not None:
        body = json.dumps(data).encode('utf-8')

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"[{method} {path}] Success: {resp.status}")
            resp_body = resp.read().decode('utf-8')
            try:
                parsed = json.loads(resp_body)
                print(json.dumps(parsed, indent=2))
            except:
                print(resp_body)
    except urllib.error.HTTPError as e:
        print(f"[{method} {path}] Failed: {e.code}")
        print(e.read().decode('utf-8'))
    except Exception as e:
        print(f"[{method} {path}] Error: {e}")

if __name__ == "__main__":
    main()
