"""Phone camera reader. Keeps only the newest frame, reconnects, stops cleanly.

Do not change a frame returned by read(). Copy it first.
"""
import threading
import time

import cv2

import config


class Camera:
    def __init__(self, url=None):
        self.url = url or config.camera_url()
        self._frame = None
        self._stamp = 0.0      # time the newest frame arrived
        self._count = 0        # frames received
        self._seen = 0         # frames already given out
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _open(self):
        return cv2.VideoCapture(
            self.url, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000])

    def _run(self):
        while not self._stop.is_set():
            cap = self._open()
            if cap.isOpened():
                while not self._stop.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        break                      # stream dropped: reconnect
                    with self._lock:
                        self._frame = frame
                        self._stamp = time.time()
                        self._count += 1
            cap.release()
            self._stop.wait(1.0)                   # pause before retry

    @property
    def received(self):
        """Total frames received from the phone so far (to compare with frames processed)."""
        with self._lock:
            return self._count

    def read(self):
        """Returns (frame, age_in_seconds) for a NEW frame, else (None, 0)."""
        with self._lock:
            if self._count == self._seen:
                return None, 0.0
            self._seen = self._count
            return self._frame, time.time() - self._stamp

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=5)