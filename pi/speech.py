# speech.py
import subprocess
import random
import os
import time

SPEAKING_SPEED = 140  # Default: 150 WPM
SPEAKING_VOICE = "f5"  # Default: female voice (f5)


def set_speaking_speed(speed_wpm):
    global SPEAKING_SPEED
    SPEAKING_SPEED = max(80, min(300, speed_wpm))
    print(f"[SPEECH] Speaking speed set to {SPEAKING_SPEED} WPM")


def set_speaking_voice(voice_code):
    global SPEAKING_VOICE
    valid_voices = [
        "m1",
        "m2",
        "m3",
        "m4",
        "m5",
        "m6",
        "m7",
        "f1",
        "f2",
        "f3",
        "f4",
        "f5",
    ]

    if voice_code.lower() in valid_voices:
        SPEAKING_VOICE = voice_code.lower()
        print(f"[SPEECH] Voice set to {SPEAKING_VOICE}")
    else:
        print(f"[SPEECH] Invalid voice code. Using default: {SPEAKING_VOICE}")


def get_speaking_speed():
    return SPEAKING_SPEED


def get_speaking_voice():
    return SPEAKING_VOICE


def speak(text, speed_override=None, voice_override=None):
    speed = speed_override if speed_override is not None else SPEAKING_SPEED
    voice = voice_override if voice_override is not None else SPEAKING_VOICE

    instruction_map = {
        "continue": "Continue straight",
        "turn left": "Turn left",
        "turn right": "Turn right",
        "sharp left": "Sharp left",
        "sharp right": "Sharp right",
        "slight left": "Slight left",
        "slight right": "Slight right",
        "merge left": "Merge left",
        "merge right": "Merge right",
        "use roundabout": "Enter roundabout",
        "keep left": "Keep left",
        "keep right": "Keep right",
        "uturn": "Make a U-turn",
        "finish": "You have arrived at your destination",
        "depart": "Start walking",
        "arrive": "You have arrived",
    }

    # Format the instruction based on distance if available
    if isinstance(text, dict):
        # This is a GraphHopper turn instruction
        instruction_type = text.get("instruction", "").lower()
        distance = text.get("distance", 0)
        street_name = text.get("street_name", "")

        # Convert meters to appropriate units with speaking-friendly format
        if distance > 1000:
            distance_str = f"{distance/1000:.1f} kilometers"
        elif distance > 100:
            distance_str = f"{int(round(distance/100)*100)} meters"
        elif distance > 10:
            distance_str = f"{int(round(distance/10)*10)} meters"
        else:
            distance_str = f"{int(distance)} meters"

        # Get base instruction
        base_instruction = instruction_map.get(instruction_type, instruction_type)

        # Build the spoken phrase
        if instruction_type == "depart":
            spoken_text = f"{base_instruction}. Walk {distance_str}"
        elif instruction_type == "finish":
            spoken_text = f"{base_instruction}"
        else:
            # Adjust speed based on urgency
            if distance <= 50:  # Close turns should be spoken faster
                adjusted_speed = min(200, speed + 50)
            elif distance <= 100:
                adjusted_speed = speed
            else:  # Far turns can be spoken slower
                adjusted_speed = max(100, speed - 20)

            # Set speed for this specific instruction
            speed = adjusted_speed

            if street_name and street_name != "-":
                spoken_text = (
                    f"In {distance_str}, {base_instruction} onto {street_name}"
                )
            else:
                spoken_text = f"In {distance_str}, {base_instruction}"

    elif isinstance(text, str):
        # This is already a string instruction
        spoken_text = text
        # Adjust speed for urgent messages
        if "turn" in spoken_text.lower() and "in a few steps" in spoken_text.lower():
            speed = min(200, speed + 50)  # Speed up urgent turns
        elif "arrived" in spoken_text.lower():
            speed = 140  # Slightly slower for arrival announcements
    else:
        spoken_text = str(text)

    # Remove any special characters that might confuse the TTS
    spoken_text = spoken_text.replace("_", " ").replace("-", " to ")

    print(f"[SPEAK] {spoken_text} (voice: {voice}, speed: {speed} WPM)")

    # Use espeak for text-to-speech with voice and speed control
    try:
        # First check if espeak is available
        result = subprocess.run(["which", "espeak"], capture_output=True, text=True)
        if result.returncode != 0:
            print("[TTS] espeak not found. Installing...")
            os.system("sudo apt-get update && sudo apt-get install -y espeak")

        # Use espeak with specified voice and speed
        subprocess.run(
            ["espeak", "-v", voice, "-s", str(speed), spoken_text],
            check=False,  # Don't raise exception if espeak fails
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[TTS Error] {e}")
        # Fallback: try without voice parameter
        try:
            subprocess.run(
                ["espeak", "-s", str(speed), spoken_text],
                check=False,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
        except:
            # Final fallback: just print the text
            print(spoken_text)


# Helper function to process GraphHopper route for spoken instructions
def process_route_for_speech(route_data):
    """Extract and format route instructions for speech synthesis"""
    if not route_data or "paths" not in route_data:
        return []

    try:
        path = route_data["paths"][0]
        instructions = path.get("instructions", [])

        spoken_instructions = []
        for instr in instructions:
            # Extract relevant information
            instruction_data = {
                "instruction": instr.get("text", ""),
                "distance": instr.get("distance", 0),
                "time": instr.get("time", 0),
                "street_name": instr.get("street_name", ""),
            }

            # Get sign if available (for turn directions)
            if "sign" in instr:
                instruction_data["sign"] = instr["sign"]

            # Get interval if available (for coordinates)
            if "interval" in instr:
                instruction_data["interval"] = instr["interval"]

            spoken_instructions.append(instruction_data)

        return spoken_instructions

    except Exception as e:
        print(f"[Route processing error] {e}")
        return []


# Additional function for announcing proximity to turn
def announce_upcoming_turn(distance_to_turn, turn_instruction):
    """Announce an upcoming turn with distance information"""
    if distance_to_turn <= 20:
        distance_text = "in a few steps"
        speed = 180  # Faster for close turns
    elif distance_to_turn <= 50:
        distance_text = "in about 50 meters"
        speed = 160
    elif distance_to_turn <= 100:
        distance_text = "in about 100 meters"
        speed = 150
    else:
        # Only announce major distances
        if distance_to_turn <= 200:
            distance_text = "in about 200 meters"
            speed = 140
        else:
            return  # Don't announce too far in advance

    if isinstance(turn_instruction, dict):
        instruction = turn_instruction.get("instruction", "").lower()
        street_name = turn_instruction.get("street_name", "")

        if instruction == "turn left":
            text = f"{distance_text}, turn left"
        elif instruction == "turn right":
            text = f"{distance_text}, turn right"
        elif instruction == "continue":
            text = f"{distance_text}, continue straight"
        else:
            text = f"{distance_text}, {instruction}"

        if street_name and street_name != "-":
            text += f" onto {street_name}"
    else:
        text = f"{distance_text}, {turn_instruction}"

    speak(text, speed_override=speed)


def announce_arrival():
    arrival_phrases = [
        "You have arrived, at your destination",
        "Destination, reached",
        "You have, arrived",
        "This is your, destination",
    ]

    phrase = random.choice(arrival_phrases)
    speak(phrase, speed_override=130)


def announce_route_start(distance_total, time_total):
    """Announce route start with summary information"""
    if distance_total > 1000:
        distance_text = f"{distance_total/1000:.1f} kilometers"
    else:
        distance_text = f"{int(distance_total)} meters"

    if time_total > 60:
        minutes = time_total // 60
        time_text = f"{minutes} minutes"
        if time_total % 60 >= 30:
            time_text += " and a half"
    else:
        time_text = "less than a minute"

    speak(
        f"Route calculated. Walk {distance_text} in approximately, {time_text}",
        speed_override=140,
    )


def list_available_voices():
    try:
        result = subprocess.run(["espeak", "--voices"], capture_output=True, text=True)
        print("Available voices:")
        print(result.stdout)
    except Exception as e:
        print(f"[VOICE] Cannot list voices: {e}")


def test_voices():
    test_phrases = [
        "Turning left in 50 meters",
        "Continue straight for 100 meters",
        "You have arrived at your destination",
    ]

    female_voices = ["f1", "f2", "f3", "f4", "f5"]

    print("\n=== Testing Female Voices ===")
    for voice in female_voices:
        print(f"\nTesting voice: {voice}")
        set_speaking_voice(voice)
        for phrase in test_phrases:
            speak(phrase, speed_override=150)
            time.sleep(1)
