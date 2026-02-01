import cv2
import time
import threading
import subprocess
import numpy as np
import ncnn

# ================= speech =================


def speak(text):
    def _speak():
        subprocess.run(["espeak", "-s", "120", text])

    threading.Thread(target=_speak, daemon=True).start()


# ================= load ncnn =================

net = ncnn.Net()
net.load_param("yolov8n.param")
net.load_model("yolov8n.bin")

TARGET_SIZE = 640
CENTER_THRESHOLD = 80
COOLDOWN = 5
last_spoken = 0

labels = ["person", "bicycle", "car", "motorcycle"]  # extend if needed

cap = cv2.VideoCapture(0)

while True:

    ret, frame = cap.read()
    if not ret:
        break

    h, w, _ = frame.shape

    mat = ncnn.Mat.from_pixels_resize(
        frame,
        ncnn.Mat.PixelType.PIXEL_BGR,
        w,
        h,
        TARGET_SIZE,
        TARGET_SIZE,
    )

    mat.substract_mean_normalize([], [1 / 255, 1 / 255, 1 / 255])

    ex = net.create_extractor()
    ex.input("images", mat)

    _, out = ex.extract("output0")

    detected = None
    cx_frame = w // 2

    for i in range(out.h):

        row = out.row(i)
        conf = row[4]

        if conf < 0.5:
            continue

        cls = int(row[5])
        x1 = int(row[0] * w)
        y1 = int(row[1] * h)
        x2 = int(row[2] * w)
        y2 = int(row[3] * h)

        cx = (x1 + x2) // 2

        if abs(cx - cx_frame) < CENTER_THRESHOLD:
            direction = "ahead"
        elif cx < cx_frame:
            direction = "on left"
        else:
            direction = "on right"

        detected = f"{labels[cls]} {direction}"
        break

    now = time.time()

    if detected and now - last_spoken > COOLDOWN:
        speak(detected)
        print(detected)
        last_spoken = now

cap.release()
