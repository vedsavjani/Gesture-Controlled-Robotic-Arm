"""
Experiment 3 (baseline): MediaPipe's own hand tracker on the UNO Q, live from the phone stream.
Measures how many frames per second the board can PROCESS with MediaPipe.
Result on the board: ~5.8 FPS tracking, ~4.5 FPS searching (uses ~1.2 of 4 cores).

Needs the MediaPipe venv (requirements-mediapipe.txt) and models/hand_landmarker.task.
Run from the repo root:  python experiments/hand_test.py http://<PHONE_IP>:8080/video
"""
import sys
import time
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "vision"))   # to find camera.py
from camera import LatestFrameReader

URL = sys.argv[1] if len(sys.argv) > 1 else "http://10.138.189.35:8080/video"
PROC_SIZE = (320, 240)   # shrink before MediaPipe; it downsizes internally anyway
TEST_SECONDS = 15

# Load the model (palm detector + landmark network) in VIDEO mode,
# so it tracks the hand between frames instead of re-detecting every frame.
options = vision.HandLandmarkerOptions(
    base_options=mp_python.BaseOptions(model_asset_path="models/hand_landmarker.task"),
    running_mode=vision.RunningMode.VIDEO,
    num_hands=1,             # one hand = less work
)
detector = vision.HandLandmarker.create_from_options(options)

cam = LatestFrameReader(URL)
time.sleep(1)

start = time.time()
frames, infer_total = 0, 0.0
report_t = time.time()
all_frames = 0

while time.time() - start < TEST_SECONDS:
    frame, _ = cam.read()
    if frame is None:
        time.sleep(0.01)
        continue

    small = cv2.resize(frame, PROC_SIZE)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)   # OpenCV is BGR, MediaPipe wants RGB
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    t = time.time()
    timestamp_ms = int((t - start) * 1000)          # VIDEO mode needs increasing timestamps
    result = detector.detect_for_video(image, timestamp_ms)
    infer_total += time.time() - t
    frames += 1
    all_frames += 1

    if time.time() - report_t >= 1.0:
        fps = frames / (time.time() - report_t)
        ms = 1000 * infer_total / frames
        if result.hand_landmarks:
            tip = result.hand_landmarks[0][8]       # landmark 8 = index fingertip
            hand = f"index tip x={tip.x:.2f} y={tip.y:.2f}"
        else:
            hand = "no hand"
        print(f"{fps:5.1f} FPS | MediaPipe {ms:5.1f} ms/frame | {hand}")
        frames, infer_total, report_t = 0, 0.0, time.time()

print(f"Average processing FPS: {all_frames / (time.time() - start):.1f}")
cam.stop()