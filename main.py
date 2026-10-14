"""Driver Drowsiness Detection and Alert System - camera app.

Run:   python main.py              (default webcam)
       python main.py --camera 1   (another camera)
       python main.py --video test.mp4
       python main.py --mute       (no sound, for testing)
Press Q in the video window to quit.
"""
import argparse
import csv
import os
import time

import cv2
import mediapipe as mp

import logic
from logic import Config, Metrics, Monitor

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "events.csv")
MODEL_FILE = os.path.join(HERE, "face_landmarker.task")
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")


class FaceTracker:
    """Finds face landmarks. Works with both old and new mediapipe versions.

    - Old mediapipe (has mp.solutions): uses the classic Face Mesh.
    - New mediapipe (solutions removed): uses the Tasks API FaceLandmarker,
      and downloads the small model file (face_landmarker.task) once.
    Both give the same landmark numbering (468+ points), so logic.py works as is.
    """

    def __init__(self):
        self._legacy = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")
        self._last_ts = -1
        if self._legacy:
            self._mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1, refine_landmarks=True,
                min_detection_confidence=0.5, min_tracking_confidence=0.5)
        else:
            self._ensure_model()
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            options = vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=MODEL_FILE),
                running_mode=vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_tracking_confidence=0.5)
            self._landmarker = vision.FaceLandmarker.create_from_options(options)

    @staticmethod
    def _ensure_model():
        if os.path.exists(MODEL_FILE) and os.path.getsize(MODEL_FILE) > 1_000_000:
            return
        import urllib.request
        print("Downloading face model (one time, about 4 MB)...")
        try:
            urllib.request.urlretrieve(MODEL_URL, MODEL_FILE)
        except Exception as exc:
            raise SystemExit(
                f"Could not download the face model: {exc}\n"
                f"Download it manually from:\n  {MODEL_URL}\n"
                f"and save it as:\n  {MODEL_FILE}")

    def process(self, frame_bgr, now_seconds):
        """Returns the list of 468+ landmarks of the first face, or None."""
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        if self._legacy:
            res = self._mesh.process(rgb)
            return res.multi_face_landmarks[0].landmark if res.multi_face_landmarks else None
        ts = max(int(now_seconds * 1000), self._last_ts + 1)  # must keep increasing
        self._last_ts = ts
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._landmarker.detect_for_video(image, ts)
        return res.face_landmarks[0] if res.face_landmarks else None

    def close(self):
        if self._legacy:
            self._mesh.close()
        else:
            self._landmarker.close()


class AlarmPlayer:
    """Level 1 = short beep, level 2 and 3 = looping siren."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.level = 0
        self._last_beep = 0.0
        self.beep = self.siren = None
        if not enabled:
            return
        try:
            import pygame
            import sounds
            self.pygame = pygame
            sounds.ensure_sounds()
            pygame.mixer.init()
            self.beep = pygame.mixer.Sound(sounds.BEEP_FILE)
            self.siren = pygame.mixer.Sound(sounds.SIREN_FILE)
            self.siren.set_volume(1.0)
        except Exception as exc:  # no speaker, pygame missing, etc.
            print(f"[warning] Sound disabled: {exc}")
            self.enabled = False

    def update(self, level):
        if self.enabled:
            if level >= 2 and self.level < 2:
                self.siren.play(loops=-1)
            elif level < 2 and self.level >= 2:
                self.siren.stop()
            if level == 1 and time.time() - self._last_beep > 1.5:
                self.beep.play()
                self._last_beep = time.time()
        self.level = level

    def close(self):
        if self.enabled:
            self.pygame.mixer.stop()


def extract_metrics(lm, w, h):
    def P(i):
        return (lm[i].x * w, lm[i].y * h)

    left = [P(i) for i in logic.LEFT_EYE]
    right = [P(i) for i in logic.RIGHT_EYE]
    ear = (logic.eye_aspect_ratio(left) + logic.eye_aspect_ratio(right)) / 2
    mar = logic.mouth_aspect_ratio(P(logic.MOUTH_TOP), P(logic.MOUTH_BOTTOM),
                                   P(logic.MOUTH_LEFT), P(logic.MOUTH_RIGHT))
    roll = logic.head_roll_degrees(P(logic.EYE_OUTER_RIGHT), P(logic.EYE_OUTER_LEFT))
    pitch = logic.pitch_ratio(P(logic.FOREHEAD), P(logic.CHIN),
                              P(logic.CHEEK_LEFT), P(logic.CHEEK_RIGHT))
    return Metrics(ear, mar, roll, pitch), left + right


def log_event(writer, now, level, status):
    writer.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), f"{now:.1f}", level, status])


def main():
    ap = argparse.ArgumentParser(description="Driver drowsiness detection")
    ap.add_argument("--camera", type=int, default=0, help="camera index")
    ap.add_argument("--video", help="use a video file instead of a camera")
    ap.add_argument("--mute", action="store_true", help="disable sound")
    ap.add_argument("--no-window", action="store_true", help="do not show video")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.video if args.video else args.camera)
    if not cap.isOpened():
        raise SystemExit("Could not open the camera/video. Check --camera or --video.")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    def clock():
        if args.video:
            return cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
        return time.time()

    tracker = FaceTracker()
    monitor = Monitor(Config(), start_time=clock())
    alarm = AlarmPlayer(enabled=not args.mute)

    new_file = not os.path.exists(LOG_FILE)
    log_f = open(LOG_FILE, "a", newline="")
    log = csv.writer(log_f)
    if new_file:
        log.writerow(["wall_time", "seconds", "level", "status"])

    last_level, prev_t, fps = 0, time.time(), 0.0
    print("Running. Press Q in the window to quit.")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            h, w = frame.shape[:2]
            now = clock()
            landmarks = tracker.process(frame, now)

            metrics, eye_pts = None, []
            if landmarks is not None:
                metrics, eye_pts = extract_metrics(landmarks, w, h)

            result = monitor.update(metrics, now)
            alarm.update(result.level)

            if result.level != last_level:
                log_event(log, now, result.level, result.status)
                log_f.flush()
                print(f"[level {result.level}] {result.status}")
                last_level = result.level

            if not args.no_window:
                for x, y in eye_pts:
                    cv2.circle(frame, (int(x), int(y)), 2, (0, 255, 0), -1)
                color = [(0, 200, 0), (0, 200, 255), (0, 120, 255), (0, 0, 255)][result.level]
                if result.level >= 2:
                    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), (0, 0, 255), 8)
                cv2.putText(frame, result.status, (15, 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                if metrics:
                    info = (f"EAR {metrics.ear:.2f} (thr {monitor.ear_threshold:.2f})  "
                            f"MAR {metrics.mar:.2f}  roll {metrics.roll:.0f}")
                    cv2.putText(frame, info, (15, h - 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    cv2.putText(frame, f"eyes closed {result.closed_for:.1f}s  "
                                       f"yawns {result.yawns}  FPS {fps:.0f}",
                                (15, h - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                (255, 255, 255), 1)
                cv2.imshow("Driver Monitor", frame)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                    break

            t = time.time()
            fps = 0.9 * fps + 0.1 / max(t - prev_t, 1e-6)
            prev_t = t
    finally:
        alarm.close()
        tracker.close()
        cap.release()
        log_f.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()