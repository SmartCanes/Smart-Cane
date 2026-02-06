import serial
import json
import requests
import websocket
import threading
import time
import uuid
from math import radians, cos, sin, sqrt, atan2

# Import from your local modules
from navigation.cache import get, store, set_active
from navigation.turns import extract, ACTIVE_TURNS
from navigation.tracker import update, reset, haversine
from speech import (
    speech_queue,  # Import the speech queue instance
    speak,  # Main speak function (now uses queue)
    set_speaking_speed,
    set_speaking_voice,
    announce_arrival,  # Updated function name
    announce_route_start,  # Updated function name
    process_route,  # Updated function name
    announce_reroute,
    announce_upcoming_turn,  # New: for turn-by-turn
    announce_obstacle,  # For obstacle warnings
    process_and_announce_route,  # New: combined processing
    start_navigation,  # New: navigation control
    stop_navigation,  # New: navigation control
    pause_navigation,  # New: navigation control
    resume_navigation,  # New: navigation control
    get_speech_status,  # New: get queue status
    emergency_stop,  # New: emergency stop all speech
    SpeechCategory,  # New: for categorizing speech
)

route_lock = threading.Lock()
active_route_id = None
route_cancel_event = threading.Event()
current_route_info = None

SERIAL_PORT = "/dev/ttyUSB0"
SERIAL_BAUDRATE = 115200
CANE_SERIAL = "SC-136901"

GRAPHOPPER_URL = "http://localhost:8989/route"
WS_URL = "ws://localhost:3000"
PING_INTERVAL = 10

set_speaking_speed(130)
set_speaking_voice("f5")  # Using clearer voice

ws = None
last_location = {"lat": 14.7226, "lng": 121.0336}
DESTINATION_THRESHOLD_M = 8
final_destination = None
destination_reached = False

OBSTACLES = []

navigation_active = threading.Event()

# Turn announcement tracking
last_turn_distance = None
turn_announcement_thresholds = [
    100,
    50,
    30,
    15,
    5,
]  

def connect_ws():
    global ws
    while True:
        try:
            ws = websocket.WebSocket()
            ws.connect(WS_URL)
            ws.send(
                json.dumps(
                    {
                        "event": "register",
                        "serial": CANE_SERIAL,
                        "type": "blind_navigation",
                        "capabilities": [
                            "turn_by_turn",
                            "obstacle_warnings",
                            "route_guidance",
                        ],
                    }
                )
            )
            print("[WS] Connected as blind navigation device")
            return
        except Exception as e:
            print("[WS] Reconnecting...", e)
            time.sleep(5)


def get_route(frm, to, avoid_stairs=True, avoid_crosswalks=False):
    try:
        params = [
            ("point", f"{frm[0]},{frm[1]}"),
            ("point", f"{to[0]},{to[1]}"),
            ("profile", "foot"),
            ("points_encoded", "false"),
        ]

        # Add avoidance parameters
        if avoid_stairs:
            params.append(("avoid", "steps"))
            params.append(("avoid", "stairway"))
        if avoid_crosswalks:
            params.append(("avoid", "crossing"))

        r = requests.get(GRAPHOPPER_URL, params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("[GraphHopper]", e)
        return None


def haversine_m(a, b):
    """Calculate distance between two points in meters"""
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
    """Check if destination reached with blind-user confirmation"""
    global destination_reached, final_destination

    if not final_destination or destination_reached:
        return

    dist = haversine_m((lat, lng), final_destination)

    if dist <= DESTINATION_THRESHOLD_M:
        handle_arrival(dist)


def check_off_route(current_pos, route_coords, threshold=30):
    """Check if user has strayed from route"""
    if not route_coords:
        return False

    # Find closest point on route
    min_dist = float("inf")
    for coord in route_coords:
        dist = haversine_m(current_pos, coord)
        if dist < min_dist:
            min_dist = dist

    return min_dist > threshold


def process_turn_instructions(current_pos):
    """Process and announce upcoming turns based on current position"""
    global current_route_info, last_turn_distance

    if not current_route_info:
        return

    # Find distance to next turn
    next_turn_info = get_next_turn_info(current_pos)

    if not next_turn_info:
        return

    distance_to_turn = next_turn_info.get("distance_to_turn", 0)
    turn_instruction = next_turn_info.get("instruction", "")
    street_name = next_turn_info.get("street_name", "")

    # Check if we should announce this turn
    should_announce = False

    # Check threshold crossings
    for threshold in turn_announcement_thresholds:
        if (
            last_turn_distance is None
            or last_turn_distance > threshold >= distance_to_turn
        ):
            should_announce = True
            break

    # Always announce if very close
    if distance_to_turn <= 5:
        should_announce = True

    # Announce the turn
    if should_announce:
        announce_upcoming_turn(
            distance_to_turn, turn_instruction, street_name
        )
        last_turn_distance = distance_to_turn

    # If turn is passed, reset tracking
    if distance_to_turn < 1:
        last_turn_distance = None


def get_next_turn_info(current_pos):
    """Get information about the next turn"""
    global current_route_info

    if not current_route_info or "turn_instructions" not in current_route_info:
        return None

    instructions = current_route_info["turn_instructions"]
    if not instructions:
        return None

    # Find total distance traveled to each instruction point
    cumulative_distance = 0
    total_traveled = 0

    for i, instr in enumerate(instructions):
        instr_distance = instr.get("distance", 0)

        # Skip departure instruction
        if i == 0:
            cumulative_distance += instr_distance
            continue

        # Check if this instruction contains a turn
        text = instr.get("text", "").lower()
        if any(
            word in text for word in ["turn", "left", "right", "merge", "roundabout"]
        ):
            if "continue" not in text and "straight" not in text:
                # This is a turn instruction
                return {
                    "instruction": text,
                    "distance_to_turn": cumulative_distance,
                    "street_name": instr.get("street_name", ""),
                    "cumulative_distance": cumulative_distance,
                }

        cumulative_distance += instr_distance

    return None


def get_route_coordinates(route_data):
    """Extract coordinates from route data"""
    if not route_data or "paths" not in route_data:
        return []

    try:
        coords = [
            (lat, lon) for lon, lat in route_data["paths"][0]["points"]["coordinates"]
        ]
        return coords
    except Exception as e:
        print(f"[ROUTE] Error extracting coordinates: {e}")
        return []


def handle_arrival(dist):
    global destination_reached, current_route_info

    if destination_reached:
        return

    print(f"[ARRIVAL] Destination reached ({dist:.1f}m)")

    destination_reached = True

    # HARD STOP NAVIGATION
    navigation_active.clear()
    route_cancel_event.set()

    reset()
    set_active(None)
    current_route_info = None

    # REMOVE ALL ROUTE SPEECH
    speech_queue.clear(keep_critical=False)

    # ARRIVAL VOICE
    announce_arrival()

    # Notify middleware
    try:
        ws.send(
            json.dumps(
                {
                    "event": "destinationReached",
                    "serial": CANE_SERIAL,
                    "payload": {"distance": dist},
                }
            )
        )
    except Exception as e:
        print("[ARRIVAL WS]", e)


def ws_listener():
    """WebSocket listener with blind-user commands"""
    global ws, final_destination, destination_reached, active_route_id, current_route_info

    while True:
        try:
            msg = ws.recv()
            data = json.loads(msg)
            print(f"[WS] Received event: {data.get('event')}")

            if data["event"] == "requestRoute":
                print("[WS] Received route request for blind user")

                if not last_location:
                    speak(
                        "GPS signal not available. Please wait.",
                        category=SpeechCategory.STATUS,
                        wait=True,
                    )
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
                    current_route_info = None

                frm = (last_location["lat"], last_location["lng"])
                to = data["payload"]["to"]

                avoid_stairs = data["payload"].get("avoid_stairs", True)
                avoid_crosswalks = data["payload"].get("avoid_crosswalks", False)

                final_destination = (to[0], to[1])
                destination_reached = False

                route = get_route(frm, to, avoid_stairs, avoid_crosswalks)

                speak(
                    "Calculating your route. Please wait.", category=SpeechCategory.STATUS, wait=True
                )

                if not route or "paths" not in route:
                    speak(
                        "Unable to calculate route. Please try again.",
                        category=SpeechCategory.STATUS,
                        urgent=True,
                    )
                    continue

                # Process route for blind users
                current_route_info = process_route(route)

                if not current_route_info:
                    speak(
                        "Error processing route data.", category=SpeechCategory.STATUS, urgent=True
                    )
                    continue

                # Store and activate route
                store(to, route)
                set_active(route)
                extract(route)
                reset()

                # Announce route details
                announce_route_start(
                    current_route_info["total_distance"],
                    current_route_info["total_time"],
                    current_route_info["turn_count"],
                )

                # Add accessibility warnings
                if current_route_info.get("has_stairs", False):
                    speak(
                        "Warning: This route contains stairs. Use caution.",
                        category=SpeechCategory.SAFETY,
                    )
                if current_route_info.get("has_crosswalks", False):
                    speak(
                        "Route includes street crossings. Listen for traffic.",
                        category=SpeechCategory.SAFETY,
                    )

                # Send route to middleware
                ws.send(
                    json.dumps(
                        {
                            "event": "routeResponse",
                            "serial": CANE_SERIAL,
                            "payload": {
                                "route": route,
                                "turn_count": current_route_info.get("turn_count", 0),
                                "total_distance": current_route_info.get(
                                    "total_distance", 0
                                ),
                                "estimated_time": current_route_info.get(
                                    "total_time", 0
                                ),
                            },
                        }
                    )
                )

                # Start navigation simulation
                coords = get_route_coordinates(route)
                if not coords:
                    speak(
                        "Unable to extract route coordinates.",
                        category=SpeechCategory.STATUS,
                        urgent=True,
                    )
                    continue

                smooth_coords = interpolate_coords(
                    coords, step_m=3
                )  # Smaller steps for precision

                threading.Thread(
                    target=navigate_user,
                    args=(smooth_coords, active_route_id),
                    daemon=True,
                ).start()

            elif data["event"] == "clearDestination":
                print("[WS] Clearing destination")
                with route_lock:
                    route_cancel_event.set()
                    active_route_id = None

                final_destination = None
                destination_reached = False
                reset()
                set_active(None)
                ACTIVE_TURNS.clear()
                current_route_info = None

                stop_navigation()

                ws.send(
                    json.dumps(
                        {
                            "event": "destinationCleared",
                            "serial": CANE_SERIAL,
                        }
                    )
                )

            elif data["event"] == "repeatInstruction":
                print("[WS] Repeating last instruction")
                speak("Repeating last instruction.", category=SpeechCategory.STATUS)

            elif data["event"] == "requestHelp":
                print("[WS] Help requested")
                speak(
                    "Help requested. Assistance is on the way.",
                    category=SpeechCategory.SAFETY,
                    urgent=True,
                )

            elif data["event"] == "setVoiceSettings":
                speed = data["payload"].get("speed", 130)
                voice = data["payload"].get("voice", "f5")
                set_speaking_speed(speed)
                set_speaking_voice(voice)
                speak(
                    f"Voice settings updated to speed {speed}, voice {voice}.",
                    category=SpeechCategory.STATUS,
                )

            elif data["event"] == "getLocation":
                print("[WS] Location requested")
                if last_location:
                    speak(f"Current location acquired.", category=SpeechCategory.STATUS)
                else:
                    speak("Location not available.", category=SpeechCategory.STATUS, urgent=True)

            elif data["event"] == "pauseNavigation":
                print("[WS] Pausing navigation")
                pause_navigation()
                speak("Navigation paused.", category=SpeechCategory.STATUS, wait=True)

            elif data["event"] == "resumeNavigation":
                print("[WS] Resuming navigation")
                resume_navigation()
                speak("Resuming navigation.", category=SpeechCategory.STATUS)

            elif data["event"] == "emergencyStop":
                print("[WS] Emergency stop requested")
                emergency_stop()
                speak(
                    "Emergency stop activated. All navigation stopped.",
                    category=SpeechCategory.SAFETY,
                    urgent=True,
                )

            elif data["event"] == "getNavigationStatus":
                print("[WS] Navigation status requested")
                speech_status = get_speech_status()
                status_msg = {
                    "queue_size": speech_status.get("queue_size", 0),
                    "is_speaking": speech_status.get("is_speaking", False),
                    "destination_reached": destination_reached,
                    "has_active_route": active_route_id is not None,
                }
                ws.send(
                    json.dumps(
                        {
                            "event": "navigationStatus",
                            "serial": CANE_SERIAL,
                            "payload": status_msg,
                        }
                    )
                )

            elif data["event"] == "obstacleDetected":
                print("[WS] Obstacle detected")
                obstacle_data = data["payload"]
                distance = obstacle_data.get("distance", 0)
                direction = obstacle_data.get("direction", "center")
                obstacle_type = obstacle_data.get("type", "object")

                announce_obstacle(distance, direction, obstacle_type)

        except Exception as e:
            print("[WS recv]", e)
            connect_ws()


def navigate_user(route_coords, route_id):
    global last_location, destination_reached, current_route_info

    print(f"[NAV] Starting blind-user navigation with {len(route_coords)} points")

    # Track progress for turn announcements
    distance_traveled = 0
    last_position = None
    total_route_distance = sum(
        haversine_m(route_coords[i], route_coords[i + 1])
        for i in range(len(route_coords) - 1)
    )

    for i, (lat, lng) in enumerate(route_coords):
        if destination_reached:
            print("[NAV] Destination reached")
            break

        if route_cancel_event.is_set() or route_id != active_route_id:
            print("[NAV] Route cancelled")
            return

        # Update position
        current_pos = (lat, lng)
        last_location = {"lat": lat, "lng": lng}

        # Calculate distance traveled
        if last_position:
            distance_traveled += haversine_m(last_position, current_pos)
        last_position = current_pos

        # Update navigation tracker
        update(current_pos, ACTIVE_TURNS, OBSTACLES)

        # Process and announce turns
        process_turn_instructions(current_pos)

        # Check for destination
        check_destination(lat, lng)

        # Check if off-route
        if check_off_route(current_pos, route_coords):
            speak(
                "You have strayed from the route. Recalculating.",
                category=SpeechCategory.ROUTE_INFO,
                urgent=True,
            )
            announce_reroute("off_route")

            # Notify middleware
            try:
                ws.send(
                    json.dumps(
                        {
                            "event": "offRoute",
                            "serial": CANE_SERIAL,
                            "payload": {"location": last_location},
                        }
                    )
                )
            except Exception as e:
                print("[NAV WS]", e)
            break

        try:
            bearing = calculate_bearing(route_coords, i)
            ws.send(
                json.dumps(
                    {
                        "event": "location",
                        "serial": CANE_SERIAL,
                        "payload": {
                            **last_location,
                            "accuracy": 5,
                            "speed": 1.2,  # Conservative walking speed for blind users
                            "bearing": bearing,
                            "progress": (
                                (distance_traveled / total_route_distance * 100)
                                if total_route_distance > 0
                                else 0
                            ),
                        },
                    }
                )
            )
        except Exception as e:
            print("[NAV WS]", e)

        # Slower pace for blind users - allow time to process speech
        # Check speech queue size and adjust timing
        queue_size = speech_queue.get_queue_size()
        if queue_size > 3:
            # Queue is backing up, slow down more
            time.sleep(1.2)
        else:
            time.sleep(0.8)

    if not destination_reached and route_id == active_route_id:
        # If we finished the route but didn't reach destination
        speak(
            "Route completed but destination not reached.",
            category=SpeechCategory.STATUS,
            urgent=True,
        )


def interpolate_coords(coords, step_m=3):
    """Interpolate coordinates with smaller steps for blind users"""
    if not coords:
        return []

    interp = []
    for i in range(len(coords) - 1):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[i + 1]
        distance = haversine_m((lat1, lon1), (lat2, lon2))
        steps = max(1, int(distance / step_m))
        for s in range(steps):
            f = s / steps
            lat = lat1 + f * (lat2 - lat1)
            lon = lon1 + f * (lon2 - lon1)
            interp.append((lat, lon))
    interp.append(coords[-1])
    return interp


def calculate_bearing(coords, current_index):
    """Calculate bearing/direction for navigation"""
    if current_index >= len(coords) - 1:
        return 0

    lat1, lon1 = coords[current_index]
    lat2, lon2 = coords[current_index + 1]

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlon = lon2 - lon1
    x = sin(dlon) * cos(lat2)
    y = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)

    bearing = atan2(x, y)
    bearing = (bearing * 180 / 3.14159265 + 360) % 360

    return bearing


def ping_loop():
    """Keep connection alive"""
    while True:
        try:
            ws.send(
                json.dumps(
                    {
                        "event": "piStatus",
                        "serial": CANE_SERIAL,
                        "payload": {
                            "alive": True,
                            "speech_queue_size": speech_queue.get_queue_size(),
                            "active_route": active_route_id is not None,
                        },
                    }
                )
            )
        except:
            connect_ws()
        time.sleep(PING_INTERVAL)


def initialize_blind_mode():
    speak("Welcome to Smart Cane ", category=SpeechCategory.STATUS, wait=True)
    time.sleep(1)

    return True


if __name__ == "__main__":
    print("Initializing Blind Navigation System...")

    if not initialize_blind_mode():
        print("Failed to initialize blind mode")
        exit(1)

    connect_ws()

    # Send initial location
    try:
        ws.send(
            json.dumps(
                {"event": "location", "serial": CANE_SERIAL, "payload": last_location}
            )
        )
    except Exception as e:
        print(f"[INIT WS] {e}")

    # Start listener threads
    ws_thread = threading.Thread(target=ws_listener, daemon=True)
    ping_thread = threading.Thread(target=ping_loop, daemon=True)

    ws_thread.start()
    ping_thread.start()

    try:
        # Main loop - minimal work here since everything runs in threads
        while True:
            # Periodically give safety reminders if navigating
            if active_route_id and not destination_reached:
                # Give safety reminder every 2 minutes
                if int(time.time()) % 120 == 0:
                    from speech import give_safety_reminder

                    give_safety_reminder()

            time.sleep(1)

    except KeyboardInterrupt:
        print("\nShutting down blind navigation system...")
        # Clean shutdown
        stop_navigation()
        emergency_stop()
        speak("System shutting down. Goodbye.", category=SpeechCategory.STATUS, wait=True)
        print("System stopped.")
