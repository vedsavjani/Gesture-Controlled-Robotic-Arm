"""
Stage 3+4: our own hand tracker (palm detector + landmark model on TFLite, 4 threads),
running live on the phone stream. Prints FPS. At the end saves:
  track_out.jpg  - last frame with the 21-point hand skeleton drawn
  track_crop.jpg - the 224x224 hand crop the landmark model saw
Run (from ~/gesture-arm, with venv-tflite active):
    python track_test.py http://<PHONE_IP>:8080/video
"""
import math
import sys
import time

import cv2
import numpy as np
from ai_edge_litert.interpreter import Interpreter

from camera import LatestFrameReader

URL = sys.argv[1] if len(sys.argv) > 1 else "http://10.138.189.35:8080/video"
TEST_SECONDS = 15
THREADS = 4
PALM_SIZE, LM_SIZE = 192, 224
PALM_THRESH, PRESENCE_THRESH = 0.5, 0.5

HAND_CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8),
                    (5, 9), (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15),
                    (15, 16), (13, 17), (0, 17), (17, 18), (18, 19), (19, 20)]


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -80, 80)))


def load(path):
    it = Interpreter(model_path=path, num_threads=THREADS)
    it.allocate_tensors()
    return it


# ---------------- palm detector (same as Stage 2, 0..1 scaling) ----------------
def make_anchors():
    a = []
    for stride, per_cell in ((8, 2), (16, 6)):
        g = PALM_SIZE // stride
        for y in range(g):
            for x in range(g):
                for _ in range(per_cell):
                    a.append(((x + 0.5) / g, (y + 0.5) / g))
    return np.array(a, dtype=np.float32)


ANCHORS = make_anchors()
palm_model = load("models/hand_detector.tflite")
palm_in = palm_model.get_input_details()[0]["index"]
palm_out = {tuple(d["shape"]): d["index"] for d in palm_model.get_output_details()}


def detect_palm(rgb):
    """Returns (center_x, center_y, size, keypoints) in frame pixels, or None."""
    h, w = rgb.shape[:2]
    scale = PALM_SIZE / max(h, w)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    pad_x, pad_y = (PALM_SIZE - nw) // 2, (PALM_SIZE - nh) // 2
    canvas = np.zeros((PALM_SIZE, PALM_SIZE, 3), dtype=np.uint8)
    canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = cv2.resize(rgb, (nw, nh))

    palm_model.set_tensor(palm_in, (canvas.astype(np.float32) / 255.0)[np.newaxis])
    palm_model.invoke()
    raw = palm_model.get_tensor(palm_out[(1, 2016, 18)])[0]
    scores = sigmoid(palm_model.get_tensor(palm_out[(1, 2016, 1)])[0, :, 0])
    i = int(np.argmax(scores))
    if scores[i] < PALM_THRESH:
        return None

    ax, ay = ANCHORS[i]
    r = raw[i]

    def to_px(nx, ny):
        return (nx * PALM_SIZE - pad_x) / scale, (ny * PALM_SIZE - pad_y) / scale

    cx, cy = to_px(r[0] / PALM_SIZE + ax, r[1] / PALM_SIZE + ay)
    size = max(r[2], r[3]) / scale                      # box side in frame pixels
    kps = [to_px(r[4 + 2 * k] / PALM_SIZE + ax, r[5 + 2 * k] / PALM_SIZE + ay) for k in range(7)]
    return cx, cy, size, kps


# ---------------- crop region (MediaPipe's rotation / scale / shift rules) ----------------
def rotation_from(p_start, p_end):
    """Angle that turns the start->end direction to point straight up."""
    r = math.pi / 2 - math.atan2(-(p_end[1] - p_start[1]), p_end[0] - p_start[0])
    return (r + math.pi) % (2 * math.pi) - math.pi


def make_roi(cx, cy, w, h, rot, scale, shift_y):
    """Square rotated crop region: center, side length, rotation."""
    u = np.array([math.cos(rot), math.sin(rot)])         # crop's "right" direction
    v = np.array([-math.sin(rot), math.cos(rot)])        # crop's "down" direction
    center = np.array([cx, cy]) + v * h * shift_y        # negative shift = toward the fingers
    return center, max(w, h) * scale, rot


def roi_from_palm(det):
    cx, cy, size, kps = det
    rot = rotation_from(kps[0], kps[2])                  # wrist -> middle-finger base
    return make_roi(cx, cy, size, size, rot, scale=2.6, shift_y=-0.5)


def roi_from_landmarks(pts):
    rot = rotation_from(pts[0], pts[9])                  # wrist -> middle-finger base
    sub = pts[[0, 1, 2, 3, 5, 6, 9, 10, 13, 14, 17, 18], :2]
    u = np.array([math.cos(rot), math.sin(rot)])
    v = np.array([-math.sin(rot), math.cos(rot)])
    c0 = sub.mean(axis=0)
    a, b = (sub - c0) @ u, (sub - c0) @ v                # coordinates along the crop's axes
    ca, cb = (a.min() + a.max()) / 2, (b.min() + b.max()) / 2
    cx, cy = c0 + u * ca + v * cb
    return make_roi(cx, cy, a.max() - a.min(), b.max() - b.min(), rot, scale=2.0, shift_y=-0.1)


def crop(rgb, roi):
    center, side, rot = roi
    u = np.array([math.cos(rot), math.sin(rot)]) * side / 2
    v = np.array([-math.sin(rot), math.cos(rot)]) * side / 2
    src = np.float32([center - u - v, center + u - v, center - u + v])   # TL, TR, BL corners
    dst = np.float32([[0, 0], [LM_SIZE, 0], [0, LM_SIZE]])
    M = cv2.getAffineTransform(src, dst)
    return cv2.warpAffine(rgb, M, (LM_SIZE, LM_SIZE), borderValue=(0, 0, 0)), M


# ---------------- landmark model ----------------
lm_model = load("models/hand_landmarks_detector.tflite")
lm_in = lm_model.get_input_details()[0]["index"]
lm_out = {d["name"]: d["index"] for d in lm_model.get_output_details()}


def run_landmarks(crop_rgb, M):
    lm_model.set_tensor(lm_in, (crop_rgb.astype(np.float32) / 255.0)[np.newaxis])
    lm_model.invoke()
    pts = lm_model.get_tensor(lm_out["Identity"])[0].reshape(21, 3)       # crop pixels
    raw_presence = float(lm_model.get_tensor(lm_out["Identity_1"])[0, 0])
    presence = raw_presence if 0.0 <= raw_presence <= 1.0 else float(sigmoid(raw_presence))
    Minv = cv2.invertAffineTransform(M)
    xy = np.hstack([pts[:, :2], np.ones((21, 1))]) @ Minv.T                # back to frame pixels
    return np.hstack([xy, pts[:, 2:3]]), presence


# ---------------- live loop ----------------
cam = LatestFrameReader(URL)
time.sleep(1)

roi, last = None, None
start = report_t = time.time()
frames = all_frames = searching = 0
lm_ms = palm_ms = 0.0
lm_runs = palm_runs = 0

while time.time() - start < TEST_SECONDS:
    frame, _ = cam.read()
    if frame is None:
        time.sleep(0.01)
        continue
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    if roi is None:                                      # no hand tracked -> search
        t = time.time()
        det = detect_palm(rgb)
        palm_ms += (time.time() - t) * 1000
        palm_runs += 1
        searching += 1
        if det is not None:
            roi = roi_from_palm(det)

    presence = 0.0
    if roi is not None:                                  # hand known -> landmarks only
        t = time.time()
        c, M = crop(rgb, roi)
        pts, presence = run_landmarks(c, M)
        lm_ms += (time.time() - t) * 1000
        lm_runs += 1
        if presence < PRESENCE_THRESH:
            roi = None                                   # lost it -> search next frame
        else:
            roi = roi_from_landmarks(pts)                # crop for the next frame
            last = (frame.copy(), pts, c)

    frames += 1
    all_frames += 1
    if time.time() - report_t >= 1.0:
        fps = frames / (time.time() - report_t)
        state = "tracking" if roi is not None else "searching"
        lm_txt = f"{lm_ms / lm_runs:5.1f}" if lm_runs else "  -  "
        palm_txt = f"{palm_ms / palm_runs:5.1f}" if palm_runs else "  -  "
        tip = f" | index tip x={last[1][8, 0]:.0f}px y={last[1][8, 1]:.0f}px" if roi is not None else ""
        print(f"{fps:5.1f} FPS | {state:9s} | landmarks {lm_txt} ms | palm {palm_txt} ms | presence {presence:.2f}{tip}")
        frames, lm_ms, palm_ms, lm_runs, palm_runs = 0, 0.0, 0.0, 0, 0
        report_t = time.time()

print(f"Average FPS: {all_frames / (time.time() - start):.1f}  "
      f"({searching} of {all_frames} frames spent searching)")
cam.stop()

if last is not None:
    img, pts, c = last
    for a, b in HAND_CONNECTIONS:
        cv2.line(img, tuple(int(v) for v in pts[a, :2]), tuple(int(v) for v in pts[b, :2]), (0, 255, 0), 2)
    for x, y, _ in pts:
        cv2.circle(img, (int(x), int(y)), 4, (0, 0, 255), -1)
    cv2.imwrite("track_out.jpg", img)
    cv2.imwrite("track_crop.jpg", cv2.cvtColor(c, cv2.COLOR_RGB2BGR))
    print("Saved track_out.jpg and track_crop.jpg")
else:
    print("No hand was tracked - nothing saved.")