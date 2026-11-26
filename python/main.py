"""The full Linux-side program: camera -> hand tracker -> gesture -> controller -> STM32 velocity commands."""
import sys
import threading
import time

import config
from camera import Camera
from controller import ArmController, MOVES
from gestures import classify
from hand import HandTracker

try:
    from arduino.app_utils import Bridge
except ImportError:
    Bridge = None
    print("Bridge not available here: commands are printed but NOT sent to the arm.", flush=True)

JOINT_IDX = {"base": 0, "shoulder": 1, "elbow": 2}


class McuSender:
    """Sends velocity commands ONLY on state change (0 Hz at hold, 1 Hz safety keepalive while moving)."""

    def __init__(self, keepalive_sec=0.8):
        self._keepalive_sec = keepalive_sec
        self._lock = threading.Lock()
        self._cmd = (-1, 0, int(round(config.GRIPPER_OPEN)))
        self._last_sent = None
        self._last_sent_at = 0.0
        self._errors = 0
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        if Bridge is not None:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def update(self, joint_id, speed_deg_s, grip_deg):
        if joint_id in (0, 1, 2):
            q_speed = int(round(speed_deg_s / 3.0)) * 3
            if q_speed == 0 and speed_deg_s != 0:
                q_speed = 3 if speed_deg_s > 0 else -3
        else:
            q_speed = int(round(speed_deg_s))
        cmd = (int(joint_id), q_speed, int(round(grip_deg)))
        with self._lock:
            changed = (cmd != self._cmd)
            self._cmd = cmd
        if changed:
            self._wake.set()

    def _send(self, cmd):
        if hasattr(Bridge, "notify"):
            Bridge.notify("set_cmd", *cmd)
        else:
            Bridge.call("set_cmd", *cmd)

    def _run(self):
        while not self._stop.is_set():
            self._wake.wait(timeout=0.1)
            self._wake.clear()
            if self._stop.is_set():
                break
            with self._lock:
                cmd = self._cmd
            now = time.monotonic()
            changed = (cmd != self._last_sent)
            moving_keepalive = (cmd[0] != -1) and ((now - self._last_sent_at) >= self._keepalive_sec)
            if changed or moving_keepalive:
                try:
                    self._send(cmd)
                    self._last_sent = cmd
                    self._last_sent_at = now
                except Exception as exc:
                    self._errors += 1
                    if self._errors == 1 or self._errors % 100 == 0:
                        print(f"Bridge send failed ({self._errors} so far): {exc!r}", flush=True)

    def stop(self):
        if Bridge is not None:
            with self._lock:
                grip = self._cmd[2]
            try:
                self._send((-1, 0, grip))
            except Exception:
                pass
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def main():
    sys.stdout.reconfigure(line_buffering=True)
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

            if arm.active in MOVES:
                joint, direction = MOVES[arm.active]
                sender.update(JOINT_IDX[joint], direction * arm.speed, angles[3])
            elif arm.active == "home":
                sender.update(99, config.HOME_SPEED, angles[3])
            else:
                sender.update(-1, 0, angles[3])

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