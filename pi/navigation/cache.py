# navigation/cache.py

ROUTES = {}
ACTIVE_ROUTE = None


def get(dest):
    return ROUTES.get(tuple(dest))


def store(dest, route):
    ROUTES[tuple(dest)] = route


def set_active(route):
    global ACTIVE_ROUTE
    ACTIVE_ROUTE = route


def active():
    return ACTIVE_ROUTE
