ACTIVE_TURNS = []


def extract(route):
    print("[Turns] Extracting turns from route")
    global ACTIVE_TURNS

    ACTIVE_TURNS = []

    instructions = route["paths"][0]["instructions"]
    coords = route["paths"][0]["points"]["coordinates"]

    print(instructions)

    for inst in instructions:
        start_idx, end_idx = inst["interval"]

        if start_idx >= len(coords) or len(coords[start_idx]) < 2:
            continue

    lon, lat = coords[start_idx]
    ACTIVE_TURNS.append({"text": inst["text"], "lat": lat, "lng": lon})

    return ACTIVE_TURNS
