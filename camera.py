"""Phone camera reader. Keeps only the newest frame, reconnects, stops cleanly.

Do not mutate a frame returned by read(). Copy it first.
"""
import os
import threading
import time

# Reduce FFmpeg internal buffering for lower MJPEG latency before cv2 initializes FFmpeg.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "fflags;nobuffer|flags;low_delay")

import cv2

import config


class Camera:
    def __init__(self, url=None):
        self.url = url or config.camera_url()
        self._frame = None
        self._stamp = 0.0        # monotonic time the newest frame arrived
        self._count = 0        # frames received
        self._seen = 0         # frames already given out
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _open(self):
        cap = cv2.VideoCapture(
            self.url, cv2.CAP_FFMPEG,
            [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000])
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run(self):
        while not self._stop.is_set():
            cap = self._open()
            try:
                if cap.isOpened():
                    while not self._stop.is_set():
                        ok, frame = cap.read()
                        if not ok:
                            break       # stream dropped: reconnect
                        now = time.monotonic()
                        with self._cond:
                            self._frame = frame
                            self._stamp = now
                            self._count += 1
                            self._cond.notify_all()
            finally:
                cap.release()
            self._stop.wait(1.0)                   # pause before retry

    @property
    def received(self):
        """Total frames received from the phone so far (to compare with frames processed)."""
        with self._lock:
            return self._count

    def read(self, timeout=0.0):
        """Returns (frame, age_in_seconds) for a NEW frame, else (None, 0.0).
        If timeout > 0, waits up to `timeout` seconds for a new frame (no busy-wait polling)."""
        with self._cond:
            if self._count == self._seen and timeout > 0.0 and not self._stop.is_set():
                self._cond.wait(timeout)
            if self._count == self._seen:
                return None, 0.0
            self._seen = self._count
            return self._frame, max(0.0, time.monotonic() - self._stamp)

    def stop(self):
        self._stop.set()
        with self._cond:
            self._cond.notify_all()
        self._thread.join(timeout=6.0)
