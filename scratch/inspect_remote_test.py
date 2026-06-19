import requests
import json
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# We will test two possible BASE_URLs:
# 1. Via domain name
# 2. Via VM IP and port with Host headers

urls_to_test = [
    {
        "url": "https://pench-nagpur.pench.api.polynexus.in/api/accounts/login/",
        "headers": {"Content-Type": "application/json"},
        "desc": "Domain with hyphen"
    },
    {
        "url": "https://pench_nagpur.pench.api.polynexus.in/api/accounts/login/",
        "headers": {"Content-Type": "application/json"},
        "desc": "Domain with underscore"
    },
    {
        "url": "http://13.235.143.251:8083/api/accounts/login/",
        "headers": {"Host": "pench-nagpur.pench.api.polynexus.in", "Content-Type": "application/json"},
        "desc": "IP:8083 with hyphen Host header"
    },
    {
        "url": "http://13.235.143.251:8083/api/accounts/login/",
        "headers": {"Host": "pench_nagpur.pench.api.polynexus.in", "Content-Type": "application/json"},
        "desc": "IP:8083 with underscore Host header"
    }
]

payload = {"username": "admin", "password": "admin"}

for test in urls_to_test:
    print(f"\n--- Testing: {test['desc']} ---")
    print(f"URL: {test['url']}")
    print(f"Headers: {test['headers']}")
    try:
        res = requests.post(test['url'], json=payload, headers=test['headers'], verify=False, timeout=10)
        print(f"Status Code: {res.status_code}")
        print(f"Response: {res.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")
