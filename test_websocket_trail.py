import asyncio
import json
import requests
import websockets
import socket
import time

# --- WINDOWS DNS PATCH ---
original_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(*args):
    if args[0] in ["pune.localhost", "nagpur.localhost"]:
        return original_getaddrinfo("127.0.0.1", *args[1:])
    return original_getaddrinfo(*args)
socket.getaddrinfo = patched_getaddrinfo

# --- CONFIGURATION ---
TENANT_HOST = "nagpur.localhost"
PORT = "8083"
BASE_URL = f"http://{TENANT_HOST}:{PORT}"
WS_URL = f"ws://{TENANT_HOST}:{PORT}/ws/tracking/"

# Using the driver account from the demo script
USERNAME = "driver_nagpur" # This might vary, check generate_comprehensive_demo.py
PASSWORD = "admin123" # Adjust if needed

def get_token():
    print(f"[*] Logging in as {USERNAME} on {BASE_URL}...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/accounts/login/", 
            json={"username": USERNAME, "password": PASSWORD},
            timeout=5
        )
        if response.status_code == 200:
            return response.json()['access']
        else:
            print(f"[!] Login failed ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        print(f"[!] Connection Error: {e}")
        return None

async def test_trail():
    token = get_token()
    if not token:
        return

    ws_uri = f"{WS_URL}?token={token}"
    
    print(f"[*] Connecting to WebSocket: {WS_URL}")
    try:
        async with websockets.connect(ws_uri) as websocket:
            print("[+] Connected!")
            
            # Send first location
            lat, lng = 21.1458, 79.0882 # Nagpur center
            payload = {"lat": lat, "lng": lng}
            print(f"[>] Sending Location 1: {payload}")
            await websocket.send(json.dumps(payload))
            
            # Wait for response
            response = await websocket.recv()
            print(f"[<] Received Response 1: {json.loads(response)}")
            
            await asyncio.sleep(2)
            
            # Send second location (slightly moved)
            lat += 0.0005
            lng += 0.0005
            payload = {"lat": lat, "lng": lng}
            print(f"[>] Sending Location 2: {payload}")
            await websocket.send(json.dumps(payload))
            
            # Wait for response
            response = await websocket.recv()
            data = json.loads(response)
            print(f"[<] Received Response 2: {data}")
            
            if "trail" in data:
                print(f"[!] SUCCESS: Trail received with {len(data['trail'])} points.")
                print(f"    Sample trail point: {data['trail'][-1]}")
            else:
                print("[?] FAILED: No trail in response.")

    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_trail())
