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


def main():
    os.makedirs("probes", exist_ok=True)
    cam = Camera()
    tracker = HandTracker()
    saved, next_save = 0, time.monotonic() + 2          # 2 s warm-up
    try:
        while saved < SHOTS:
            frame, _ = cam.read(timeout=0.05)
            if frame is None:
                continue
            res = tracker.process(frame)                # include tracking time in the measurement
            mono_now = time.monotonic()
            if mono_now < next_save:
                continue
            stamp = datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3]
            img = frame.copy()                          # never draw on the camera's frame
            text = f"board {stamp} UTC" + ("" if res else "  (no hand)")
            y = max(25, img.shape[0] - 15)
            cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 5)
            cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            saved += 1
            name = f"probes/latency_{saved}.jpg"
            cv2.imwrite(name, img)
            print(f"saved {name}: board time {stamp} UTC")
            next_save = mono_now + 1
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()


if __name__ == "__main__":
    main()
