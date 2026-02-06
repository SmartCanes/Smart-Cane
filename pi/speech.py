import subprocess
import random
import os
import time
import threading
import queue
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Callable, Any

# ========== GLOBAL SETTINGS ==========
SPEAKING_SPEED = 130  # Slower for comprehension
SPEAKING_VOICE = "f5"  # Clear female voice
SPEAKING_VOLUME = 100  # Max volume for clarity

# ========== ENUMS & DATA CLASSES ==========
class SpeechPriority(Enum):
    """Priority levels for speech messages"""
    CRITICAL = 0      # Obstacles, immediate turns, safety warnings
    HIGH = 1          # Upcoming turns, route changes
    NORMAL = 2        # Route info, confirmations
    LOW = 3           # Status updates, reminders
    BACKGROUND = 4    # Non-essential info

class SpeechCategory(Enum):
    """Categories for speech messages"""
    OBSTACLE = "obstacle"
    TURN_INSTRUCTION = "turn"
    ARRIVAL = "arrival"
    ROUTE_INFO = "route"
    SAFETY = "safety"
    STATUS = "status"
    CONFIRMATION = "confirmation"

@dataclass
class SpeechItem:
    """Data class for speech queue items"""
    text: str
    priority: SpeechPriority
    category: SpeechCategory
    urgent: bool = False
    speed_override: Optional[int] = None
    voice_override: Optional[str] = None
    callback: Optional[Callable] = None
    callback_args: tuple = ()
    metadata: dict = None
    
    def __lt__(self, other):
        """For priority queue ordering (lower priority number = higher priority)"""
        return self.priority.value < other.priority.value

# ========== SPEECH QUEUE CLASS ==========
class SpeechQueue:
    """Thread-safe priority queue for managing TTS output"""

    def __init__(self):
        self.queue = queue.PriorityQueue()
        self.current_item = None
        self.is_speaking = False
        self.is_paused = False
        self.interrupt_requested = False
        self.lock = threading.Lock()
        self.worker_thread = None
        self.start_worker()

        # Statistics
        self.stats = {
            "total_spoken": 0,
            "interruptions": 0,
            "by_category": {cat.value: 0 for cat in SpeechCategory},
            "by_priority": {prio.value: 0 for prio in SpeechPriority}
        }

    def start_worker(self):
        """Start the background worker thread"""
        if self.worker_thread and self.worker_thread.is_alive():
            return

        self.worker_thread = threading.Thread(
            target=self._queue_worker,
            daemon=True,
            name="SpeechQueueWorker"
        )
        self.worker_thread.start()
        print("[SPEECH] Speech queue worker started")

    def _queue_worker(self):
        """Background worker that processes speech items"""
        while True:
            try:
                # Get next item (blocking)
                priority, speech_item = self.queue.get()

                # Check if we should skip this item
                if self.interrupt_requested and speech_item.priority != SpeechPriority.CRITICAL:
                    print(f"[SPEECH] Skipping non-critical item during interruption: {speech_item.text[:50]}...")
                    self.queue.task_done()
                    continue

                # Clear interruption flag if we're processing again
                if self.interrupt_requested and speech_item.priority == SpeechPriority.CRITICAL:
                    self.interrupt_requested = False

                # Speak the item (blocking)
                with self.lock:
                    self.is_speaking = True
                    self.current_item = speech_item

                self._speak_item(speech_item)

                # Update statistics
                self._update_stats(speech_item)

                # Execute callback if provided
                if speech_item.callback:
                    try:
                        speech_item.callback(*speech_item.callback_args)
                    except Exception as e:
                        print(f"[SPEECH] Callback error: {e}")

                with self.lock:
                    self.is_speaking = False
                    self.current_item = None

                self.queue.task_done()

            except Exception as e:
                print(f"[SPEECH] Worker error: {e}")
                time.sleep(0.1)

    def _speak_item(self, item: SpeechItem):
        """Internal method to speak a single item"""
        # Skip if paused (unless critical)
        if self.is_paused and item.priority != SpeechPriority.CRITICAL:
            print(f"[SPEECH] Paused, skipping: {item.text[:50]}...")
            return

        # Use espeak with blind-user optimizations
        try:
            # Prepare parameters
            speed = item.speed_override if item.speed_override is not None else SPEAKING_SPEED
            voice = item.voice_override if item.voice_override is not None else SPEAKING_VOICE

            # Increase speed for urgent items
            if item.urgent:
                speed = min(180, speed + 30)
                voice = "f5"

            # Clean text
            text = item.text.replace("_", " ").replace("-", " to ")

            print(f"[SPEAK:{item.priority.name}] {text[:80]}...")

            # Calculate approximate duration for timing
            words = len(text.split())
            approx_duration = words / (speed/60)  # seconds

            # Add pre-speech pause for non-critical items
            if item.priority.value > SpeechPriority.CRITICAL.value:
                time.sleep(0.05)

            # Speak using espeak
            subprocess.run(
                ["espeak", "-v", voice, "-s", str(speed), "-a", "200", text],
                check=True,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )

            # Add post-speech pause based on importance
            if item.urgent or item.priority == SpeechPriority.CRITICAL:
                time.sleep(0.3)  # Short pause for critical items
            elif item.priority == SpeechPriority.HIGH:
                time.sleep(0.2)
            elif item.priority == SpeechPriority.NORMAL:
                time.sleep(0.1)

            return approx_duration

        except subprocess.CalledProcessError as e:
            print(f"[SPEECH] TTS Error: {e}")
            print(f"[SPEECH] Failed text: {item.text}")
            return 0
        except Exception as e:
            print(f"[SPEECH] Unexpected error: {e}")
            return 0

    def _update_stats(self, item: SpeechItem):
        """Update statistics"""
        self.stats["total_spoken"] += 1
        self.stats["by_category"][item.category.value] += 1
        self.stats["by_priority"][item.priority.value] += 1

    # ========== PUBLIC API ==========

    def add_speech(self, 
                   text: str, 
                   priority: SpeechPriority = SpeechPriority.NORMAL,
                   category: SpeechCategory = SpeechCategory.STATUS,
                   urgent: bool = False,
                   speed_override: Optional[int] = None,
                   voice_override: Optional[str] = None,
                   callback: Optional[Callable] = None,
                   callback_args: tuple = (),
                   metadata: dict = None) -> int:
        """Add a speech item to the queue"""
        item = SpeechItem(
            text=text,
            priority=priority,
            category=category,
            urgent=urgent,
            speed_override=speed_override,
            voice_override=voice_override,
            callback=callback,
            callback_args=callback_args,
            metadata=metadata or {}
        )

        # Put in queue with priority as first element for PriorityQueue
        self.queue.put((item.priority.value, item))

        queue_size = self.queue.qsize()
        if queue_size > 5:
            print(f"[SPEECH] Queue size: {queue_size}")

        return queue_size

    def interrupt(self, clear_queue: bool = False):
        """Interrupt current speech and optionally clear queue"""
        with self.lock:
            self.interrupt_requested = True
            self.stats["interruptions"] += 1

            if clear_queue:
                # Clear all non-critical items
                temp_queue = queue.PriorityQueue()
                while not self.queue.empty():
                    priority, item = self.queue.get()
                    if item.priority == SpeechPriority.CRITICAL:
                        temp_queue.put((priority, item))
                self.queue = temp_queue
                print("[SPEECH] Queue cleared (critical items kept)")

    def pause(self):
        """Pause speech output (except critical)"""
        self.is_paused = True
        print("[SPEECH] Speech paused")

    def resume(self):
        """Resume speech output"""
        self.is_paused = False
        print("[SPEECH] Speech resumed")

    def clear(self, keep_critical: bool = True):
        with self.queue.mutex:
            if keep_critical:
                new_items = [
                    item for item in self.queue.queue
                    if item[1].priority == SpeechPriority.CRITICAL
                ]
                self.queue.queue.clear()
                self.queue.queue.extend(new_items)
            else:
                self.queue.queue.clear()
    
            self.queue.unfinished_tasks = 0

    print("[SPEECH] Queue cleared")

    def wait_until_empty(self, timeout: Optional[float] = None) -> bool:
        """Wait until queue is empty"""
        try:
            self.queue.join()
            return True
        except Exception as e:
            print(f"[SPEECH] Wait error: {e}")
            return False

    def get_status(self) -> dict:
        """Get current queue status"""
        with self.lock:
            return {
                "queue_size": self.queue.qsize(),
                "is_speaking": self.is_speaking,
                "is_paused": self.is_paused,
                "current_item": self.current_item.text[:50] + "..." if self.current_item else None,
                "stats": self.stats.copy()
            }

    def get_queue_size(self) -> int:
        """Get current queue size"""
        return self.queue.qsize()

# ========== GLOBAL SPEECH QUEUE INSTANCE ==========
speech_queue = SpeechQueue()

# ========== CONVENIENCE FUNCTIONS ==========
def speak(text, 
          speed_override=None, 
          voice_override=None, 
          urgent=False,
          wait=False,
          category=SpeechCategory.STATUS):
    
    if urgent:
        priority = SpeechPriority.CRITICAL
    elif category in [SpeechCategory.OBSTACLE, SpeechCategory.TURN_INSTRUCTION]:
        priority = SpeechPriority.HIGH
    elif category in [SpeechCategory.ARRIVAL, SpeechCategory.SAFETY]:
        priority = SpeechPriority.NORMAL
    else:
        priority = SpeechPriority.LOW
    
    # Add to queue
    speech_queue.add_speech(
        text=text,
        priority=priority,
        category=category,
        urgent=urgent,
        speed_override=speed_override,
        voice_override=voice_override
    )
    
    # Wait if requested
    if wait:
        speech_queue.wait_until_empty()

# ========== SPECIALIZED FUNCTIONS USING QUEUE ==========
def announce_obstacle(distance, direction, obstacle_type="object"):
    if distance <= 2:
        urgency = "Immediately"
        speed = 180
    elif distance <= 5:
        urgency = "Just ahead"
        speed = 170
    else:
        urgency = "Ahead"
        speed = 150
    
    direction_text = {
        "left": "on your left side",
        "right": "on your right side",
        "center": "directly ahead",
        "both": "on both sides"
    }.get(direction, "ahead")
    
    text = f"{urgency}, {obstacle_type} {direction_text}. Use caution."
    
    # Critical priority for obstacles
    speech_queue.add_speech(
        text=text,
        priority=SpeechPriority.CRITICAL,
        category=SpeechCategory.OBSTACLE,
        urgent=True,
        speed_override=speed
    )

def announce_upcoming_turn(distance_to_turn, turn_instruction, street_name=""):
    """Announce upcoming turn using speech queue"""
    if distance_to_turn <= 5:
        distance_text = "Immediately"
        speed = 180
        additional = " Prepare to turn now."
    elif distance_to_turn <= 15:
        distance_text = "In a few steps"
        speed = 170
        additional = " Get ready to turn."
    elif distance_to_turn <= 30:
        distance_text = "Very soon"
        speed = 160
        additional = " Approaching turn."
    elif distance_to_turn <= 50:
        distance_text = "In about 50 meters"
        speed = 150
        additional = ""
    else:
        return  # Don't announce distant turns
    
    # Get turn direction
    if isinstance(turn_instruction, dict):
        instruction = turn_instruction.get("instruction", "").lower()
    else:
        instruction = str(turn_instruction).lower()
    
    # Convert to natural language
    if "turn left" in instruction:
        turn_text = "turn left"
        hand_guidance = "Extend your left arm slightly."
    elif "turn right" in instruction:
        turn_text = "turn right"
        hand_guidance = "Extend your right arm slightly."
    elif "continue" in instruction or "straight" in instruction:
        turn_text = "continue straight"
        hand_guidance = "Keep cane centered."
    else:
        turn_text = instruction
        hand_guidance = ""
    
    # Build text
    if street_name and street_name != "-":
        text = f"{distance_text}, {turn_text} onto {street_name}. {additional}"
    else:
        text = f"{distance_text}, {turn_text}.{additional}"
    
    if hand_guidance and distance_to_turn <= 30:
        text += f" {hand_guidance}"
    
    # Add to queue with high priority
    speech_queue.add_speech(
        text=text,
        priority=SpeechPriority.HIGH,
        category=SpeechCategory.TURN_INSTRUCTION,
        urgent=(distance_to_turn <= 30),
        speed_override=speed
    )

def announce_arrival():
    arrival_phrases = [
        "You have arrived, at your, destination. Stop, walking.",
        "Destination reached. This is your stopping point.",
        "You have arrived. Please, stop, here.",
        "This is your destination. You may stop, now.",
    ]
    
    phrase = random.choice(arrival_phrases)
    speech_queue.add_speech(
        text=phrase,
        priority=SpeechPriority.CRITICAL,
        category=SpeechCategory.ARRIVAL,
        urgent=True,
        speed_override=120
    )


def announce_route_start(distance_total, time_total, num_turns):
    """Announce route start using speech queue"""
    # Convert distance
    if distance_total > 1000:
        distance_text = f"{distance_total/1000:.1f} kilometers"
    else:
        distance_text = f"{int(distance_total)} meters"
    
    # Convert time
    if time_total > 60:
        minutes = int(time_total // 60)
        seconds = int(time_total % 60)
        if seconds > 30:
            minutes += 1
        time_text = f"{minutes} minutes"
    else:
        time_text = "less than a minute"
    
    # Announce turn count
    if num_turns == 0:
        turn_text = "straight path with no turns"
    elif num_turns == 1:
        turn_text = "1 turn"
    else:
        turn_text = f"{num_turns} turns"
    
    text = f"Route calculated. {distance_text} total, approximately {time_text}. {turn_text}. Begin when ready."
    
    speech_queue.add_speech(
        text=text,
        priority=SpeechPriority.NORMAL,
        category=SpeechCategory.ROUTE_INFO,
        speed_override=120
    )

def give_safety_reminder():
    reminders = [
        "Remember to stay aware of your surroundings.",
        "Stay alert to your surroundings.",
        "Listen for traffic before crossing.",
        "Keep phone accessible for emergencies.",
    ]
    
    reminder = random.choice(reminders)
    
    speech_queue.add_speech(
        text=f"Safety reminder: {reminder}",
        priority=SpeechPriority.LOW,
        category=SpeechCategory.SAFETY,
        speed_override=140
    )

def announce_reroute(reason="route change"):
    """Announce rerouting using speech queue"""
    reasons = {
        "off_route": "You have strayed from the path.",
        "obstacle": "Route blocked ahead.",
        "user_request": "Rerouting as requested.",
        "traffic": "Heavy traffic detected.",
    }
    
    reason_text = reasons.get(reason, "Recalculating route.")
    text = f"{reason_text} Calculating new path. Please stand by."
    
    speech_queue.add_speech(
        text=text,
        priority=SpeechPriority.HIGH,
        category=SpeechCategory.ROUTE_INFO,
        urgent=True
    )

# ... [previous imports and SpeechQueue class remain the same] ...

# ========== ROUTE PROCESSING FUNCTIONS ==========
def process_route(route_data):
    """
    Process route data for blind users and extract key information
    Returns a dictionary with processed route info
    """
    if not route_data or "paths" not in route_data:
        print("[ROUTE] No valid route data provided")
        return {}
    
    try:
        path = route_data["paths"][0]
        instructions = path.get("instructions", [])
        
        # Count turns for announcement
        turn_count = 0
        for instr in instructions:
            text = instr.get("text", "").lower()
            if any(word in text for word in ["turn", "left", "right", "merge", "roundabout"]):
                if "continue" not in text and "straight" not in text:
                    turn_count += 1
        
        # Get total distance and time
        total_distance = path.get("distance", 0)
        total_time = path.get("time", 0) / 1000  # Convert ms to seconds
        
        # Extract street names and distances for turn-by-turn guidance
        turn_instructions = []
        for instr in instructions:
            turn_info = {
                "text": instr.get("text", ""),
                "distance": instr.get("distance", 0),
                "time": instr.get("time", 0),
                "street_name": instr.get("street_name", ""),
                "sign": instr.get("sign", 0)
            }
            turn_instructions.append(turn_info)
        
        # Check for accessibility features
        full_route_text = str(route_data).lower()
        
        return {
            "instructions": instructions,
            "turn_instructions": turn_instructions,
            "total_distance": total_distance,
            "total_time": total_time,
            "turn_count": turn_count,
            "has_crosswalks": "crosswalk" in full_route_text,
            "has_stairs": "stairs" in full_route_text or "steps" in full_route_text,
            "has_elevators": "elevator" in full_route_text,
            "has_ramps": "ramp" in full_route_text,
            "raw_data": route_data
        }
    
    except Exception as e:
        print(f"[ROUTE] Error processing route for blind users: {e}")
        return {}

def announce_route_details(route_info):
    """
    Announce route details using speech queue
    """
    if not route_info:
        speech_queue.add_speech(
            text="Unable to process route information.",
            priority=SpeechPriority.HIGH,
            category=SpeechCategory.ROUTE_INFO
        )
        return
    
    # Announce route start
    announce_route_start(
        route_info.get("total_distance", 0),
        route_info.get("total_time", 0),
        route_info.get("turn_count", 0)
    )
    
    # Add accessibility warnings
    accessibility_warnings = []
    if route_info.get("has_stairs"):
        accessibility_warnings.append("Warning: Route contains stairs.")
    if route_info.get("has_crosswalks"):
        accessibility_warnings.append("Route includes street crossings.")
    
    if accessibility_warnings:
        # Wait a moment after initial announcement
        def announce_accessibility():
            time.sleep(2)
            for warning in accessibility_warnings:
                speech_queue.add_speech(
                    text=warning,
                    priority=SpeechPriority.NORMAL,
                    category=SpeechCategory.SAFETY
                )
        
        threading.Thread(target=announce_accessibility, daemon=True).start()

def process_and_announce_route(route_data):
    """
    Complete route processing and announcement
    """
    # Process route
    route_info = process_route(route_data)
    
    if not route_info:
        speech_queue.add_speech(
            text="Failed to calculate route. Please try again.",
            priority=SpeechPriority.CRITICAL,
            category=SpeechCategory.ROUTE_INFO,
            urgent=True
        )
        return None
    
    # Announce route details
    announce_route_details(route_info)
    
    return route_info

def get_next_turn_instruction(route_info, current_distance=0):
    """
    Get the next turn instruction based on current distance traveled
    """
    if not route_info or "turn_instructions" not in route_info:
        return None
    
    instructions = route_info["turn_instructions"]
    if not instructions:
        return None
    
    # Find the next instruction that hasn't been passed yet
    cumulative_distance = 0
    
    for instr in instructions:
        cumulative_distance += instr.get("distance", 0)
        
        # If we haven't reached this instruction yet
        if cumulative_distance > current_distance:
            return {
                "instruction": instr.get("text", ""),
                "distance_to_turn": cumulative_distance - current_distance,
                "street_name": instr.get("street_name", ""),
                "cumulative_distance": cumulative_distance
            }
    
    # If we've passed all instructions
    return {"instruction": "arrive", "distance_to_turn": 0}

def announce_progress_update(route_info, distance_traveled):
    """
    Announce progress update (called periodically during navigation)
    """
    next_turn = get_next_turn_instruction(route_info, distance_traveled)
    
    if not next_turn:
        return
    
    distance_to_turn = next_turn.get("distance_to_turn", 0)
    instruction = next_turn.get("instruction", "")
    street_name = next_turn.get("street_name", "")
    
    # Announce if turn is coming up soon
    if distance_to_turn <= 100:  # Within 100 meters
        if "arrive" in instruction.lower():
            # We're approaching destination
            if distance_to_turn <= 30:
                announce_arrival()
            else:
                speech_queue.add_speech(
                    text=f"Destination in {int(distance_to_turn)} meters.",
                    priority=SpeechPriority.HIGH,
                    category=SpeechCategory.ROUTE_INFO
                )
        elif any(word in instruction.lower() for word in ["turn", "left", "right", "merge"]):
            # It's a turn instruction
            announce_upcoming_turn(distance_to_turn, instruction, street_name)

# ========== NAVIGATION CONTROL FUNCTIONS ==========
def start_navigation(route_data):
    print("[NAVIGATION] Starting navigation")
    
    # Clear any existing speech
    speech_queue.clear()
    
    # Process and announce route
    route_info = process_and_announce_route(route_data)
    
    # Add initial safety reminder
    time.sleep(1)
    give_safety_reminder()
    
    return route_info

def stop_navigation():
    print("[NAVIGATION] Stopping navigation")
    speech_queue.clear(keep_critical=False)
    speech_queue.add_speech(
    text="Navigation has been cancelled.",
    priority=SpeechPriority.CRITICAL,
    category=SpeechCategory.STATUS,
    urgent=True
)

def pause_navigation():
    """Pause navigation announcements"""
    print("[NAVIGATION] Pausing navigation")
    speech_queue.add_speech(
        text="Navigation paused.",
        priority=SpeechPriority.NORMAL,
        category=SpeechCategory.STATUS
    )
    speech_queue.pause()

def resume_navigation():
    """Resume navigation announcements"""
    print("[NAVIGATION] Resuming navigation")
    speech_queue.add_speech(
        text="Navigation resumed.",
        priority=SpeechPriority.NORMAL,
        category=SpeechCategory.STATUS
    )
    speech_queue.resume()

# ========== MAIN FUNCTION FOR TESTING ==========

# ========== UTILITY FUNCTIONS ==========
def set_speaking_speed(speed_wpm):
    """Set the speaking speed for blind users"""
    global SPEAKING_SPEED
    SPEAKING_SPEED = max(100, min(200, speed_wpm))
    print(f"[SPEECH] Speed set to {SPEAKING_SPEED} WPM for blind user")

def set_speaking_voice(voice_code):
    """Set the speaking voice"""
    global SPEAKING_VOICE
    clear_voices = ["f4", "f5", "en-us+f5", "en-gb+f5"]
    if voice_code.lower() in clear_voices:
        SPEAKING_VOICE = voice_code.lower()
    else:
        SPEAKING_VOICE = "f5"
    print(f"[SPEECH] Using voice {SPEAKING_VOICE}")

def emergency_stop():
    """Emergency stop all speech"""
    print("[SPEECH] EMERGENCY STOP - Clearing all speech")
    speech_queue.clear(keep_critical=False)
    speech_queue.interrupt()

def get_speech_status():
    return speech_queue.get_status()

    # Test the speech queue
    print("Testing Speech Queue System...")

    # Test different priorities
    speech_queue.add_speech(
        "Low priority test message.",
        priority=SpeechPriority.LOW,
        category=SpeechCategory.STATUS
    )

    speech_queue.add_speech(
        "Normal priority test message.",
        priority=SpeechPriority.NORMAL,
        category=SpeechCategory.STATUS
    )

    speech_queue.add_speech(
        "High priority test message - this should speak first!",
        priority=SpeechPriority.HIGH,
        category=SpeechCategory.STATUS
    )

    speech_queue.add_speech(
        "Critical obstacle warning!",
        priority=SpeechPriority.CRITICAL,
        category=SpeechCategory.OBSTACLE,
        urgent=True
    )

    # Wait for all speech to complete
    time.sleep(5)
    print("Test complete.")
    print(f"Queue status: {speech_queue.get_status()}")

if __name__ == "__main__":
    # Test the complete system
    print("Testing complete navigation system...")

    # Simulate a route
    test_route = {
        "paths": [
            {
                "distance": 1500,  # 1.5 km
                "time": 900000,  # 15 minutes in ms
                "instructions": [
                    {
                        "text": "Depart",
                        "distance": 0,
                        "street_name": "Start",
                        "sign": 0,
                    },
                    {
                        "text": "Turn left onto Main Street",
                        "distance": 200,
                        "street_name": "Main Street",
                        "sign": -1,
                    },
                    {
                        "text": "Continue straight",
                        "distance": 500,
                        "street_name": "Main Street",
                        "sign": 0,
                    },
                    {
                        "text": "Turn right onto Oak Avenue",
                        "distance": 300,
                        "street_name": "Oak Avenue",
                        "sign": 1,
                    },
                    {
                        "text": "Arrive at destination",
                        "distance": 500,
                        "street_name": "Destination",
                        "sign": 4,
                    },
                ],
            }
        ]
    }

    # Test route processing
    route_info = process_route(test_route)
    print(f"Route info: {route_info.keys()}")
    print(f"Total distance: {route_info.get('total_distance')}m")
    print(f"Turn count: {route_info.get('turn_count')}")

    # Test navigation
    nav_route_info = start_navigation(test_route)

    # Simulate progress
    time.sleep(3)
    print("\nSimulating progress...")

    # Test turn announcement at different distances
    announce_progress_update(nav_route_info, 180)  # 20m before turn
    time.sleep(2)

    announce_progress_update(nav_route_info, 480)  # After first turn, before second
    time.sleep(2)

    # Test obstacle announcement
    announce_obstacle(3, "center", "pedestrian")

    # Wait for everything to finish
    time.sleep(10)
    print("\nTest complete.")
    print(f"Final status: {get_speech_status()}")
