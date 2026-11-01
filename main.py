"""The full Linux-side program: camera -> hand tracker -> gesture -> controller -> 4 angles -> STM32.

Prints 4 lines per second:
  FPS | stable gesture | moving joint + speed | base shoulder elbow gripper (deg)
send_to_mcu() sends the angles to sketch/sketch.ino over the Bridge, ~20 times per second.
If the Bridge library can't be imported (e.g. on a laptop), the angles are only printed.
Stop with Ctrl+C.

CHANGES on Nov 1 (README task 2, the Bridge link; everything else in this file is unchanged):
  - send_to_mcu() was an empty `pass`. It now calls
        Bridge.call(config.MCU_METHOD, base, shoulder, elbow, gripper)
    with 4 integers, matching the contract at the top of sketch/sketch.ino.
  - The Bridge import is wrapped in try/except, so this file still runs on a laptop (it just prints).
  - A failed Bridge call prints an error (first one, then every 100th) and does NOT stop the vision loop.
  - SEND_HZ stays 20 and must keep sending even when the angles don't change: the sketch freezes the
    arm if nothing arrives for 0.5 s.

NOT VERIFIED YET: nobody has tested that `from arduino.app_utils import Bridge` works from the README's
uv venv, or that the call reaches the sketch. If main.py prints "Bridge not available here", the import
failed. In the Arduino examples I found, Python runs inside App Lab (App.run(user_loop=...)); if the
plain script can't reach the Bridge, this program may need to run that way. Test this first on the board.
"""
import time

import config
from camera import Camera
from controller import ArmController
from gestures import classify
from hand import HandTracker

try:
    from arduino.app_utils import Bridge       # Arduino's Linux<->STM32 link (UNO Q only)
except ImportError:
    Bridge = None
    print("Bridge not available here: angles are printed but NOT sent to the arm.")

SEND_HZ = 20                    # updates per second to the microcontroller. Keep sending even when the
                                # angles don't change: the sketch freezes the arm if nothing arrives for 0.5 s.
_mcu_errors = 0


def send_to_mcu(angles):
    """Send (base, shoulder, elbow, gripper) to the STM32 sketch over the Bridge.
    The sketch registers config.MCU_METHOD and takes 4 integers (degrees)."""
    global _mcu_errors
    if Bridge is None:
        return
    base, shoulder, elbow, gripper = (int(round(a)) for a in angles)
    try:
        Bridge.call(config.MCU_METHOD, base, shoulder, elbow, gripper)
    except Exception as exc:                   # never let a link problem stop the vision loop
        _mcu_errors += 1
        if _mcu_errors == 1 or _mcu_errors % 100 == 0:
            print(f"Bridge call failed ({_mcu_errors} so far): {exc!r}")


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