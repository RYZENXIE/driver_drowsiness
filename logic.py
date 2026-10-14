"""Detection logic for the Driver Drowsiness Detection and Alert System.

This file has NO camera or sound dependencies, so it can be tested anywhere.

It turns per-frame measurements (EAR, MAR, head tilt) into an alert level:
    0 = awake
    1 = caution   (short beep)
    2 = warning   (loud siren)
    3 = emergency (loud siren + red alert, logged)
"""
import math
from collections import deque
from dataclasses import dataclass, field
from statistics import median
from typing import Deque, Optional, Sequence, Tuple

Point = Tuple[float, float]

# Face Mesh landmark indices: [P1, P2, P3, P4, P5, P6]
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
MOUTH_TOP, MOUTH_BOTTOM, MOUTH_LEFT, MOUTH_RIGHT = 13, 14, 78, 308
EYE_OUTER_RIGHT, EYE_OUTER_LEFT = 33, 263   # used for head roll
FOREHEAD, CHIN, CHEEK_LEFT, CHEEK_RIGHT = 10, 152, 234, 454  # used for nod


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def eye_aspect_ratio(p: Sequence[Point]) -> float:
    """EAR = (|P2-P6| + |P3-P5|) / (2 |P1-P4|). Low value = closed eye."""
    return (dist(p[1], p[5]) + dist(p[2], p[4])) / (2.0 * max(dist(p[0], p[3]), 1e-6))


def mouth_aspect_ratio(top: Point, bottom: Point, left: Point, right: Point) -> float:
    """MAR = mouth opening / mouth width. High value = yawning."""
    return dist(top, bottom) / max(dist(left, right), 1e-6)


def head_roll_degrees(eye_right_outer: Point, eye_left_outer: Point) -> float:
    """Sideways head tilt in degrees (0 = head upright)."""
    return math.degrees(math.atan2(eye_left_outer[1] - eye_right_outer[1],
                                   eye_left_outer[0] - eye_right_outer[0]))


def pitch_ratio(forehead: Point, chin: Point, cheek_l: Point, cheek_r: Point) -> float:
    """Face height / face width. Changes when the head nods forward or back."""
    return dist(forehead, chin) / max(dist(cheek_l, cheek_r), 1e-6)


@dataclass
class Metrics:
    ear: float
    mar: float
    roll: float
    pitch: float


@dataclass
class Config:
    # eyes
    ear_default: float = 0.21      # used until calibration finishes
    ear_ratio: float = 0.75        # threshold = driver's open-eye EAR * this
    closed_caution: float = 1.0    # seconds eyes closed -> level 1
    closed_warning: float = 2.0    # -> level 2
    closed_emergency: float = 4.0  # -> level 3
    # yawning
    mar_threshold: float = 0.5
    yawn_seconds: float = 1.5      # mouth open this long = one yawn
    yawns_for_caution: int = 2     # yawns inside the window -> level 1
    yawn_window: float = 120.0
    # head
    roll_limit: float = 25.0       # degrees
    pitch_dev: float = 0.18        # 18 % change from the calibrated value
    head_warning: float = 3.0      # seconds head off-position -> level 2
    head_emergency: float = 6.0    # -> level 3
    # face missing
    no_face_seconds: float = 3.0   # -> level 3
    # calibration
    calib_frames: int = 45


@dataclass
class Result:
    level: int
    status: str
    closed_for: float = 0.0
    head_off_for: float = 0.0
    yawns: int = 0
    calibrated: bool = False


STATUS = {
    0: "AWAKE",
    1: "CAUTION - stay alert",
    2: "WARNING - WAKE UP!",
    3: "EMERGENCY - DRIVER NOT RESPONDING!",
}


@dataclass
class Monitor:
    cfg: Config = field(default_factory=Config)
    start_time: float = 0.0

    def __post_init__(self) -> None:
        self.ear_threshold = self.cfg.ear_default
        self.pitch_base: Optional[float] = None
        self.calibrated = False
        self._calib_ear = []
        self._calib_pitch = []
        self._eyes_closed_since: Optional[float] = None
        self._head_off_since: Optional[float] = None
        self._yawn_since: Optional[float] = None
        self._yawn_counted = False
        self._yawn_times: Deque[float] = deque()
        self._last_face = self.start_time

    def update(self, m: Optional[Metrics], now: float) -> Result:
        """Call once per frame. m = None when no face was found."""
        cfg = self.cfg

        if m is None:
            self._eyes_closed_since = None
            self._head_off_since = None
            self._yawn_since = None
            if now - self._last_face >= cfg.no_face_seconds:
                return Result(3, "NO DRIVER FACE - EMERGENCY!", calibrated=self.calibrated)
            return Result(0, "Looking for face...", calibrated=self.calibrated)

        self._last_face = now

        if not self.calibrated:
            self._calib_ear.append(m.ear)
            self._calib_pitch.append(m.pitch)
            if len(self._calib_ear) >= cfg.calib_frames:
                base = median(self._calib_ear)
                self.ear_threshold = max(0.12, min(0.25, base * cfg.ear_ratio))
                self.pitch_base = median(self._calib_pitch)
                self.calibrated = True
            return Result(0, "Calibrating - eyes open, look ahead", calibrated=False)

        # --- eyes ---
        if m.ear < self.ear_threshold:
            if self._eyes_closed_since is None:
                self._eyes_closed_since = now
            closed_for = now - self._eyes_closed_since
        else:
            self._eyes_closed_since = None
            closed_for = 0.0

        # --- head position ---
        pitch_off = abs(m.pitch / self.pitch_base - 1.0) > cfg.pitch_dev
        head_off = abs(m.roll) > cfg.roll_limit or pitch_off
        if head_off:
            if self._head_off_since is None:
                self._head_off_since = now
            head_off_for = now - self._head_off_since
        else:
            self._head_off_since = None
            head_off_for = 0.0

        # --- yawning ---
        if m.mar > cfg.mar_threshold:
            if self._yawn_since is None:
                self._yawn_since = now
            if now - self._yawn_since >= cfg.yawn_seconds and not self._yawn_counted:
                self._yawn_times.append(now)
                self._yawn_counted = True
        else:
            self._yawn_since = None
            self._yawn_counted = False
        while self._yawn_times and now - self._yawn_times[0] > cfg.yawn_window:
            self._yawn_times.popleft()

        # --- decide the level ---
        level = 0
        if len(self._yawn_times) >= cfg.yawns_for_caution:
            level = max(level, 1)
        if closed_for >= cfg.closed_caution:
            level = max(level, 1)
        if closed_for >= cfg.closed_warning:
            level = max(level, 2)
        if head_off_for >= cfg.head_warning:
            level = max(level, 2)
        if (closed_for >= cfg.closed_emergency
                or head_off_for >= cfg.head_emergency
                or (closed_for >= cfg.closed_warning and head_off_for >= 1.0)):
            level = 3

        return Result(level, STATUS[level], closed_for, head_off_for,
                      len(self._yawn_times), True)
