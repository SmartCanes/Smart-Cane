import serial
import json
import requests
import websocket
import threading
import time

SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200
CANE_SERIAL = "SC-136901"

GRAPHOPPER_URL = "http://localhost:8989/route"
WS_URL = "wss://middleware.icane.org"
PING_INTERVAL = 10

ws = None


# ---------------- WS CONNECT ----------------


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


# ---------------- GRAPHOPPER ----------------


def get_route(frm, to):
    try:
        params = [
            ("point", f"{frm[0]},{frm[1]}"),
            ("point", f"{to[0]},{to[1]}"),
            ("profile", "foot"),
            ("points_encoded", "false"),
        ]

        r = requests.get(GRAPHOPPER_URL, params=params, timeout=6)
        print(r.url)
        r.raise_for_status()

        return r.json()["paths"][0]["points"]["coordinates"]

    except Exception as e:
        print("[GraphHopper]", e)
        return []


# ---------------- SERIAL ----------------

ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)


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

                # forward ESP32 payload directly to middleware
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


# ---------------- WS LISTENER ----------------


def ws_listener():
    global ws

    while True:
        try:
            msg = ws.recv()
            data = json.loads(msg)

            if data["event"] == "requestRoute":
                frm = data["payload"]["from"]
                to = data["payload"]["to"]

                print("[Route] computing")

                route = get_route(frm, to)
                print(route)

                ws.send(
                    json.dumps(
                        {
                            "event": "routeResponse",
                            "serial": CANE_SERIAL,
                            "route": route,
                        }
                    )
                )

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


# ---------------- START ----------------

connect_ws()

threading.Thread(target=serial_loop, daemon=True).start()
threading.Thread(target=ws_listener, daemon=True).start()
threading.Thread(target=ping_loop, daemon=True).start()

print("Pi edge service running")

while True:
    time.sleep(1)
