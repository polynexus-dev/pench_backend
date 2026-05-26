import asyncio
import json
import requests
import websockets
import socket
import argparse
import sys
import time

# --- WINDOWS DNS PATCH ---
# This forces Python to resolve tenant subdomains to localhost on Windows
original_getaddrinfo = socket.getaddrinfo


def patched_getaddrinfo(*args):
    if args[0] in ["pune.localhost", "nagpur.localhost"]:
        return original_getaddrinfo("127.0.0.1", *args[1:])
    return original_getaddrinfo(*args)


socket.getaddrinfo = patched_getaddrinfo

# --- COLOR CODES FOR PREMIUM TERMINAL ---
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"

# --- COORDINATES LIST (WGS84 EPSG:4326 Nagpur) ---
NAGPUR_COORDINATES = [
    [79.048219754255, 21.17424546903328],
    [79.04836855240109, 21.17418405410072],
    [79.04851735054865, 21.1741886033559],
    [79.04855150094323, 21.17426139141925],
    [79.04865395212539, 21.17434100332254],
    [79.04867834526425, 21.174482030018027],
    [79.04860516584745, 21.174541170204776],
    [79.04856125819879, 21.174659450507946],
    [79.0486734666365, 21.174714041385556],
    [79.04868810251986, 21.1748914615972],
    [79.04860272653355, 21.174939228540566],
    [79.04859052996403, 21.17503703699694],
    [79.0485661368266, 21.175146218451886],
    [79.04870761703103, 21.17520990759752],
    [79.04878323576179, 21.175255399826895],
    [79.04898569881362, 21.175264498271247],
    [79.04914425421532, 21.175207632985675],
    [79.04920767637657, 21.17515531690293],
    [79.04932232412813, 21.17516214074088],
    [79.04941745737005, 21.17518033764044],
    [79.04962235973579, 21.17518488686501],
    [79.04966626738593, 21.175103000802437],
    [79.04970285709283, 21.174968798545834],
    [79.0497906723931, 21.1748050261361],
    [79.04973700748735, 21.174716316005032],
    [79.04964675287476, 21.174618507337215],
    [79.04959796659688, 21.174554817936965],
    [79.04965894944428, 21.174445636044823],
    [79.04943209325347, 21.17434100332254],
    [79.04935891383656, 21.174290961560004],
    [79.04926865922243, 21.174224997391704],
    [79.04903204577613, 21.174254567539776],
    [79.0487271315422, 21.17417723021768],
    [79.04854662231543, 21.17411126599933],
    [79.04833684132194, 21.174163582450632],
    [79.04818804317432, 21.17421362425695],
]


def get_auth_token(base_url, username, password):
    print(f"[*] Authenticating user '{username}' on {base_url}...")
    try:
        resp = requests.post(
            f"{base_url}/api/accounts/login/",
            json={"username": username, "password": password},
            timeout=5,
        )
        if resp.status_code == 200:
            print(f"{GREEN}[+] Authenticated successfully!{RESET}")
            return resp.json()["access"]
        else:
            print(
                f"{RED}[!] Authentication failed ({resp.status_code}): {resp.text}{RESET}"
            )
            return None
    except Exception as e:
        print(f"{RED}[!] Connection error during auth: {e}{RESET}")
        return None


async def listen_broadcasts(ws_uri):
    """Listens for websocket broadcast locations in background to verify real-time routing."""
    try:
        async with websockets.connect(ws_uri) as ws:
            print(f"{CYAN}[WS Broadcast Listener] Connected to broadcast group!{RESET}")
            while True:
                msg = await ws.recv()
                data = json.loads(msg)
                if data.get("type") == "broadcast_location":
                    print(
                        f"\n{CYAN}[WS Broadcast Received] Driver: {data.get('driver_name')}"
                    )
                    print(f"  Current: [{data.get('lng')}, {data.get('lat')}]")
                    print(
                        f"  Snaps Route points count: {len(data.get('trail', []))}{RESET}"
                    )
    except Exception as e:
        pass


async def run_simulation(host, port, username, password, interval):
    base_url = f"http://{host}:{port}"
    token = get_auth_token(base_url, username, password)
    if not token:
        print(
            f"{RED}[!] Aborting. Please check if server is running on port {port}.{RESET}"
        )
        return

    ws_uri = f"ws://{host}:{port}/ws/tracking/?token={token}"
    print(f"[*] Connecting to Live Tracking WebSocket: {ws_uri}")

    try:
        async with websockets.connect(ws_uri) as websocket:
            print(f"{GREEN}[+] Connected! Ready to stream Nagpur coordinates.{RESET}")
            print(
                f"{YELLOW}[*] Interval: {interval} seconds per ping. Total points: {len(NAGPUR_COORDINATES)}{RESET}"
            )

            step = 1
            for coord in NAGPUR_COORDINATES:
                lng, lat = coord
                payload = {"lat": round(lat, 6), "lng": round(lng, 6)}

                print(
                    f"\n{YELLOW}[->] [{step}/{len(NAGPUR_COORDINATES)}] Sending Location: {payload}{RESET}"
                )
                await websocket.send(json.dumps(payload))

                # Await instant feedback response
                try:
                    response_msg = await asyncio.wait_for(
                        websocket.recv(), timeout=10.0
                    )
                    res = json.loads(response_msg)
                    if res.get("type") == "location_update_response":
                        trail = res.get("trail", [])
                        print(
                            f"{GREEN}[<-] Server Acknowledged! Snapped Location: [{res.get('lng')}, {res.get('lat')}]{RESET}"
                        )
                        print(
                            f"{GREEN}[<-] Trail coordinates count: {len(trail)} (Successfully snapped along roads!){RESET}"
                        )
                except asyncio.TimeoutError:
                    print(f"{RED}[!] Timeout waiting for server response.{RESET}")
                except Exception as e:
                    print(f"{RED}[!] Error reading response: {e}{RESET}")

                step += 1
                await asyncio.sleep(interval)

            print(f"\n{GREEN}[+] Simulation completed successfully!{RESET}")

    except Exception as e:
        print(f"{RED}[!] WebSocket connection error: {e}{RESET}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Nagpur Live WebSockets Tracking Simulator"
    )
    parser.add_argument(
        "--host", type=str, default="nagpur.localhost", help="Tenant host name"
    )
    parser.add_argument("--port", type=str, default="8000", help="Server port")
    parser.add_argument(
        "--username", type=str, default="driver_nagpur_10", help="Driver username"
    )
    parser.add_argument(
        "--password", type=str, default="securepass123", help="Driver password"
    )
    parser.add_argument(
        "--interval", type=float, default=5.0, help="Ping interval in seconds"
    )

    args = parser.parse_args()

    try:
        asyncio.run(
            run_simulation(
                args.host, args.port, args.username, args.password, args.interval
            )
        )
    except KeyboardInterrupt:
        print(f"\n{RED}[!] Simulation stopped by user.{RESET}")
