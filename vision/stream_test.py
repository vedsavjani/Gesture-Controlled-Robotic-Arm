"""
Headless stream test for the UNO Q: how many FPS arrive from the phone?
Run:  python stream_test.py http://<PHONE_IP>:8080/video
"""
import sys
import time

import cv2

from camera import LatestFrameReader

URL = sys.argv[1] if len(sys.argv) > 1 else "http://10.138.189.35:8080/video"
TEST_SECONDS = 10

cam = LatestFrameReader(URL)
time.sleep(1)  # let the stream start

total, t0 = 0, time.time()
for _ in range(TEST_SECONDS):
    time.sleep(1)
    frame, n = cam.read()
    total += n
    size = "no frame yet" if frame is None else f"{frame.shape[1]}x{frame.shape[0]}"
    print(f"{n:3d} frames this second | {size}")

print(f"Average arrival FPS: {total / (time.time() - t0):.1f}")
if frame is not None:
    cv2.imwrite("stream_frame.jpg", frame)
    print("Saved stream_frame.jpg")
cam.stop()