"""Hand points -> gesture name. Rule-based (which fingers are up), no training data.

Works for either hand, mirrored or not: every rule compares distances, never left/right.

Gestures:
  hold           open palm (5 fingers)          arm stays where it is
  home           fist                           arm returns to its start pose
  grip           OK sign: thumb tip on index tip, other 3 fingers up   toggle the claw
  left           1: index only                  base turns left
  right          2: index + middle              base turns right
  shoulder_up    3: index + middle + ring       shoulder up
  shoulder_down  4: four fingers, thumb folded  shoulder down
  elbow_up       thumb only (thumbs up)         elbow up
  elbow_down     "call me": pinky up (thumb out)  elbow down
  none           anything else / unclear
"""
import numpy as np

# Landmark indices (0 = wrist). Each finger: base joint (MCP), middle joint (PIP), tip.
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, MIDDLE_MCP = 5, 9
FINGERS = {             # name: (PIP, TIP)
    "index": (6, 8),
    "middle": (10, 12),
    "ring": (14, 16),
    "pinky": (18, 20),
}

# Thresholds, as fractions of palm size (wrist -> middle-finger base), so they work at any distance.
FINGER_UP = 1.1       # finger up if its tip is >= 1.1x farther from the wrist than its middle joint
# Thumb out if its tip is far enough from the index-finger base. The threshold depends on the
# other fingers. Measured on the board, Oct 31:
#   fingers up:   "4" (thumb folded) 0.28-0.52   vs  open palm 0.64-0.98
#   fingers down: fist 0.08-0.66                 vs  thumbs-up 0.83-1.07
THUMB_OUT_OPEN = 0.58     # when 3+ fingers are up  (open palm vs "4")
THUMB_OUT_CLOSED = 0.75   # when fewer are up       (fist vs thumbs-up)
PINCH = 0.35              # pinch if thumb tip and index tip are <= 0.35 palm sizes apart (seen: 0.13-0.28)


def _dist(pts, a, b):
    return float(np.linalg.norm(pts[a, :2] - pts[b, :2]))


def finger_states(pts):
    """Returns (states, measures).
    states: dict thumb/index/middle/ring/pinky -> True if up.
    measures: the raw ratios behind the decision (printed by gesture_test.py, for tuning)."""
    palm = max(_dist(pts, WRIST, MIDDLE_MCP), 1e-6)
    states, measures = {}, {}
    for name, (pip, tip) in FINGERS.items():
        ratio = _dist(pts, WRIST, tip) / max(_dist(pts, WRIST, pip), 1e-6)
        states[name] = ratio >= FINGER_UP
        measures[name] = ratio
    thumb = _dist(pts, THUMB_TIP, INDEX_MCP) / palm
    fingers_up = sum(states[f] for f in FINGERS)
    states["thumb"] = thumb >= (THUMB_OUT_OPEN if fingers_up >= 3 else THUMB_OUT_CLOSED)
    measures["thumb"] = thumb
    measures["pinch"] = _dist(pts, THUMB_TIP, FINGERS["index"][1]) / palm
    measures["palm_px"] = palm          # palm size in pixels: bigger = hand closer (used for speed)
    return states, measures


def classify(pts):
    """21x3 points -> (gesture name, states, measures)."""
    s, m = finger_states(pts)
    four = (s["index"], s["middle"], s["ring"], s["pinky"])

    # Pinch only counts as the OK sign (middle, ring, pinky up): in a fist the thumb
    # also rests on the index finger, so a bare thumb-index distance check would misfire.
    if m["pinch"] <= PINCH and s["middle"] and s["ring"] and s["pinky"]:
        g = "grip"
    elif four == (True, True, True, True):
        g = "hold" if s["thumb"] else "shoulder_down"
    elif four == (False, False, False, False):
        g = "elbow_up" if s["thumb"] else "home"
    elif four == (True, False, False, False):
        g = "left"                    # thumb ignored: "1" with or without thumb
    elif four == (True, True, False, False):
        g = "right"
    elif four == (True, True, True, False):
        g = "shoulder_up"
    elif four == (False, False, False, True):
        g = "elbow_down"              # pinky up alone = "call me"; thumb ignored (measured 0.49-0.87, unreliable)
    else:
        g = "none"
    return g, s, m


class Debouncer:
    """A gesture only counts once it has been seen for `frames` frames in a row
    (~0.2 s at 18 FPS), so passing through '1' on the way to '2' doesn't fire 'left'."""

    def __init__(self, frames=4):
        self.frames = frames
        self.stable = "none"
        self._candidate, self._count = "none", 0

    def update(self, gesture):
        if gesture == self._candidate:
            self._count += 1
        else:
            self._candidate, self._count = gesture, 1
        if self._count >= self.frames:
            self.stable = self._candidate
        return self.stable

    def reset(self):
        self.stable = "none"
        self._candidate, self._count = "none", 0