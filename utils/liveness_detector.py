import cv2
import numpy as np
 
try:
    import mediapipe as mp
except ImportError:
    mp = None

eye_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades +
    "haarcascade_eye.xml"
)

face_mesh = None
if mp is not None and hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )
else:
    mp = None

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

profile_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_profileface.xml"
)

def detect_liveness(frame):

    gray = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    eyes = eye_cascade.detectMultiScale(gray)

    if len(eyes) >= 2:
        return True, "Eyes Detected"

    return False, "Blink / Open Eyes"


def _distance(a, b):
    return float(np.linalg.norm(a - b))


def analyze_liveness_actions(frame):
    if face_mesh is None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        eyes = eye_cascade.detectMultiScale(gray)
        front_faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
        right_profiles = profile_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
        left_profiles = profile_cascade.detectMultiScale(cv2.flip(gray, 1), scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))

        if len(front_faces) == 0 and len(right_profiles) == 0 and len(left_profiles) == 0:
            return {
                "status": "no_face",
                "message": "No face detected",
                "eyes_open": False,
                "head_direction": "unknown",
                "ear": 0.0,
            }

        direction = "center"
        if len(left_profiles) > 0:
            direction = "left"
        elif len(right_profiles) > 0:
            direction = "right"

        eyes_open = len(eyes) >= 2
        return {
            "status": "ok",
            "message": "Face detected (OpenCV fallback mode)",
            "eyes_open": bool(eyes_open),
            "head_direction": direction,
            "ear": 0.3 if eyes_open else 0.1,
        }

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = face_mesh.process(rgb)

    if not result.multi_face_landmarks:
        return {
            "status": "no_face",
            "message": "No face detected",
            "eyes_open": False,
            "head_direction": "unknown",
            "ear": 0.0,
        }

    h, w, _ = frame.shape
    landmarks = result.multi_face_landmarks[0].landmark

    def pt(i):
        return np.array([landmarks[i].x * w, landmarks[i].y * h], dtype=np.float32)

    left = [33, 160, 158, 133, 153, 144]
    right = [362, 385, 387, 263, 373, 380]

    left_ear = (_distance(pt(left[1]), pt(left[5])) + _distance(pt(left[2]), pt(left[4]))) / max(2.0 * _distance(pt(left[0]), pt(left[3])), 1.0)
    right_ear = (_distance(pt(right[1]), pt(right[5])) + _distance(pt(right[2]), pt(right[4]))) / max(2.0 * _distance(pt(right[0]), pt(right[3])), 1.0)
    ear = (left_ear + right_ear) / 2.0
    eyes_open = ear > 0.22

    left_eye_corner = pt(33)
    right_eye_corner = pt(263)
    nose_tip = pt(1)
    eye_mid_x = (left_eye_corner[0] + right_eye_corner[0]) / 2.0
    eye_width = max(abs(right_eye_corner[0] - left_eye_corner[0]), 1.0)
    yaw_ratio = (nose_tip[0] - eye_mid_x) / eye_width

    if yaw_ratio < -0.10:
        direction = "left"
    elif yaw_ratio > 0.10:
        direction = "right"
    else:
        direction = "center"

    return {
        "status": "ok",
        "message": "Face detected",
        "eyes_open": bool(eyes_open),
        "head_direction": direction,
        "ear": round(float(ear), 3),
    }
