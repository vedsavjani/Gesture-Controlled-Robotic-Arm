"""The full Linux-side program: camera -> hand tracker -> gesture -> controller -> 4 angles -> STM32.

Prints 4 lines per second:
  FPS | stable gesture | moving joint + speed | base shoulder elbow gripper (deg)
A dedicated sender thread sends the latest angles to sketch/sketch.ino over the Bridge at
config.MCU_SEND_HZ (20 Hz) without blocking the vision loop. If the vision loop stalls for
longer than config.MCU_STALE_SEC, sending pauses so the STM32 watchdog freezes the arm.
If the Bridge library can't be imported (e.g. on a laptop), the angles are only printed.
Stop with Ctrl+C.
"""
import threading
import time

import config
from camera import Camera
from controller import ArmController
from gestures import classify
from hand import HandTracker

try:
    from arduino.app_utils import Bridge     # Arduino's Linux<->STM32 link (UNO Q only)
except ImportError:
    Bridge = None
    print("Bridge not available here: angles are printed but NOT sent to the arm.")


class McuSender:
    """Sends (base, shoulder, elbow, gripper) to the STM32 at a steady rate on a background thread."""

    def __init__(self, hz=config.MCU_SEND_HZ, stale_sec=config.MCU_STALE_SEC):
        self._period = 1.0 / hz
        self._stale_sec = stale_sec
        self._lock = threading.Lock()
        self._angles = None
        self._updated_at = 0.0
        self._errors = 0
        self._stop = threading.Event()
        self._thread = None
        if Bridge is not None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def update(self, angles, now):
        with self._lock:
            self._angles = tuple(int(round(a)) for a in angles)
            self._updated_at = now

    def _run(self):
        next_t = time.monotonic()
        while not self._stop.is_set():
            with self._lock:
                angles = self._angles
                updated_at = self._updated_at
            now = time.monotonic()
            if angles is not None and (now - updated_at) <= self._stale_sec:
                try:
                    Bridge.call(config.MCU_METHOD, *angles)
                except Exception as exc:      # never let a link problem stop the vision loop
                    self._errors += 1
                    if self._errors == 1 or self._errors % 100 == 0:
                        print(f"Bridge call failed ({self._errors} so far): {exc!r}")
            next_t += self._period
            delay = next_t - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_t = time.monotonic()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def main():
    cam = Camera()
    tracker = HandTracker()
    arm = ArmController()
    sender = McuSender()
    last_print = time.monotonic()
    frames = 0

    try:
        while True:
            frame, _ = cam.read(timeout=0.05)
            if frame is None:
                continue
            res = tracker.process(frame)
            if res is None:
                gesture, palm_frac = "none", None
            else:
                gesture, _, m = classify(res[0], frame_h=frame.shape[0])
                palm_frac = m["palm_frac"]
            now = time.monotonic()
            angles = arm.update(gesture, palm_frac, now)
            sender.update(angles, now)
            frames += 1

            if now - last_print >= 0.25:
                fps = frames / (now - last_print)
                if arm.active == "home":
                    moving = f"home glide @ {arm.speed:4.1f} deg/s"
                elif arm.active:
                    moving = f"{arm.active} @ {arm.speed:4.1f} deg/s"
                else:
                    moving = "-"
                b, s, e, g = angles
                print(f"{fps:5.1f} FPS | {arm.stable:13s} | {moving:30s} | "
                      f"base {b:5.1f}  shoulder {s:5.1f}  elbow {e:5.1f}  gripper {g:5.1f}")
                frames, last_print = 0, now
    except KeyboardInterrupt:
        pass
    finally:
        sender.stop()
        cam.stop()


if __name__ == "__main__":
    main()
