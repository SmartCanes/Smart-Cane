import math

def bearing(a, b):
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)

    dlon = lon2 - lon1

    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)

    return (math.degrees(math.atan2(y, x)) + 360) % 360


def obstacle_on_route(
    current_pos,
    next_waypoint,
    obstacle_side,   # "left" | "right" | "front"
    threshold=25
):
    route_heading = bearing(current_pos, next_waypoint)

    if obstacle_side == "front":
        return True

    if obstacle_side == "left":
        return route_heading > 270 or route_heading < 180

    if obstacle_side == "right":
        return route_heading < 90 or route_heading > 180

    return False
