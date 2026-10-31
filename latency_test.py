"""End-to-end latency test: how far the tracker's result trails reality.

Point the phone camera at a screen showing a live clock with milliseconds in UTC
(e.g. https://time.is/UTC). Keep your hand in view too, so the full tracking path runs.
Every second, one processed frame is saved to probes/latency_N.jpg with the BOARD's
UTC time (taken right after tracking) stamped on it.

    latency = stamped board time - clock time visible in the photo

Before running, check the board clock is synced: `timedatectl` -> "System clock synchronized: yes".
"""
import os
import time
from datetime import datetime, timezone

import cv2

from camera import Camera
from hand import HandTracker

SHOTS = 5
os.makedirs("probes", exist_ok=True)

cam = Camera()
tracker = HandTracker()
saved, next_save = 0, time.time() + 2          # 2 s warm-up
try:
    while saved < SHOTS:
        frame, _ = cam.read()
        if frame is None:
            time.sleep(0.002)
            continue
        res = tracker.process(frame)               # include tracking time in the measurement
        now = time.time()
        if now < next_save:
            continue
        stamp = datetime.fromtimestamp(now, timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        img = frame.copy()                         # never draw on the camera's frame
        text = f"board {stamp} UTC" + ("" if res else "  (no hand)")
        cv2.putText(img, text, (10, 465), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5)
        cv2.putText(img, text, (10, 465), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        saved += 1
        name = f"probes/latency_{saved}.jpg"
        cv2.imwrite(name, img)
        print(f"saved {name}: board time {stamp} UTC")
        next_save = now + 1
except KeyboardInterrupt:
    pass
finally:
    cam.stop()