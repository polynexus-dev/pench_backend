import asyncio
import json
import requests
import websockets
import socket
import random
import time

# --- WINDOWS DNS PATCH ---
# This forces Python to resolve tenant subdomains to localhost
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

# Use a staff user or driver user
USERNAME = "driver_nagpur"
PASSWORD = "admin123" 

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

async def simulate_driver():
    token = get_token()
    if not token:
        print("[!] Aborting simulation due to login failure.")
        return

    # Starting Coordinates (Kothrud, Pune)
    lat = 18.5074
    lng = 73.8077

    ws_uri = f"{WS_URL}?token={token}"
    
    print(f"[*] Connecting to WebSocket: {WS_URL}")
    while True: # Keep trying to reconnect
        try:
            async with websockets.connect(ws_uri) as websocket:
                print("[+] Connected! Sending location every 3 seconds...")
                
                step = 0
                while True:
                    # Simulate movement in a jittery path
                    lat += (random.random() - 0.5) * 0.0005 + 0.0002
                    lng += (random.random() - 0.5) * 0.0005 + 0.0002
                    
                    payload = {
                        "lat": round(lat, 6), 
                        "lng": round(lng, 6)
                    }
                    
                    print(f"[>] [{step}] Sending Location: {payload}")
                    await websocket.send(json.dumps(payload))
                    
                    step += 1
                    await asyncio.sleep(3)
                    
        except Exception as e:
            print(f"[!] WebSocket Error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(simulate_driver())
    except KeyboardInterrupt:
        print("\n[*] Simulation stopped by user.")

