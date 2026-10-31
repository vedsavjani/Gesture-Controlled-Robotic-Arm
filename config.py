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
JOINTS = ("base", "shoulder", "elbow")
HOME = {"base": 90.0, "shoulder": 90.0, "elbow": 90.0}
LIMITS = {"base": (0.0, 180.0), "shoulder": (0.0, 180.0), "elbow": (0.0, 180.0)}   # (min, max) deg
GRIPPER_OPEN, GRIPPER_CLOSED = 30.0, 100.0     # deg; claw starts open

# Speed from hand distance (palm size in px, measured Oct 31: far ~75-80, near ~190-250)
PALM_FAR, PALM_NEAR = 80.0, 200.0              # px
SPEED_FAST, SPEED_SLOW = 20.0, 3.0             # deg/s at PALM_FAR / PALM_NEAR
PALM_SMOOTHING = 0.3                           # 0..1, lower = smoother (exponential moving average)
HOME_SPEED = 30.0                              # deg/s when gliding home on a fist
STOP_FRAMES = 2                                # frames of a different gesture before a motion stops


def _default_gateway():
    """IPv4 default gateway from Linux's routing table (same info as `ip route`), or None."""
    try:
        with open("/proc/net/route") as f:
            next(f)                                    # skip the header line
            for line in f:
                fields = line.split()
                # destination 00000000 = default route; flag 0x2 = it goes via a gateway
                if fields[1] == "00000000" and int(fields[3], 16) & 0x2:
                    return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
    except (OSError, IndexError, ValueError):
        pass                                           # not Linux, or no network
    return None


def camera_url():
    url = os.environ.get("CAMERA_URL")
    if url:
        print(f"Camera: {url} (from CAMERA_URL)")
        return url
    gateway = _default_gateway()
    if gateway:
        url = f"http://{gateway}:{CAMERA_PORT}/video"
        print(f"Camera: {url} (auto: phone = hotspot gateway)")
        return url
    raise SystemExit("No camera URL: not on a network with a gateway, and CAMERA_URL is not set.\n"
                     "Set it: export CAMERA_URL=http://<PHONE_IP>:8080/video  (README 5.7)")