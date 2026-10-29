"""
Stage 2: run the palm detector on ONE photo and draw what it finds.

Run (from ~/gesture-arm, with venv-tflite active):
    python palm_test.py hand.jpg
Output: prints the best score, saves palm_out.jpg with the box + 7 keypoints drawn.
"""
import sys

import cv2
import numpy as np
from ai_edge_litert.interpreter import Interpreter

IMG_PATH = sys.argv[1] if len(sys.argv) > 1 else "hand.jpg"
SIZE = 192            # palm detector input is 192x192
SCORE_THRESH = 0.5    # MediaPipe's own threshold for "this is a palm"


# ---------- 1. Anchors: the 2016 fixed reference positions ----------
# Fine 24x24 grid (stride 8) with 2 anchors per cell  -> 1152
# Coarse 12x12 grid (stride 16) with 6 anchors per cell -> 864
def make_anchors():
    anchors = []
    for stride, per_cell in ((8, 2), (16, 6)):
        grid = SIZE // stride
        for y in range(grid):
            for x in range(grid):
                for _ in range(per_cell):
                    anchors.append(((x + 0.5) / grid, (y + 0.5) / grid))
    return np.array(anchors, dtype=np.float32)          # shape (2016, 2), values 0..1


ANCHORS = make_anchors()


# ---------- 2. Letterbox: fit the photo into 192x192 without stretching ----------
def letterbox(img):
    h, w = img.shape[:2]
    scale = SIZE / max(h, w)
    nw, nh = int(round(w * scale)), int(round(h * scale))
    resized = cv2.resize(img, (nw, nh))
    pad_x, pad_y = (SIZE - nw) // 2, (SIZE - nh) // 2
    canvas = np.zeros((SIZE, SIZE, 3), dtype=np.uint8)   # black padding
    canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = resized
    return canvas, scale, pad_x, pad_y


def to_original(nx, ny, scale, pad_x, pad_y):
    """Model coords (0..1 inside the 192 square) -> pixel coords in the original photo."""
    return (nx * SIZE - pad_x) / scale, (ny * SIZE - pad_y) / scale


# ---------- 3. Run the model ----------
def run_detector(interp, rgb192, value_range):
    x = rgb192.astype(np.float32) / 255.0                # 0..1
    if value_range == "-1..1":
        x = x * 2.0 - 1.0
    inp = interp.get_input_details()[0]
    interp.set_tensor(inp["index"], x[np.newaxis])       # add batch dimension -> (1,192,192,3)
    interp.invoke()
    out = {tuple(d["shape"]): d["index"] for d in interp.get_output_details()}
    raw_boxes = interp.get_tensor(out[(1, 2016, 18)])[0]   # (2016, 18)
    raw_scores = interp.get_tensor(out[(1, 2016, 1)])[0, :, 0]
    scores = 1 / (1 + np.exp(-np.clip(raw_scores, -100, 100)))   # sigmoid -> 0..1
    return raw_boxes, scores


# ---------- 4. Decode one candidate: adjustment + its anchor ----------
def decode(raw, anchor):
    ax, ay = anchor
    cx = raw[0] / SIZE + ax
    cy = raw[1] / SIZE + ay
    w = raw[2] / SIZE
    h = raw[3] / SIZE
    kps = [(raw[4 + 2 * k] / SIZE + ax, raw[5 + 2 * k] / SIZE + ay) for k in range(7)]
    return cx, cy, w, h, kps


# ---------- main ----------
img = cv2.imread(IMG_PATH)
if img is None:
    sys.exit(f"Could not read {IMG_PATH}")
boxed, scale, pad_x, pad_y = letterbox(img)
rgb = cv2.cvtColor(boxed, cv2.COLOR_BGR2RGB)

interp = Interpreter(model_path="models/hand_detector.tflite", num_threads=4)
interp.allocate_tensors()

# We're not sure which input scaling this model expects, so run BOTH and
# save a separate picture for each. The picture decides, not the score.
stem = IMG_PATH.rsplit(".", 1)[0]
for value_range, tag in (("0..1", "01"), ("-1..1", "11")):
    raw_boxes, scores = run_detector(interp, rgb, value_range)
    i = int(np.argmax(scores))
    score = scores[i]
    cx, cy, w, h, kps = decode(raw_boxes[i], ANCHORS[i])
    x1, y1 = to_original(cx - w / 2, cy - h / 2, scale, pad_x, pad_y)
    x2, y2 = to_original(cx + w / 2, cy + h / 2, scale, pad_x, pad_y)

    print(f"\ninput {value_range}: best score {score:.3f}  "
          f"(candidates above {SCORE_THRESH}: {(scores > SCORE_THRESH).sum()})")
    print(f"  box in pixels: ({x1:.0f}, {y1:.0f}) to ({x2:.0f}, {y2:.0f})   "
          f"[photo is {img.shape[1]}x{img.shape[0]}]")

    out = img.copy()
    cv2.rectangle(out, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
    for k, (kx, ky) in enumerate(kps):
        px, py = to_original(kx, ky, scale, pad_x, pad_y)
        cv2.circle(out, (int(px), int(py)), 4, (0, 0, 255), -1)
        cv2.putText(out, str(k), (int(px) + 5, int(py) - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.putText(out, f"{value_range}  score {score:.2f}", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    name = f"{stem}_out_{tag}.jpg"
    cv2.imwrite(name, out)
    print(f"  saved {name}")