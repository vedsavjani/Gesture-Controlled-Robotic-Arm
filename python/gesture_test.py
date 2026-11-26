"""Live gesture check: shows each gesture as the board sees it. Ctrl+C to stop.

Each line (4 per second):
  STABLE gesture (after debounce) | raw gesture | palm size px | fingers up (T I M R P) | ratios
Hold each gesture for ~2 s and check STABLE matches. If one is misread, the ratios show which
threshold in gestures.py to adjust.
Palm size: hold one gesture at your NEAR and FAR positions and note the px values (speed control).
"""
import time

from camera import Camera
from gestures import Debouncer, classify
from hand import HandTracker


def main():
    cam = Camera()
    tracker = HandTracker()
    debounce = Debouncer()
    last = 0.0
    try:
        while True:
            frame, _ = cam.read(timeout=0.05)
            if frame is None:
                continue
            res = tracker.process(frame)
            now = time.monotonic()
            if res is None:
                stable = debounce.update("none", now)
                line = f"{stable:13s} | no hand"
            else:
                g, s, m = classify(res[0], frame_h=frame.shape[0])
                stable = debounce.update(g, now)
                fingers = "".join("1" if s[f] else "0" for f in ("thumb", "index", "middle", "ring", "pinky"))
                line = (f"{stable:13s} | raw {g:13s} | palm {m['palm_px']:5.1f} px | TIMRP {fingers} | thumb {m['thumb']:.2f} "
                        f"pinch {m['pinch']:.2f} | I {m['index']:.2f} M {m['middle']:.2f} "
                        f"R {m['ring']:.2f} P {m['pinky']:.2f}")
            if now - last >= 0.25:
                print(line)
                last = now
    except KeyboardInterrupt:
        pass
    finally:
        cam.stop()


if __name__ == "__main__":
    main()
