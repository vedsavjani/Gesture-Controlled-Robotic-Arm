"""Live loop: camera -> hand tracker -> print. Stop with Ctrl+C."""
import time

from camera import Camera
from hand import HandTracker

cam = Camera()
tracker = HandTracker()
last = time.time()
frames = found = 0
try:
    while True:
        frame, age = cam.read()
        if frame is None:
            time.sleep(0.002)
            continue
        res = tracker.process(frame)
        frames += 1
        found += res is not None
        now = time.time()
        if now - last >= 1.0:
            tip = f" | index tip {res[0][8,0]:.0f},{res[0][8,1]:.0f}" if res is not None else ""
            print(f"{frames / (now - last):5.1f} FPS | hand in {found}/{frames} frames{tip}")
            frames = found = 0
            last = now
except KeyboardInterrupt:
    pass
finally:
    cam.stop()
