# tracker.py
from math import atan2, radians, sin, cos, sqrt
from speech import (
    announce_upcoming_turn,
    speak,
    announce_obstacle,
    give_safety_reminder,
)
import time

INDEX = 0
LAST_SAFETY_REMINDER = 0
SAFETY_REMINDER_INTERVAL = 300  # 5 minutes


def reset():
    global INDEX, LAST_SAFETY_REMINDER
    INDEX = 0
    LAST_SAFETY_REMINDER = time.time()
    print(f"[TRACKER] Reset for blind user navigation")


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


def update(position, turns, obstacles=None):
    """Update position for blind user navigation"""
    global INDEX, LAST_SAFETY_REMINDER

    # Give periodic safety reminders
    current_time = time.time()
    if current_time - LAST_SAFETY_REMINDER > SAFETY_REMINDER_INTERVAL:
        give_safety_reminder()
        LAST_SAFETY_REMINDER = current_time

    # Check for obstacles if provided
    if obstacles:
        for obstacle in obstacles:
            dist = haversine(position, (obstacle["lat"], obstacle["lng"]))
            if dist < 10:
                announce_obstacle(
                    dist,
                    obstacle.get("direction", "center"),
                    obstacle.get("type", "obstacle"),
                )

    # Handle turns
    if not turns or INDEX >= len(turns):
        return

    wp = turns[INDEX]
    d = haversine(position, (wp["lat"], wp["lng"]))

    # Announce upcoming turn with blind-user specific guidance
    # if d <= 100 and d > 20:
    #     street_name = wp.get("street_name", "")
    #     announce_upcoming_turn_for_blind(
    #         d, wp.get("instruction", wp.get("text", "")), street_name
    #     )

    if d < 5:
        # Speak the turn instruction
        instruction = wp.get("instruction", wp.get("text", ""))
        street_name = wp.get("street_name", "")

        # Format final turn instruction
        # if street_name and street_name != "-":
        #     final_text = f"Now, {instruction}"
        # else:
        final_text = f"Now, {instruction}."

        # Add cane guidance for sharp turns
        if "sharp" in instruction.lower():
            final_text += " Use wide cane sweep."
        elif "slight" in instruction.lower():
            final_text += " Gentle cane adjustment."

        speak(final_text, urgent=True)

        INDEX += 1
        print(
            f"[NAV] Completed turn {INDEX-1}. Next turn in {len(turns) - INDEX} turns"
        )
