from math import radians, sin, cos, asin, sqrt

INDEX = 0


def reset():
    global INDEX
    INDEX = 0


def haversine(a, b):
    lat1, lon1 = a
    lat2, lon2 = b

    R = 6371000

    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)

    h = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )

    return 2 * R * asin(sqrt(h))


def update(position, turns, speak):
    global INDEX

    if not turns or INDEX >= len(turns):
        return

    wp = turns[INDEX]

    d = haversine(position, (wp["lat"], wp["lng"]))

    if d < 5:
        speak(wp["text"])
        INDEX += 1
