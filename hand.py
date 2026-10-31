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
PRESENCE_THRESH = 0.5
MIN_ROI = 20          # pixels; smaller crop means the hand is lost


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -80, 80)))


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
    right = np.array([math.cos(rot), math.sin(rot)])
    down = np.array([-math.sin(rot), math.cos(rot)])
    return right, down


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
    a, b = (sub - c0) @ right, (sub - c0) @ down
    mid_a, mid_b = (a.min() + a.max()) / 2, (b.min() + b.max()) / 2
    cx, cy = c0 + right * mid_a + down * mid_b
    return _make_roi(cx, cy, a.max() - a.min(), b.max() - b.min(), rot, 2.0, -0.1)


def _crop(rgb, roi):
    center, side, rot = roi
    right, down = _axes(rot)
    u, v = right * side / 2, down * side / 2
    src = np.float32([center - u - v, center + u - v, center - u + v])   # TL, TR, BL
    dst = np.float32([[0, 0], [LM_SIZE, 0], [0, LM_SIZE]])
    m = cv2.getAffineTransform(src, dst)
    return cv2.warpAffine(rgb, m, (LM_SIZE, LM_SIZE)), m


class HandTracker:
    def __init__(self):
        self._palm = _load("hand_detector.tflite")
        self._palm_in = self._palm.get_input_details()[0]["index"]
        shapes = {tuple(d["shape"]): d["index"] for d in self._palm.get_output_details()}
        self._palm_boxes = shapes[(1, 2016, 18)]
        self._palm_scores = shapes[(1, 2016, 1)]
        self._anchors = _make_anchors()

        self._lm = _load("hand_landmarks_detector.tflite")
        self._lm_in = self._lm.get_input_details()[0]["index"]
        names = {d["name"]: d["index"] for d in self._lm.get_output_details()}
        try:
            self._lm_points = names["Identity"]
            self._lm_presence = names["Identity_1"]
        except KeyError:
            raise RuntimeError(f"Unexpected landmark outputs: {sorted(names)}")

        self._roi = None
        self.last_crop = None          # RGB crop the landmark model saw (for debugging)

    def reset(self):
        self._roi = None

    def process(self, bgr):
        """Returns (points, presence) or None.
        points: 21x3 array. x, y are frame pixels. z is not scaled."""
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        if self._roi is None:
            palm = self._detect_palm(rgb)
            if palm is None:
                return None
            self._roi = _roi_from_palm(palm)
        crop, m = _crop(rgb, self._roi)
        self.last_crop = crop
        points, presence = self._run_landmarks(crop, m)
        if presence < PRESENCE_THRESH:
            self._roi = None
            return None
        roi = _roi_from_points(points)
        self._roi = roi if roi[1] >= MIN_ROI else None
        return points, presence

    def _detect_palm(self, rgb):
        h, w = rgb.shape[:2]
        scale = PALM_SIZE / max(h, w)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        pad_x, pad_y = (PALM_SIZE - nw) // 2, (PALM_SIZE - nh) // 2
        canvas = np.zeros((PALM_SIZE, PALM_SIZE, 3), dtype=np.uint8)
        canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = cv2.resize(rgb, (nw, nh))

        self._palm.set_tensor(self._palm_in, (canvas.astype(np.float32) / 255.0)[np.newaxis])
        self._palm.invoke()
        raw = self._palm.get_tensor(self._palm_boxes)[0]
        scores = _sigmoid(self._palm.get_tensor(self._palm_scores)[0, :, 0])
        i = int(np.argmax(scores))
        if scores[i] < PALM_THRESH:
            return None

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
        self._lm.set_tensor(self._lm_in, (crop.astype(np.float32) / 255.0)[np.newaxis])
        self._lm.invoke()
        pts = self._lm.get_tensor(self._lm_points)[0].reshape(21, 3)    # crop pixels
        presence = float(self._lm.get_tensor(self._lm_presence)[0, 0])   # already 0..1
        inv = cv2.invertAffineTransform(m)
        xy = np.hstack([pts[:, :2], np.ones((21, 1))]) @ inv.T          # back to frame
        return np.hstack([xy, pts[:, 2:3]]), presence