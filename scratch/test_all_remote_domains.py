import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

domains = [
    "https://nagpur.pench.api.polynexus.in",
    "https://nagpur.pench.dev.api.polynexus.in",
    "https://pench-nagpur.pench.api.polynexus.in",
    "https://pench-nagpur.pench.dev.api.polynexus.in",
    "http://13.235.143.251",  # Public IP from docker-compose
    "http://13.235.143.251:8000"
]

for base_url in domains:
    url = f"{base_url}/api/accounts/login/"
    try:
        response = requests.post(url, json={"username": "admin", "password": "admin"}, verify=False, timeout=5)
        print(f"URL: {url} -> Status: {response.status_code}")
        if response.status_code == 200:
            print("  SUCCESS!")
            print(f"  Response: {response.json()}")
        elif response.status_code != 404:
            print(f"  Response: {response.text[:200]}")
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")
