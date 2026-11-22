"""Long-run test (default 10 min): does FPS hold as the board heats up? Any crash?

Keep a hand in view most of the time. Prints a line every 10 s, then a summary.
Run:  python soak_test.py          or  python soak_test.py 300   (seconds)
"""
import glob
import sys
import time

from camera import Camera
from hand import HandTracker

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 600
REPORT = 10


def cpu_temp():
    """Hottest thermal zone in degC (Linux exposes them under /sys/class/thermal), or None."""
    temps = []
    for path in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
        try:
            temps.append(int(open(path).read()) / 1000)
        except (OSError, ValueError):
            pass
    return max(temps) if temps else None


cam = Camera()
tracker = HandTracker()
start = last = time.time()
last_received = cam.received
frames = found = 0
history = []                                   # (minute, fps, arriving, temp)
try:
    while time.time() - start < DURATION:
        frame, _ = cam.read()
        if frame is None:
            time.sleep(0.002)
            continue
        found += tracker.process(frame) is not None
        frames += 1
        now = time.time()
        if now - last >= REPORT:
            dt = now - last
            fps, arriving, temp = frames / dt, (cam.received - last_received) / dt, cpu_temp()
            history.append(((now - start) / 60, fps, arriving, temp))
            t = f"{temp:4.1f} C" if temp is not None else "  n/a"
            print(f"{(now - start) / 60:4.1f} min | {fps:5.1f} FPS | arriving {arriving:4.1f}/s "
                  f"| hand {found}/{frames} | {t}")
            frames = found = 0
            last, last_received = now, cam.received
except KeyboardInterrupt:
    pass
finally:
    cam.stop()

if len(history) >= 2:
    first, end = history[:3], history[-3:]
    avg = lambda rows, i: sum(r[i] for r in rows) / len(rows)
    temps = [r[3] for r in history if r[3] is not None]
    print(f"\nFPS first 30 s: {avg(first, 1):.1f}   last 30 s: {avg(end, 1):.1f}")
    if temps:
        print(f"CPU temp start: {temps[0]:.1f} C   peak: {max(temps):.1f} C")