"""Hand tracker: BGR frame in, 21 hand points out (frame pixels).

Two TFLite models, 4 threads:
  palm detector  - finds a hand in the whole frame (slow, used only when searching)
  landmark model - reads 21 points from a rotated crop (fast, every frame)
After a hand is found, the next crop is built from the last 21 points,
so the palm detector is skipped until the hand is lost.
"""
import math

import cv2
import numpy as np
from ai_edge_litert.interpreter import Interpreter

import config

PALM_SIZE = 192
LM_SIZE = 224
PALM_THRESH = 0.5
# Sigmoid is strictly monotonic: sigmoid(x) >= p  <=>  x >= log(p / (1 - p)).
_PALM_LOGIT_THRESH = math.log(PALM_THRESH / (1.0 - PALM_THRESH))
PRESENCE_THRESH = 0.5
MIN_ROI = 20          # pixels; smaller crop means the hand is lost
_INV_255 = np.float32(1.0 / 255.0)


def _load(name):
    it = Interpreter(model_path=f"{config.MODEL_DIR}/{name}", num_threads=config.THREADS)
    it.allocate_tensors()
    return it


def _make_anchors():
    anchors = []
    for stride, per_cell in ((8, 2), (16, 6)):
        grid = PALM_SIZE // stride
        for y in range(grid):
            for x in range(grid):
                for _ in range(per_cell):
                    anchors.append(((x + 0.5) / grid, (y + 0.5) / grid))
    return np.array(anchors, dtype=np.float32)


def _rotation(start, end):
    """Angle that turns the start->end direction to point straight up."""
    r = math.pi / 2 - math.atan2(-(end[1] - start[1]), end[0] - start[0])
    return (r + math.pi) % (2 * math.pi) - math.pi


def _axes(rot):
    c, s = math.cos(rot), math.sin(rot)
    return np.array([c, s]), np.array([-s, c])


def _make_roi(cx, cy, w, h, rot, scale, shift_y):
    """Square rotated crop: (center, side length, rotation)."""
    _, down = _axes(rot)
    center = np.array([cx, cy]) + down * h * shift_y   # negative = toward fingers
    return center, max(w, h) * scale, rot


def _roi_from_palm(palm):
    cx, cy, size, kps = palm
    rot = _rotation(kps[0], kps[2])                    # wrist -> middle-finger base
    return _make_roi(cx, cy, size, size, rot, 2.6, -0.5)


def _roi_from_points(pts):
    rot = _rotation(pts[0], pts[9])                    # wrist -> middle-finger base
    right, down = _axes(rot)
    sub = pts[[0, 1, 2, 3, 5, 6, 9, 10, 13, 14, 17, 18], :2]
    c0 = sub.mean(axis=0)
    diff = sub - c0
    a, b = diff @ right, diff @ down
    mid_a, mid_b = (a.min() + a.max()) / 2, (b.min() + b.max()) / 2
    cx, cy = c0 + right * mid_a + down * mid_b
    return _make_roi(cx, cy, a.max() - a.min(), b.max() - b.min(), rot, 2.0, -0.1)


def _crop_rgb(bgr, roi):
    """Warp the rotated ROI from BGR first, then convert only the 224x224 crop to RGB (6x less work)."""
    center, side, rot = roi
    right, down = _axes(rot)
    u, v = right * (side * 0.5), down * (side * 0.5)
    src = np.float32([center - u - v, center + u - v, center - u + v])   # TL, TR, BL
    dst = np.float32([[0, 0], [LM_SIZE, 0], [0, LM_SIZE]])
    m = cv2.getAffineTransform(src, dst)
    crop_bgr = cv2.warpAffine(bgr, m, (LM_SIZE, LM_SIZE))
    return cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB), m


class HandTracker:
    def __init__(self, store_crop=False):
        self._palm = _load("hand_detector.tflite")
        self._palm_in = self._palm.get_input_details()[0]["index"]
        shapes = {tuple(d["shape"]): d["index"] for d in self._palm.get_output_details()}
        self._palm_boxes = shapes[(1, 2016, 18)]
        self._palm_scores = shapes[(1, 2016, 1)]
        self._anchors = _make_anchors()

        self._lm = _load("hand_landmarks_detector.tflite")
        self._lm_in = self._lm.get_input_details()[0]["index"]
        lm_outs = self._lm.get_output_details()
        names = {d["name"]: d["index"] for d in lm_outs}
        if "Identity" in names and "Identity_1" in names:
            self._lm_points = names["Identity"]
            self._lm_presence = names["Identity_1"]
        else:
            # Fallback by tensor shape for re-exported TFLite models
            pts_idx = next((d["index"] for d in lm_outs if tuple(d["shape"]) == (1, 63)), None)
            scalars = [d["index"] for d in lm_outs if tuple(d["shape"]) == (1, 1)]
            if pts_idx is None or not scalars:
                raise RuntimeError(f"Unexpected landmark outputs: {sorted(names)}")
            self._lm_points = pts_idx
            self._lm_presence = scalars[0]

        # Pre-allocated input buffers to avoid per-frame allocations
        self._palm_canvas = np.zeros((PALM_SIZE, PALM_SIZE, 3), dtype=np.uint8)
        self._palm_buf = np.empty((1, PALM_SIZE, PALM_SIZE, 3), dtype=np.float32)
        self._lm_buf = np.empty((1, LM_SIZE, LM_SIZE, 3), dtype=np.float32)

        self._roi = None
        self._store_crop = store_crop
        self.last_crop = None           # RGB crop the landmark model saw (populated only when store_crop=True)

    def reset(self):
        self._roi = None
        self.last_crop = None

    def process(self, bgr):
        """Returns (points, presence) or None.
        points: 21x3 array. x, y are frame pixels. z is not scaled."""
        if self._roi is None:
            palm = self._detect_palm(bgr)
            if palm is None:
                return None
            self._roi = _roi_from_palm(palm)
        crop, m = _crop_rgb(bgr, self._roi)
        if self._store_crop:
            self.last_crop = crop
        points, presence = self._run_landmarks(crop, m)
        if presence < PRESENCE_THRESH:
            self._roi = None
            return None
        roi = _roi_from_points(points)
        self._roi = roi if roi[1] >= MIN_ROI else None
        return points, presence

    def _detect_palm(self, bgr):
        h, w = bgr.shape[:2]
        scale = PALM_SIZE / max(h, w)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        pad_x, pad_y = (PALM_SIZE - nw) // 2, (PALM_SIZE - nh) // 2

        # Resize in BGR first, then convert only the <=192x192 image to RGB (11x fewer pixels)
        small_bgr = cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        self._palm_canvas.fill(0)
        self._palm_canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2RGB)
        np.multiply(self._palm_canvas, _INV_255, out=self._palm_buf[0])

        self._palm.set_tensor(self._palm_in, self._palm_buf)
        self._palm.invoke()
        logits = self._palm.get_tensor(self._palm_scores)[0, :, 0]
        i = int(np.argmax(logits))
        if logits[i] < _PALM_LOGIT_THRESH:
            return None

        raw = self._palm.get_tensor(self._palm_boxes)[0]
        ax, ay = self._anchors[i]
        r = raw[i]

        def to_px(nx, ny):
            return (nx * PALM_SIZE - pad_x) / scale, (ny * PALM_SIZE - pad_y) / scale

        cx, cy = to_px(r[0] / PALM_SIZE + ax, r[1] / PALM_SIZE + ay)
        size = max(r[2], r[3]) / scale
        kps = [to_px(r[4 + 2 * k] / PALM_SIZE + ax, r[5 + 2 * k] / PALM_SIZE + ay)
               for k in range(7)]
        return cx, cy, size, kps

    def _run_landmarks(self, crop, m):
        np.multiply(crop, _INV_255, out=self._lm_buf[0])
        self._lm.set_tensor(self._lm_in, self._lm_buf)
        self._lm.invoke()
        pts = self._lm.get_tensor(self._lm_points)[0].reshape(21, 3)    # crop pixels
        presence = float(self._lm.get_tensor(self._lm_presence)[0, 0])   # already 0..1
        inv = cv2.invertAffineTransform(m)
        xy = np.hstack([pts[:, :2], np.ones((21, 1))]) @ inv.T          # back to frame
        return np.hstack([xy, pts[:, 2:3]]), presence