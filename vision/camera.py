"""
Shared phone-camera reader. Every script (stream test, MediaPipe test,
final arm controller) imports this, so fixes happen in one place.
Same class as in phone_cam_demo.py.
"""
import threading

import cv2


class LatestFrameReader:
    """Background thread that always keeps only the newest frame (avoids lag build-up)."""

    def __init__(self, url):
        self.cap = cv2.VideoCapture(url)
        if not self.cap.isOpened():
            raise SystemExit(f"Could not open {url} - is IP Webcam running and are you on the hotspot?")
        self.frame, self.new_frames = None, 0
        self.lock = threading.Lock()
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = f
                    self.new_frames += 1

    def read(self):
        """Returns (newest frame or None, number of new frames since the last read)."""
        with self.lock:
            n, self.new_frames = self.new_frames, 0
            return (None if self.frame is None else self.frame.copy()), n

    def stop(self):
        self.running = False
        self.cap.release()