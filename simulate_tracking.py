import asyncio
import json
import requests
import websockets
import socket

# --- WINDOWS DNS PATCH ---
# This forces Python to resolve pune.localhost to 127.0.0.1
# to fix Windows-specific DNS resolution issues.
original_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(*args):
    if args[0] == "pune.localhost":
        return original_getaddrinfo("127.0.0.1", *args[1:])
    return original_getaddrinfo(*args)
socket.getaddrinfo = patched_getaddrinfo
# -------------------------

# --- CONFIGURATION ---
TENANT_HOST = "pune.localhost"
BASE_URL = f"http://{TENANT_HOST}:8000"
WS_URL = f"ws://{TENANT_HOST}:8000/ws/tracking/"
USERNAME = "admin"
PASSWORD = "admin"

def get_token():
    print(f"[*] Logging in as {USERNAME} on {BASE_URL}...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/accounts/login/", 
            json={"username": USERNAME, "password": PASSWORD}
        )
        if response.status_code == 200:
            return response.json()['access']
        else:
            print(f"[!] Login failed ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        print(f"[!] Connection Error: {e}")
        return None

async def simulate_driver():
    token = get_token()
    if not token:
        return

    # Kothrud Coordinates
    lat = 18.5074
    lng = 73.8077

    ws_uri = f"{WS_URL}?token={token}"
    
    print(f"[*] Connecting to WebSocket: {WS_URL}")
    try:
        # Now that we've patched DNS, standard connection will work!
        async with websockets.connect(ws_uri) as websocket:
            print("[+] Connected! Sending location every 5 seconds...")
            
            for i in range(20):
                lat += 0.0005
                lng += 0.0005
                payload = {"lat": round(lat, 6), "lng": round(lng, 6)}
                
                print(f"[>] Sending Location {i+1}: {payload}")
                await websocket.send(json.dumps(payload))
                await asyncio.sleep(5)
                
            print("[*] Simulation complete.")
    except Exception as e:
        print(f"[!] WebSocket Error: {e}")

if __name__ == "__main__":
    asyncio.run(simulate_driver())
