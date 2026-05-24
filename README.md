<div align="center">

# AegisAI-Offline-Intelligent-Facial-Authentication-Real-Time-Liveness-Verification-System

**Biometric attendance and identity verification — fully offline, no cloud, no compromise.**

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?style=flat-square&logo=flask&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=flat-square&logo=opencv&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL--enabled-003B57?style=flat-square&logo=sqlite&logoColor=white)
![MediaPipe](https://img.shields.io/badge/MediaPipe-optional-FF6F00?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)

Live face recognition → liveness verification → automatic attendance marking.  
Zero internet. Zero cloud. Every byte stays on your machine.

</div>

---

## What This Is

OfflineFaceAuth is a **Flask-based biometric identity system** for environments where sending face data to an external API is not an option. It runs entirely on local hardware — detecting, verifying, and recognizing faces in real time using OpenCV and optionally MediaPipe, with SQLite as the persistence layer.

It is built around two distinct workflows:

- **Users** enroll through a guided 4-stage liveness capture flow before their face is stored
- **Admins** operate a live camera scanner that continuously identifies known people and marks them present

No third-party auth. No API keys. No telemetry. Just a Flask server and a camera.

---

## Feature Overview

| Area | What It Does |
|---|---|
| **Face Detection** | Haar cascade frontal face detector (OpenCV) |
| **Face Recognition** | Cosine similarity on normalized 128×128 pixel embeddings |
| **Liveness Detection** | EAR-based blink detection + yaw-ratio head direction via MediaPipe FaceMesh; OpenCV cascade fallback |
| **Enrollment Flow** | 4 staged captures: blink → left → right → straight |
| **Admin Scanner** | Continuous frame processing with `Scanning → Capturing → Captured` state flow |
| **Attendance** | Per-day present/absent snapshots with last-seen timestamps |
| **Auth** | Role-based login (admin / user), signup, password reset — Werkzeug-hashed |
| **Persistence** | SQLite with WAL mode, busy timeout, write lock retry backoff |

---

## Project Structure

```
OfflineFaceAuth/
├── app.py                    # Flask routes, session logic, frame processing
├── requirements.txt
├── database.db               # Auto-created on first run
│
├── embeddings/
│   ├── users.pkl             # name|phone → embedding vectors
│   └── trained_index.pkl     # Flat label + embedding matrix for recognition
│
├── utils/
│   ├── database.py           # SQLite layer: schema, CRUD, retry logic
│   ├── face_detector.py      # Haar cascade face detection
│   ├── face_recognizer.py    # Embedding + cosine similarity recognition
│   ├── liveness_detector.py  # EAR blink + yaw head direction detection
│   └── recognizer.py         # Public re-export of recognize / register_face
│
├── templates/
│   ├── login.html
│   ├── signup.html
│   ├── forgot_password.html
│   ├── index.html            # Admin scan portal
│   ├── register.html         # User enrollment entry
│   ├── capture_stage.html    # Per-stage camera UI
│   ├── attendance.html       # Admin attendance dashboard
│   └── captured_people.html  # Admin people directory
│
└── static/
    ├── style.css
    ├── app.js                # Admin scan loop
    ├── register.js
    └── capture_stage.js      # Staged capture + verify logic
```

---

## How It Works

### Enrollment (User)

```
Login → Enter name / place / phone
  └─ Stage 1: Blink detected via EAR < 0.22       → advance
  └─ Stage 2: Head LEFT via yaw ratio < -0.10      → advance
  └─ Stage 3: Head RIGHT via yaw ratio > 0.10      → advance
  └─ Stage 4: Face straight → extract embedding
                             → upsert DB record
                             → save to users.pkl
                             → retrain trained_index.pkl
```

Each stage is verified server-side. The client cannot skip stages.

### Recognition (Admin)

```
Camera frame (base64) → POST /process_frame
  └─ detect_faces()         Haar cascade
  └─ recognize()            cosine_similarity(query_emb, all_stored_embs)
  └─ score ≥ 0.80?
        YES → mark_present() → return { status: "captured", user, confidence }
        NO  → return { status: "capturing", user: "Unknown" }
```

Confidence threshold is 80%. Below it, the frame returns as `capturing` and scanning continues.

### Embedding Format

Faces are resized to **128×128**, flattened to **49,152-dimensional vectors**, and L2-normalized before storage. Recognition is brute-force cosine similarity across all stored embeddings — fast and dependency-light for small to medium deployments.

> **Accuracy note:** Raw pixel embeddings are sensitive to lighting, distance, and angle variation. For production-grade accuracy, drop in a deep embedding model (e.g. MobileFaceNet, ArcFace). The `register_face` / `recognize` interface is designed to be swapped without touching any other code.

---

## Setup

### 1. Clone and create environment

```bash
git clone https://github.com/your-username/OfflineFaceAuth.git
cd OfflineFaceAuth
python -m venv .venv
```

```bash
# Windows
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

MediaPipe is optional. If it fails to import, liveness detection falls back to OpenCV cascades automatically — no configuration needed.

### 3. Create embeddings directory

```bash
mkdir embeddings
```

### 4. Run

```bash
python app.py
```

On startup, `app.py` will:
1. Initialize the SQLite schema (creates `database.db`)
2. Seed default admin and user accounts
3. Load or initialize the recognition index

Visit `http://127.0.0.1:5000`

---

## Default Credentials

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| User | `user` | `user123` |

Change these before any non-local deployment.

---

## API Reference

### Auth

| Method | Route | Description |
|---|---|---|
| GET/POST | `/login` | Login with role selection |
| GET/POST | `/signup` | Create account |
| GET/POST | `/forgot-password` | Reset password by username + role |
| GET | `/logout` | Clear session |

### Admin

| Method | Route | Description |
|---|---|---|
| GET | `/admin/scan` | Live scanner portal |
| POST | `/process_frame` | Submit camera frame for recognition |
| GET | `/admin/attendance` | Today's attendance snapshot |
| GET | `/admin/people` | All registered people |

### User Enrollment

| Method | Route | Description |
|---|---|---|
| GET | `/user/register` | Registration entry form |
| POST | `/user/start-capture` | Submit name/place/phone, begin capture |
| GET | `/user/capture/<step>` | Render capture UI for step |
| POST | `/user/capture/verify` | Server-side liveness verification per step |
| POST | `/liveness_challenge` | Raw liveness analysis on a frame |
| POST | `/register` | Single-shot registration (no staged flow) |

---

## Database Schema

```sql
app_users   (id, username, password [hashed], role)
people      (id, name, place, phone [unique], embedding_key [unique], created_at)
attendance  (id, person_id, date, status, last_seen)  -- UNIQUE(person_id, date)
```

WAL journal mode and a threading `RLock` with exponential retry backoff handle concurrent write contention.

---

## Known Limitations

| Limitation | Detail |
|---|---|
| Pixel-based embeddings | Sensitive to lighting and pose. Not suitable for high-security identity verification. |
| Single embedding per person | Only the final capture stage is stored. Multiple embeddings per person would improve match stability. |
| Brute-force matching | O(n) scan over all embeddings on every frame. Degrades at scale (1000+ people). |
| Hardcoded secret key | `app.config["SECRET_KEY"]` must be replaced with an environment variable before deployment. |
| No account lockout | Repeated failed login attempts are not rate-limited. |

---

## Production Checklist

- [ ] Replace `SECRET_KEY` with `os.environ.get("SECRET_KEY")`
- [ ] Enable HTTPS and set `SESSION_COOKIE_SECURE = True`
- [ ] Add login rate-limiting (e.g. Flask-Limiter)
- [ ] Schedule periodic backups of `database.db` and `embeddings/`
- [ ] Swap pixel embeddings for a deep face model for better accuracy
- [ ] Add audit log for auth events and attendance marks
- [ ] Set `debug=False` in `app.run()`

---

## Requirements

```
opencv-python
mediapipe          # optional — fallback supported
numpy
flask
flask-cors
pillow
scikit-learn
werkzeug           # pulled in by flask
```

Python 3.9 or later recommended.

---

## License

MIT — see `LICENSE` for details.
