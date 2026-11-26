"""Settings in one place.

Camera URL, in this order:
  1. CAMERA_URL environment variable, if set   (manual override)
  2. http://<default gateway>:8080/video        (on the phone hotspot, the gateway IS the phone)
  3. otherwise: stop with a clear error
"""
import os
import socket
import struct

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
THREADS = 4
CAMERA_PORT = 8080           # IP Webcam's default port

# ---------------- Arm (controller.py) ----------------
# PLACEHOLDERS until the assembled arm is measured: set each servo to 90 deg before fitting its
# horn, then find each joint's safe min/max and a good home pose, and update these.
# LIMITS must match MIN_A / MAX_A in sketch/sketch.ino (the sketch clamps again as a safety net).
# CHANGED Nov 1: LIMITS were 0..180 for every joint; now 20..160 so that an untested arm can't be
# driven into its mechanical stops. These are still interim values. When the real arm is measured
# (README task 4), update LIMITS, HOME and GRIPPER_* here AND MIN_A / MAX_A / HOME_A in the sketch.
JOINTS = ("base", "shoulder", "elbow")
HOME = {"base": 90.0, "shoulder": 90.0, "elbow": 90.0}
LIMITS = {"base": (20.0, 160.0), "shoulder": (20.0, 160.0), "elbow": (20.0, 160.0)}   # (min, max) deg
GRIPPER_OPEN, GRIPPER_CLOSED = 30.0, 100.0     # deg; claw starts open

# Speed from hand distance (resolution-independent fraction of frame height;
# matches 80..200 px at 640x480: far ~0.167, near ~0.417).
PALM_FAR_FRAC, PALM_NEAR_FRAC = 80.0 / 480.0, 200.0 / 480.0
PALM_FAR, PALM_NEAR = 80.0, 200.0            # legacy 480p px values (kept for display/tuning)
SPEED_FAST, SPEED_SLOW = 20.0, 3.0             # deg/s at PALM_FAR / PALM_NEAR
PALM_TAU_SEC = 0.15                          # time constant (s) for dt-aware EMA smoothing
HOME_SPEED = 30.0                              # deg/s when gliding home on a fist
DEBOUNCE_SEC = 0.20                          # gesture must hold this long to trigger
STOP_FRAMES = 2                                # frames of a different gesture before a motion stops
GRIP_COOLDOWN_SEC = 1.0                      # minimum seconds between claw toggles

# ---------------- Microcontroller link (main.py -> sketch/sketch.ino) ----------------
# Name of the Bridge method the sketch registers: Bridge.provide("set_angles", ...).
# It takes 4 integers in this order: base, shoulder, elbow, gripper (degrees).
# The name must be identical in sketch/sketch.ino and here; main.py's MCU sender uses this value.
MCU_METHOD = "set_angles"
MCU_SEND_HZ = 20                             # steady transmit rate to the STM32
MCU_STALE_SEC = 0.40                         # stop transmitting if vision loop stalls (lets MCU watchdog freeze)


def _default_gateway():
    """IPv4 default gateway from Linux's routing table (lowest metric active route), or None."""
    candidates = []
    try:
        with open("/proc/net/route") as f:
            next(f)                                    # skip the header line
            for line in f:
                fields = line.split()
                if len(fields) < 7:
                    continue
                flags = int(fields[3], 16)
                # destination 00000000 = default route; flags 0x1 (UP) | 0x2 (GATEWAY)
                if fields[1] == "00000000" and (flags & 0x3) == 0x3:
                    metric = int(fields[6])
                    gw = socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
                    candidates.append((metric, gw))
    except (OSError, IndexError, ValueError):
        return None
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def camera_url(verbose=True):
    url = os.environ.get("CAMERA_URL")
    if url:
        if verbose:
            print(f"Camera: {url} (from CAMERA_URL)")
        return url
    gateway = _default_gateway()
    if gateway:
        url = f"http://{gateway}:{CAMERA_PORT}/video"
        if verbose:
            print(f"Camera: {url} (auto: phone = hotspot gateway)")
        return url
    raise SystemExit("No camera URL: not on a network with a gateway, and CAMERA_URL is not set.\n"
                     "Set it: export CAMERA_URL=http://<PHONE_IP>:8080/video  (README 5.7)")