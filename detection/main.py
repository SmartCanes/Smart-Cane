from ultralytics import YOLO
import cv2
import pyttsx3
import time

engine = pyttsx3.init()
engine.setProperty("rate", 140)
engine.setProperty("volume", 1.5)

model = YOLO("yolov8n.pt")

# Open camera
cap = cv2.VideoCapture(0)

# Track last spoken description & time
last_spoken = None
last_spoken_time = 0
COOLDOWN = 5  # seconds

# Threshold for "ahead" zone
CENTER_THRESHOLD = 80

while True:
    ret, frame = cap.read()
    if not ret:
        break

    results = model(frame)
    annotated_frame = results[0].plot()

    h, w, _ = frame.shape
    frame_center_x = w // 2

    detected_obj = None
    direction = None

    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        label = results[0].names[cls_id]

        # Bounding box
        x1, y1, x2, y2 = map(int, box.xyxy[0])
        obj_center_x = (x1 + x2) // 2

        # Decide direction
        if abs(obj_center_x - frame_center_x) <= CENTER_THRESHOLD:
            direction = "ahead"
        elif obj_center_x < frame_center_x - CENTER_THRESHOLD:
            direction = "on left"
        else:
            direction = "on right"

        detected_obj = f"{label} {direction}"
        break  # take only the first detected object

    # Speak only if cooldown has passed
    current_time = time.time()
    if detected_obj and (current_time - last_spoken_time >= COOLDOWN):
        engine.say(detected_obj)
        engine.runAndWait()
        last_spoken = detected_obj
        last_spoken_time = current_time

    # Show video (keeps running smoothly even while waiting)
    cv2.imshow("YOLOv8 + Voice", annotated_frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
