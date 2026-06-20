import cv2
import numpy as np

try:
    import mediapipe as mp
except ImportError:
    mp = None

face_mesh = None
if mp is not None and hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=5,
        refine_landmarks=False,
        min_detection_confidence=0.25,
    )

face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)
profile_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_profileface.xml"
)

# Below this width, faces tend to be too small for Haar/FaceMesh to pick up
# reliably with fixed-pixel thresholds (e.g. person standing far from a
# desk-mounted scanner camera). We upscale before detecting, then scale
# the resulting box back down to original-frame coordinates.
MIN_FRAME_WIDTH_FOR_FULL_RES = 480


def _mesh_detect(frame):
    """MediaPipe FaceMesh detection — most accurate, but weak past ~45 deg yaw."""
    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = face_mesh.process(rgb)

    detected = []
    if result.multi_face_landmarks:
        for face_landmarks in result.multi_face_landmarks:
            xs = [lm.x * w for lm in face_landmarks.landmark]
            ys = [lm.y * h for lm in face_landmarks.landmark]
            x_min, x_max = int(min(xs)), int(max(xs))
            y_min, y_max = int(min(ys)), int(max(ys))

            # Add some padding to capture the forehead and chin properly
            pad_x = int((x_max - x_min) * 0.15)
            pad_y = int((y_max - y_min) * 0.15)

            x = max(0, x_min - pad_x)
            y = max(0, y_min - pad_y)
            width = min(w - x, (x_max - x_min) + 2 * pad_x)
            height = min(h - y, (y_max - y_min) + 2 * pad_y)

            detected.append([x, y, width, height])

    return detected


def _haar_detect(frame, min_size):
    """
    Haar cascade fallback — catches turned/profile/small faces that
    FaceMesh misses. Tries frontal, right-profile, and left-profile (via
    horizontal flip). min_size scales with frame resolution rather than
    being a fixed pixel count, so it still works on smaller frames.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)  # helps in dim/uneven lighting
    h, w = gray.shape[:2]
    candidates = []

    frontal = face_cascade.detectMultiScale(
        gray, scaleFactor=1.05, minNeighbors=4, minSize=min_size
    )
    for (x, y, fw, fh) in frontal:
        candidates.append([x, y, fw, fh])

    right_profile = profile_cascade.detectMultiScale(
        gray, scaleFactor=1.05, minNeighbors=4, minSize=min_size
    )
    for (x, y, fw, fh) in right_profile:
        candidates.append([x, y, fw, fh])

    flipped = cv2.flip(gray, 1)
    left_profile = profile_cascade.detectMultiScale(
        flipped, scaleFactor=1.05, minNeighbors=4, minSize=min_size
    )
    for (x, y, fw, fh) in left_profile:
        # Un-flip the x coordinate back to original frame space
        orig_x = w - x - fw
        candidates.append([orig_x, y, fw, fh])

    return candidates


def detect_faces(frame):
    h, w = frame.shape[:2]

    # Upscale small frames before detection so fixed-pixel-size cascades
    # still have enough resolution to find a face, then scale results back.
    scale = 1.0
    work_frame = frame
    if w < MIN_FRAME_WIDTH_FOR_FULL_RES:
        scale = MIN_FRAME_WIDTH_FOR_FULL_RES / float(w)
        work_frame = cv2.resize(frame, (int(w * scale), int(h * scale)))

    detected = []
    if face_mesh is not None:
        detected = _mesh_detect(work_frame)

    if not detected:
        # min_size scales with the (possibly upscaled) frame's own width,
        # so a face taking up ~12% of frame width is still caught.
        ww = work_frame.shape[1]
        min_dim = max(40, int(ww * 0.12))
        detected = _haar_detect(work_frame, (min_dim, min_dim))

    if not detected:
        return np.empty((0, 4), dtype=int)

    # Largest box = most likely the real, in-frame face
    detected.sort(key=lambda box: box[2] * box[3], reverse=True)

    if scale != 1.0:
        detected = [
            [int(x / scale), int(y / scale), int(bw / scale), int(bh / scale)]
            for (x, y, bw, bh) in detected
        ]

    return np.array(detected)