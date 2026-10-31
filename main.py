"""The full Linux-side program: camera -> hand tracker -> gesture -> controller -> 4 angles.

Prints 4 lines per second:
  FPS | stable gesture | moving joint + speed | base shoulder elbow gripper (deg)
send_to_mcu() is where the angles go to the STM32 sketch over the Bridge (to be filled in
with the sketch). Stop with Ctrl+C.
"""
import time

from camera import Camera
from controller import ArmController
from gestures import classify
from hand import HandTracker

SEND_HZ = 20                    # max updates per second to the microcontroller


def send_to_mcu(angles):
    """Send (base, shoulder, elbow, gripper) to the STM32 sketch over the Bridge. TODO with the sketch."""
    pass


cam = Camera()
tracker = HandTracker()
arm = ArmController()
last_print = last_send = time.time()
frames = 0
try:
    while True:
        frame, _ = cam.read()
        if frame is None:
            time.sleep(0.002)
            continue
        res = tracker.process(frame)
        if res is None:
            gesture, palm = "none", None
        else:
            gesture, _, m = classify(res[0])
            palm = m["palm_px"]
        now = time.time()
        angles = arm.update(gesture, palm, now)
        frames += 1

        if now - last_send >= 1.0 / SEND_HZ:
            send_to_mcu(angles)
            last_send = now

        if now - last_print >= 0.25:
            fps = frames / (now - last_print)
            moving = f"{arm.active} @ {arm.speed:4.1f} deg/s" if arm.active else ("home glide" if arm.speed else "-")
            b, s, e, g = angles
            print(f"{fps:5.1f} FPS | {arm._stable_prev:13s} | {moving:30s} | "
                  f"base {b:5.1f}  shoulder {s:5.1f}  elbow {e:5.1f}  gripper {g:5.1f}")
            frames, last_print = 0, now
except KeyboardInterrupt:
    pass
finally:
    cam.stop()