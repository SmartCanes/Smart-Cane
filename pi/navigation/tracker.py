from math import atan2, radians, sin, cos, sqrt
from speech import announce_upcoming_turn, speak

INDEX = 0


def reset():
    global INDEX
    INDEX = 0


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


def update(position, turns):
    global INDEX

    if not turns or INDEX >= len(turns):
        return

    wp = turns[INDEX]
    d = haversine(position, (wp["lat"], wp["lng"]))

    if d <= 100 and d > 20:
        announce_upcoming_turn(d, wp.get("instruction", wp.get("text", "")))

        print(f"[Tracker] Approaching turn in {int(d)} meters: {wp.get('text', '')}")

    if d < 5:
        speak(wp.get("instruction", wp.get("text", "")))
        INDEX += 1
