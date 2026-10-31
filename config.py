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