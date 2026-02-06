# navigation/turns.py
import json
from math import radians, cos, sin, sqrt, atan2

ACTIVE_TURNS = []


def haversine(a, b):
    """Calculate distance between two points in meters"""
    R = 6371000
    lat1, lon1 = a
    lat2, lon2 = b

    φ1 = radians(lat1)
    φ2 = radians(lat2)
    Δφ = radians(lat2 - lat1)
    Δλ = radians(lon2 - lon1)

    s = sin(Δφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(Δλ / 2) ** 2
    return 2 * R * atan2(sqrt(s), sqrt(1 - s))


def extract(route):
    """Extract turn points from GraphHopper route"""
    global ACTIVE_TURNS
    ACTIVE_TURNS.clear()

    if not route or "paths" not in route:
        print("[TURNS] No route or paths found")
        return

    try:
        path = route["paths"][0]
        instructions = path.get("instructions", [])
        points = path.get("points", {}).get("coordinates", [])

        print(f"[TURNS] Found {len(instructions)} instructions")
        print(f"[TURNS] Found {len(points)} coordinate points")

        # For each instruction (except the last "arrive" one)
        for i, instr in enumerate(instructions):
            if i >= len(instructions) - 1:
                continue  # Skip the last "arrive" instruction

            interval = instr.get("interval", [])
            if len(interval) >= 2:
                start_idx, end_idx = interval[0], interval[1]

                # Get the coordinate at the end of this instruction segment
                if end_idx < len(points):
                    # GraphHopper coordinates are [lon, lat]
                    lon, lat = points[end_idx]

                    turn_info = {
                        "lat": lat,
                        "lng": lon,
                        "text": instr.get("text", ""),
                        "instruction": instr.get("text", ""),
                        "distance": instr.get("distance", 0),
                        "street_name": instr.get("street_name", ""),
                        "sign": instr.get("sign", 0),
                        "interval": interval,
                    }

                    ACTIVE_TURNS.append(turn_info)

                    # print(f"[TURNS] Added turn {i}: {instr.get('text', '')}")
                    # print(f"[TURNS]   Coordinates: ({lat:.6f}, {lon:.6f})")
                    # print(f"[TURNS]   Distance: {instr.get('distance', 0)}m")
                    # print(f"[TURNS]   Street: {instr.get('street_name', 'N/A')}")
                else:
                    print(
                        f"[TURNS] Warning: end_idx {end_idx} out of bounds for points list"
                    )

        print(f"[TURNS] Total turns extracted: {len(ACTIVE_TURNS)}")

        # Print all turns for debugging
        for i, turn in enumerate(ACTIVE_TURNS):
            print(
                f"[TURNS] Turn {i}: {turn['text']} at ({turn['lat']:.6f}, {turn['lng']:.6f})"
            )

    except Exception as e:
        print(f"[TURNS] Error extracting turns: {e}")
        import traceback

        traceback.print_exc()
