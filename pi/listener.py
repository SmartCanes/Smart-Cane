import serial
import json
import requests
import websocket
import threading
import time
import subprocess
import threading
import uuid
route_lock = threading.Lock()
active_route_id = None
route_cancel_event = threading.Event()

from math import radians, cos, sin, sqrt, atan2
from navigation.cache import get, store, set_active
from navigation.turns import extract, ACTIVE_TURNS
from navigation.tracker import update, reset


SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200
CANE_SERIAL = "SC-136901"

GRAPHOPPER_URL = "http://localhost:8989/route"
# WS_URL = "wss://middleware.icane.org"
WS_URL = "ws://localhost:3000"
PING_INTERVAL = 10

ws = None

last_location = {"lat": 14.7226, "lng": 121.0336}

DESTINATION_THRESHOLD_M = 10
final_destination = None
destination_reached = False

route_lock = threading.Lock()
active_route_id = None
route_cancel_event = threading.Event()


def connect_ws():
    global ws

    while True:
        try:
            ws = websocket.WebSocket()
            ws.connect(WS_URL)

            # Register Pi as compute node for this serial
            ws.send(json.dumps({"event": "register", "serial": CANE_SERIAL}))

            print("[WS] Connected")
            
            return

        except Exception as e:
            print("[WS] reconnecting...", e)
            time.sleep(5)


def get_route(frm, to):
    try:
        params = [
            ("point", f"{frm[0]},{frm[1]}"),
            ("point", f"{to[0]},{to[1]}"),
            ("profile", "foot"),
            ("points_encoded", "false"),
        ]

        r = requests.get(GRAPHOPPER_URL, params=params, timeout=6)

        r.raise_for_status()

        return r.json()

    except Exception as e:
        print("[GraphHopper]", e)
        return []


def haversine_m(a, b):
    lat1, lon1 = a
    lat2, lon2 = b

    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    h = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )

    return 2 * R * atan2(sqrt(h), sqrt(1 - h))


def check_destination(lat, lng):
    global destination_reached, final_destination

    if not final_destination or destination_reached:
        return

    dist = haversine_m((lat, lng), final_destination)

    if dist <= DESTINATION_THRESHOLD_M:
        print(f"[ARRIVAL] Within {DESTINATION_THRESHOLD_M}m of destination (dist={dist}m)")
        destination_reached = True

        print("[ARRIVAL] Destination reached")

        # reset navigation state
        reset()
        set_active(None)

        # notify middleware
        try:
            ws.send(json.dumps({"event": "destinationReached", "serial": CANE_SERIAL}))
        except Exception as e:
            print("[ARRIVAL WS]", e)


# ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)


def serial_loop():
    buffer = ""

    while True:
        try:
            chunk = ser.read(ser.in_waiting or 1).decode()
            buffer += chunk

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)

                if not line.strip():
                    continue

                data = json.loads(line)

                # print("[Serial] Received:", data)

                if data["event"] == "location":
                    global last_location
                    last_location = data["payload"]
                    update(
                        (last_location["lat"], last_location["lng"]),
                        ACTIVE_TURNS,
                        speak,
                    )
                    check_destination(last_location["lat"], last_location["lng"])

                    ws.send(
                      json.dumps(
                          {
                              "event": data["event"],
                              "serial": CANE_SERIAL,
                              "payload": data.get("payload"),
                          }
                      )
                    )

        except Exception as e:
            print("[Serial]", e)
            time.sleep(1)


def ws_listener():
    global ws

    while True:
        try:
            msg = ws.recv()
            data = json.loads(msg)

            if data["event"] == "requestRoute":
                global final_destination, destination_reached, active_route_id

                print("[WS] Received route request")

                if not last_location:
                    print("[Route] No GPS fix yet")
                    ws.send(
                        json.dumps(
                            {
                                "event": "routeError",
                                "serial": CANE_SERIAL,
                                "payload": "No GPS fix yet",
                            }
                        )
                    )
                    continue

                with route_lock:
                    route_cancel_event.set()

                    active_route_id = str(uuid.uuid4())
                    route_cancel_event.clear()

                    reset()
                    set_active(None)
                    ACTIVE_TURNS.clear()

                frm = (last_location["lat"], last_location["lng"])
                to = data["payload"]["to"]

                final_destination = (to[0], to[1])
                destination_reached = False

                print(f"[Route] Request from {frm} to {to}")

                cached = get(to)

                if cached:
                    route = cached
                    print("[Route] Using cached route")
                else:
                    route = get_route(frm, to)
                    store(to, route)
                    print("[Route] New route computed")

                set_active(route)
                extract(route)
                reset()

                ws.send(
                    json.dumps(
                        {
                            "event": "routeResponse",
                            "serial": CANE_SERIAL,
                            "payload": route,
                        }
                    )
                )

                coords = [
                    (lat, lon)
                    for lon, lat in route["paths"][0]["points"]["coordinates"]
                ]

                smooth_coords = interpolate_coords(coords, step_m=8)
                threading.Thread(
                    target=simulate_walk,
                    args=(smooth_coords, active_route_id, 0.5),
                    daemon=True,
                ).start()

            if data["event"] == "clearDestination":

                with route_lock:
                    route_cancel_event.set()
                    active_route_id = None

                final_destination = None
                destination_reached = False

                reset()
                set_active(None)
                ACTIVE_TURNS.clear()

                ws.send(json.dumps({
                    "event": "destinationCleared",
                    "serial": CANE_SERIAL,
                }))

                print("[NAV] Destination cleared")

            if data["event"] == "requestStatus":
                try:
                    ser.write(json.dumps({"event": "requestStatus"}).encode() + b"\n")
                    print("[Serial] Sent requestStatus to ESP32")
                    # ws.send(
                    #     json.dumps(
                    #         {
                    #             "event": "piStatus",
                    #             "serial": CANE_SERIAL,
                    #             "payload": {"alive": True},
                    #         }
                    #     )
                    # )
                except Exception as e:
                    print("[Serial] Failed to send requestStatus:", e)

        except Exception as e:
            print("[WS recv]", e)
            connect_ws()


def ping_loop():
    while True:
        try:
            ws.send(
                json.dumps(
                    {
                        "event": "piStatus",
                        "serial": CANE_SERIAL,
                        "payload": {"alive": True},
                    }
                )
            )
        except:
            connect_ws()

        time.sleep(PING_INTERVAL)


import time
from shapely.geometry import LineString


def interpolate_coords(coords, step_m=2):
    from math import radians, cos, sin, sqrt, atan2

    def haversine(a, b):
        R = 6371000  
        lat1, lon1 = a
        lat2, lon2 = b

        φ1 = radians(lat1)
        φ2 = radians(lat2)
        Δφ = radians(lat2 - lat1)
        Δλ = radians(lon2 - lon1)

        s = sin(Δφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(Δλ / 2) ** 2
        return 2 * R * atan2(sqrt(s), sqrt(1 - s))

    interp = []
    for i in range(len(coords) - 1):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[i + 1]
        distance = haversine((lat1, lon1), (lat2, lon2))
        steps = max(1, int(distance / step_m))
        for s in range(steps):
            f = s / steps
            lat = lat1 + f * (lat2 - lat1)
            lon = lon1 + f * (lon2 - lon1)
            interp.append((lat, lon))
    interp.append(coords[-1])
    return interp


def simulate_walk(route_coords, route_id, interval=0.5):
    global last_location, ws, destination_reached

    for lat, lng in route_coords:
        # Stop walking if destination was reached
        if destination_reached:
            print("[SIM] Destination reached, stopping simulation")
            break

        if route_cancel_event.is_set() or route_id != active_route_id:
            print("[SIM] Route cancelled")
            return

        print(f"[SIM] Moving to {lat}, {lng}")

        # mimic ESP32 GPS payload
        last_location = {"lat": lat, "lng": lng}

        update((lat, lng), ACTIVE_TURNS, speak)

        # check if arrived
        check_destination(lat, lng)

        # send simulated location to middleware
        try:
            ws.send(
                json.dumps(
                    {
                        "event": "location",
                        "serial": CANE_SERIAL,
                        "payload": last_location,
                    }
                )
            )
        except Exception as e:
            print("[SIM WS]", e)

        time.sleep(interval)


def speak(text):
    print(f"[SPEAK] {text}")
    subprocess.Popen(["espeak", text])


connect_ws()

# Initial location send
ws.send(
    json.dumps({
        "event": "location",
        "serial": CANE_SERIAL,
        "payload": last_location,
    })
)
print("[SIM] Initial location sent")

# threading.Thread(target=serial_loop, daemon=True).start()
threading.Thread(target=ws_listener, daemon=True).start()
threading.Thread(target=ping_loop, daemon=True).start()

print("Pi edge service running")

while True:
    time.sleep(1)
