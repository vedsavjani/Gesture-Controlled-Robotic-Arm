"""
Proof that the phone camera works as a live OpenCV input.

Shows the phone's live feed in a window with FPS, resolution and lag info,
and records the first 10 seconds to proof.mp4 

Run:
    python phone_cam_demo.py http://<PHONE_IP>:8080/video

Keys:  s = save snapshot    q = quit
"""
import sys
import threading
import time
from datetime import datetime

import cv2

URL = sys.argv[1] if len(sys.argv) > 1 else "http://100.79.200.43:8080/video"
RECORD_SECONDS = 10


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
        with self.lock:
            n, self.new_frames = self.new_frames, 0
            return (None if self.frame is None else self.frame.copy()), n

    def stop(self):
        self.running = False
        self.cap.release()


def main():
    cam = LatestFrameReader(URL)
    writer, rec_start = None, None
    received, fps, t0 = 0, 0.0, time.time()
    total_frames = 0

    print("Streaming... press 'q' in the video window to quit, 's' for a snapshot.")
    while True:
        frame, n = cam.read()
        if frame is None:
            time.sleep(0.01)
            continue
        received += n
        total_frames += n

        if time.time() - t0 >= 1.0:
            fps = received / (time.time() - t0)
            received, t0 = 0, time.time()

        h, w = frame.shape[:2]
        if w > 640:  # shrink for display/recording
            frame = cv2.resize(frame, (640, int(h * 640 / w)))
        dh, dw = frame.shape[:2]

        now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        lines = [
            "PHONE CAM -> OPENCV : LIVE",
            f"Camera FPS: {fps:4.1f}",
            f"Source: {w}x{h}",
            f"Laptop clock: {now}",
            f"Frames received: {total_frames}",
        ]
        for i, text in enumerate(lines):
            y = 28 + i * 26
            cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4)
            cv2.putText(frame, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

        # Record the first RECORD_SECONDS as proof
        if writer is None and rec_start is None:
            writer = cv2.VideoWriter("proof.mp4", cv2.VideoWriter_fourcc(*"mp4v"), 15, (dw, dh))
            rec_start = time.time()
            print(f"Recording {RECORD_SECONDS}s to proof.mp4 ...")
        if writer is not None:
            writer.write(frame)
            if time.time() - rec_start >= RECORD_SECONDS:
                writer.release()
                writer = None
                print("Saved proof.mp4")

        cv2.imshow("Phone camera via OpenCV", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("s"):
            name = f"snapshot_{datetime.now().strftime('%H%M%S')}.jpg"
            cv2.imwrite(name, frame)
            print(f"Saved {name}")
        elif key == ord("q"):
            break

    if writer is not None:
        writer.release()
    cam.stop()
    cv2.destroyAllWindows()
    print(f"Done. Total frames received: {total_frames}")


if __name__ == "__main__":
    main()