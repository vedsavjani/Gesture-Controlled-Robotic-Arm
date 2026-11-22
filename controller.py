"""Gestures -> 4 servo angles (base, shoulder, elbow, gripper), in degrees.

Each joint is a counter that gestures push up or down:
    new angle = old angle +/- speed * dt        (dt = time since the last frame)
Speed comes from hand distance: far hand (small palm) = fast, near hand (big palm) = slow.

Rules:
  left/right, shoulder_up/down, elbow_up/down
            the joint moves while the gesture is held (starts after the 0.2 s debounce,
            stops after STOP_FRAMES frames of anything else, so a one-frame blip doesn't stutter)
  grip      toggles the claw open/closed, once per new OK sign
  hold      nothing moves
  home      all joints glide back to HOME while the fist is held
  none / no hand   nothing moves (never moves on its own)
All angles are clamped to config.LIMITS. All numbers live in config.py.
"""
import config
from gestures import Debouncer

MOVES = {                      # gesture: (joint, direction)
    "left": ("base", -1),
    "right": ("base", +1),
    "shoulder_up": ("shoulder", +1),
    "shoulder_down": ("shoulder", -1),
    "elbow_up": ("elbow", +1),
    "elbow_down": ("elbow", -1),
}


def _clamp(value, low, high):
    return max(low, min(value, high))


class ArmController:
    def __init__(self):
        self.angles = dict(config.HOME)
        self.gripper_closed = False
        self.active = None              # gesture currently moving a joint, or None
        self.speed = 0.0                # deg/s used this frame (for display)
        self._debounce = Debouncer()
        self._stable_prev = "none"
        self._other = 0                 # consecutive frames that don't match self.active
        self._palm = None               # smoothed palm size (px)
        self._last_t = None

    def _speed_from_palm(self):
        if self._palm is None:
            return config.SPEED_SLOW
        frac = (self._palm - config.PALM_FAR) / (config.PALM_NEAR - config.PALM_FAR)
        frac = _clamp(frac, 0.0, 1.0)              # 0 = far, 1 = near
        return config.SPEED_FAST - frac * (config.SPEED_FAST - config.SPEED_SLOW)

    def update(self, gesture, palm_px, now):
        """gesture: raw gesture name for this frame ("none" if no hand).
        palm_px: palm size in pixels, or None if no hand. now: time.time().
        Returns (base, shoulder, elbow, gripper) in degrees."""
        dt = 0.0 if self._last_t is None else min(now - self._last_t, 0.2)   # cap after a stall
        self._last_t = now

        if palm_px is not None:                    # smooth the palm size (exponential moving average)
            a = config.PALM_SMOOTHING
            self._palm = palm_px if self._palm is None else a * palm_px + (1 - a) * self._palm

        stable = self._debounce.update(gesture)

        # Claw: toggle once when a new OK sign becomes stable
        if stable == "grip" and self._stable_prev != "grip":
            self.gripper_closed = not self.gripper_closed

        # Start a motion once its gesture is stable
        if stable in MOVES and stable != self.active:
            self.active, self._other = stable, 0

        # Stop it quickly once the raw gesture no longer matches
        if self.active is not None:
            self._other = self._other + 1 if gesture != self.active else 0
            if self._other >= config.STOP_FRAMES:
                self.active = None

        self.speed = 0.0
        if self.active is not None:
            joint, direction = MOVES[self.active]
            self.speed = self._speed_from_palm()
            low, high = config.LIMITS[joint]
            self.angles[joint] = _clamp(self.angles[joint] + direction * self.speed * dt, low, high)
        elif stable == "home":                     # glide every joint toward home
            step = config.HOME_SPEED * dt
            for joint in config.JOINTS:
                diff = config.HOME[joint] - self.angles[joint]
                self.angles[joint] += _clamp(diff, -step, step)
            self.speed = config.HOME_SPEED

        self._stable_prev = stable
        gripper = config.GRIPPER_CLOSED if self.gripper_closed else config.GRIPPER_OPEN
        return (self.angles["base"], self.angles["shoulder"], self.angles["elbow"], gripper)