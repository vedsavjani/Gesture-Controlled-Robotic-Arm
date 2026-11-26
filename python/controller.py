"""Gestures -> 4 servo angles (base, shoulder, elbow, gripper), in degrees.

Each joint is a counter that gestures push up or down:
    new angle = old angle +/- speed * dt       (dt = monotonic time since the last frame)
Speed comes from hand distance: far hand (small palm) = fast, near hand (big palm) = slow.

Rules:
  left/right, shoulder_up/down, elbow_up/down
                the joint moves while the gesture is held (starts after DEBOUNCE_SEC,
                stops after STOP_FRAMES frames of anything else without re-arming on stale debounce)
    grip        toggles the claw open/closed, once per intentional OK sign (guarded against
                transient tracking drops and rapid double-toggles)
  hold      nothing moves
    home        all joints glide back to HOME while the fist is held (also stops in STOP_FRAMES)
  none / no hand   nothing moves (never moves on its own)
All angles are clamped to config.LIMITS. All numbers live in config.py.
"""
import math

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
ACTIVE_GESTURES = set(MOVES) | {"home"}


def _clamp(value, low, high):
    return max(low, min(value, high))


class ArmController:
    def __init__(self):
        self.angles = dict(config.HOME)
        self.gripper_closed = False
        self.active = None              # gesture currently moving the arm (MOVES or "home"), or None
        self.speed = 0.0                # deg/s used this frame (for display)
        self._debounce = Debouncer()
        self._stable = "none"
        self._other = 0                 # consecutive frames that don't match self.active
        self._palm_frac = None          # smoothed palm size as fraction of frame height
        self._last_t = None
        self._grip_armed = True         # requires seeing a non-grip, non-none gesture before re-toggle
        self._last_grip_t = -1e9

    @property
    def stable(self):
        return self._stable

    def sync_angles(self, base, shoulder, elbow, gripper):
        """Initialize internal angles from the MCU's current position to avoid a jump on restart."""
        for joint, val in zip(config.JOINTS, (base, shoulder, elbow)):
            low, high = config.LIMITS[joint]
            self.angles[joint] = _clamp(float(val), low, high)
        mid_grip = 0.5 * (config.GRIPPER_OPEN + config.GRIPPER_CLOSED)
        self.gripper_closed = float(gripper) >= mid_grip

    def _speed_from_palm(self):
        if self._palm_frac is None:
            return config.SPEED_SLOW
        span = config.PALM_NEAR_FRAC - config.PALM_FAR_FRAC
        frac = (self._palm_frac - config.PALM_FAR_FRAC) / span if span > 0 else 0.0
        frac = _clamp(frac, 0.0, 1.0)              # 0 = far, 1 = near
        return config.SPEED_FAST - frac * (config.SPEED_FAST - config.SPEED_SLOW)

    def update(self, gesture, palm_frac, now):
        """gesture: raw gesture name for this frame ("none" if no hand).
        palm_frac: palm size as fraction of frame height (or None if no hand).
        now: monotonic time in seconds (time.monotonic()).
        Returns (base, shoulder, elbow, gripper) in degrees."""
        if self._last_t is None:
            dt = 0.0
        else:
            dt = max(0.0, min(now - self._last_t, 0.2))  # guard against stalls and clock anomalies
        self._last_t = now

        if palm_frac is not None:
            if self._palm_frac is None or dt <= 0.0:
                self._palm_frac = palm_frac
            else:
                # Framerate-independent exponential moving average
                alpha = 1.0 - math.exp(-dt / config.PALM_TAU_SEC)
                self._palm_frac = alpha * palm_frac + (1.0 - alpha) * self._palm_frac

        stable = self._debounce.update(gesture, now)

        # Re-arm gripper only when user deliberately shows another valid gesture (not tracking loss "none")
        if stable not in ("grip", "none"):
            self._grip_armed = True

        # Claw: toggle once per intentional OK sign, with cooldown
        if stable == "grip" and self._grip_armed and (now - self._last_grip_t >= config.GRIP_COOLDOWN_SEC):
            self.gripper_closed = not self.gripper_closed
            self._grip_armed = False
            self._last_grip_t = now

        # Stop active motion quickly when raw gesture stops matching, and clear stale debounce
        # so the old stable gesture cannot re-arm on the next frame.
        if self.active is not None:
            self._other = self._other + 1 if gesture != self.active else 0
            if self._other >= config.STOP_FRAMES:
                self.active = None
                self._other = 0
                if stable == self._stable or stable in ACTIVE_GESTURES:
                    self._debounce.reset()
                    stable = "none"

        # Start a motion only when its debounced gesture is stable AND still actively shown
        if stable in ACTIVE_GESTURES and gesture == stable and stable != self.active:
            self.active = stable
            self._other = 0

        self.speed = 0.0
        if self.active in MOVES:
            joint, direction = MOVES[self.active]
            self.speed = self._speed_from_palm()
            low, high = config.LIMITS[joint]
            self.angles[joint] = _clamp(self.angles[joint] + direction * self.speed * dt, low, high)
        elif self.active == "home":         # glide every joint toward home while fist is held
            step = config.HOME_SPEED * dt
            for joint in config.JOINTS:
                diff = config.HOME[joint] - self.angles[joint]
                self.angles[joint] += _clamp(diff, -step, step)
            self.speed = config.HOME_SPEED

        self._stable = stable
        gripper = config.GRIPPER_CLOSED if self.gripper_closed else config.GRIPPER_OPEN
        return (self.angles["base"], self.angles["shoulder"], self.angles["elbow"], gripper)