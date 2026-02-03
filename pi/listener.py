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

last_location = None


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

        r.raise_for_status()

        return r.json()

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

                if data["event"] == "location":
                    global last_location
                    last_location = data["payload"]

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


def ws_listener():
    global ws

    while True:
        try:
            msg = ws.recv()
            data = json.loads(msg)

            if data["event"] == "requestRoute":

                if not last_location:
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

                frm = (last_location["lat"], last_location["lng"])
                to = data["payload"]["to"]

                route = get_route(frm, to)

                ws.send(
                    json.dumps(
                        {
                            "event": "routeResponse",
                            "serial": CANE_SERIAL,
                            "payload": route,
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


connect_ws()

threading.Thread(target=serial_loop, daemon=True).start()
threading.Thread(target=ws_listener, daemon=True).start()
threading.Thread(target=ping_loop, daemon=True).start()

print("Pi edge service running")

while True:
    time.sleep(1)
