import base64
import csv
import io
import sqlite3
from datetime import date, datetime
from functools import wraps

import cv2
import numpy as np
from flask import Flask, jsonify, redirect, render_template, request, session, url_for, Response

from utils.database import (
    create_app_user,
    create_person,
    ensure_default_users,
    get_attendance_snapshot,
    get_attendance_export_rows,
    list_people,
    get_person_by_embedding_key,
    get_person_by_id,
    init_db,
    mark_present,
    upsert_person_by_phone,
    update_app_user_password,
    validate_login,
    delete_person_by_id,
    update_person_details,
    delete_attendance_by_id,
    update_attendance_status_by_id,
    clear_attendance_for_date,
)
from utils.face_detector import detect_faces
from utils.recognizer import recognize, register_face, register_face_multi, is_model_training, train_model, remove_face_class, rename_face_class
from utils.liveness_detector import analyze_liveness_actions

app = Flask(__name__)
app.config["SECRET_KEY"] = "offline-face-auth-secret"
CAPTURE_STEPS = ["left", "right", "final"]


def normalize_capture_stage(stage):
    if stage == "blink":
        return CAPTURE_STEPS[0]
    if stage in CAPTURE_STEPS:
        return stage
    return CAPTURE_STEPS[0]


def decode_base64_image(data_uri: str):
    encoded = data_uri.split(",", 1)[1]
    img = np.frombuffer(base64.b64decode(encoded), np.uint8)
    return cv2.imdecode(img, cv2.IMREAD_COLOR)


def login_required(role=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return redirect(url_for("home"))
            return func(*args, **kwargs)

        return wrapper

    return decorator


@app.route("/")
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if session.get("role") == "admin":
        return redirect(url_for("admin_scan"))
    return redirect(url_for("user_register"))


@app.route("/login", methods=["GET", "POST"])
def login():
    role = request.args.get("role", "admin")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "admin")
        user = validate_login(username, password, selected_role)
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("admin_scan" if user["role"] == "admin" else "user_register"))
        return render_template("login.html", role=selected_role, error="Invalid credentials")
    return render_template("login.html", role=role, error=None)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    role = request.args.get("role", "user")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        selected_role = request.form.get("role", "user")

        if len(username) < 4 or len(password) < 8:
            return render_template(
                "signup.html",
                role=selected_role,
                error="Username must be 4+ chars and password must be 8+ chars.",
            )
        if password != confirm_password:
            return render_template("signup.html", role=selected_role, error="Passwords do not match.")

        try:
            create_app_user(username, password, selected_role)
        except sqlite3.IntegrityError:
            return render_template(
                "signup.html",
                role=selected_role,
                error="Username already exists. Try another username or login with Forgot Password.",
            )
        except sqlite3.OperationalError:
            return render_template(
                "signup.html",
                role=selected_role,
                error="Database busy. Please wait 2-3 seconds and try signup again.",
            )

        return render_template("login.html", role=selected_role, error="Account created. Please login.")

    return render_template("signup.html", role=role, error=None)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    role = request.args.get("role", "user")
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        selected_role = request.form.get("role", "user")

        if len(new_password) < 8:
            return render_template("forgot_password.html", role=selected_role, error="Password must be at least 8 characters.")
        if new_password != confirm_password:
            return render_template("forgot_password.html", role=selected_role, error="Passwords do not match.")

        changed = update_app_user_password(username, selected_role, new_password)
        if not changed:
            return render_template("forgot_password.html", role=selected_role, error="User not found for selected role.")

        return render_template("login.html", role=selected_role, error="Password reset successful. Please login.")

    return render_template("forgot_password.html", role=role, error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin/scan")
@login_required(role="admin")
def admin_scan():
    return render_template("index.html", username=session.get("username"))


@app.route("/admin/attendance")
@login_required(role="admin")
def admin_attendance():
    today_iso = date.today().isoformat()
    snapshot = get_attendance_snapshot(today_iso)
    return render_template(
        "attendance.html",
        username=session.get("username"),
        today=date.today().strftime("%d %b %Y"),
        today_iso=today_iso,
        present=snapshot["present"],
        absent=snapshot["absent"],
    )


@app.route("/admin/attendance/export")
@login_required(role="admin")
def export_attendance_csv():
    target_date = request.args.get("date", date.today().isoformat())
    rows = get_attendance_export_rows(target_date)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Place", "Phone", "Status", "Last Seen"])
    for row in rows:
        writer.writerow([row["name"], row["place"], row["phone"], row["status"], row["last_seen"]])
    session[f"attendance_exported_{target_date}"] = True
    filename = f"attendance_{target_date}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/admin/attendance/clear", methods=["POST"])
@login_required(role="admin")
def clear_attendance():
    payload = request.get_json(force=True) if request.is_json else {}
    target_date = payload.get("date", date.today().isoformat())
    if not session.get(f"attendance_exported_{target_date}"):
        return jsonify({"status": "failed", "message": "Export attendance to CSV before clearing."}), 400
    clear_attendance_for_date(target_date)
    session.pop(f"attendance_exported_{target_date}", None)
    return jsonify({"status": "ok", "message": "Attendance cleared for selected date."})


@app.route("/admin/attendance/update", methods=["POST"])
@login_required(role="admin")
def update_attendance_record():
    payload = request.get_json(force=True)
    person_id = payload.get("person_id")
    target_date = payload.get("date", date.today().isoformat())
    status = (payload.get("status") or "").strip().lower()
    if not person_id:
        return jsonify({"status": "failed", "message": "Person id is required."}), 400
    person = get_person_by_id(int(person_id))
    if not person:
        return jsonify({"status": "failed", "message": "Person not found."}), 404
    if status not in ("present", "absent"):
        return jsonify({"status": "failed", "message": "Status must be present or absent."}), 400
    update_attendance_status_by_id(int(person_id), target_date, status)
    return jsonify({"status": "ok", "message": f"Marked as {status}."})


@app.route("/admin/attendance/remove", methods=["POST"])
@login_required(role="admin")
def remove_attendance_record():
    payload = request.get_json(force=True)
    person_id = payload.get("person_id")
    target_date = payload.get("date", date.today().isoformat())
    if not person_id:
        return jsonify({"status": "failed", "message": "Person id is required."}), 400
    person = get_person_by_id(int(person_id))
    if not person:
        return jsonify({"status": "failed", "message": "Person not found."}), 404
    delete_attendance_by_id(int(person_id), target_date)
    return jsonify({"status": "ok", "message": "Attendance record removed."})


@app.route("/admin/people")
@login_required(role="admin")
def admin_people():
    people = list_people()
    return render_template("captured_people.html", username=session.get("username"), people=people)


@app.route("/admin/people/export")
@login_required(role="admin")
def export_people_csv():
    people = list_people()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Name", "Place", "Phone", "Registered At"])
    for row in people:
        writer.writerow([row["name"], row["place"], row["phone"], row["created_at"]])
    filename = f"registered_people_{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/admin/people/update", methods=["POST"])
@login_required(role="admin")
def update_person_record():
    payload = request.get_json(force=True)
    person_id = payload.get("person_id")
    new_name = (payload.get("name") or "").strip()
    new_place = (payload.get("place") or "").strip()
    new_phone = (payload.get("phone") or "").strip()
    if not person_id:
        return jsonify({"status": "failed", "message": "Person id is required."}), 400
    if not new_name or not new_place or not new_phone:
        return jsonify({"status": "failed", "message": "Name, place and phone are required."}), 400
    person = get_person_by_id(int(person_id))
    if not person:
        return jsonify({"status": "failed", "message": "Person not found."}), 404
    try:
        result = update_person_details(int(person_id), new_name, new_place, new_phone)
    except sqlite3.IntegrityError:
        return jsonify({"status": "failed", "message": "Phone number already registered."}), 400
    if not result:
        return jsonify({"status": "failed", "message": "Person not found."}), 404
    old_key, new_key = result
    if old_key != new_key:
        rename_face_class(old_key, new_key)
    return jsonify({"status": "ok", "message": "Person details updated."})


@app.route("/admin/people/remove", methods=["POST"])
@login_required(role="admin")
def remove_person_record():
    payload = request.get_json(force=True)
    person_id = payload.get("person_id")
    if not person_id:
        return jsonify({"status": "failed", "message": "Person id is required."}), 400
    person = get_person_by_id(int(person_id))
    if not person:
        return jsonify({"status": "failed", "message": "Person not found."}), 404
    embedding_key = delete_person_by_id(int(person_id))
    if embedding_key:
        remove_face_class(embedding_key)
    return jsonify({"status": "ok", "message": "Person deleted and model retraining scheduled."})


@app.route("/attendance")
def redirect_attendance():
    return redirect(url_for("admin_attendance"))


@app.route("/people")
def redirect_people():
    return redirect(url_for("admin_people"))


@app.route("/scan")
def redirect_scan():
    return redirect(url_for("admin_scan"))


@app.route("/admin/captured_people")
def redirect_captured_people():
    return redirect(url_for("admin_people"))


@app.route("/user/register")
@login_required(role="user")
def user_register():
    return render_template("register.html", username=session.get("username"), error=None)


@app.route("/user/start-capture", methods=["POST"])
@login_required(role="user")
def start_capture():
    name = request.form.get("name", "").strip()
    place = request.form.get("place", "").strip()
    phone = request.form.get("phone", "").strip()

    if not name or not place or not phone:
        return render_template("register.html", username=session.get("username"), error="Name, place and phone are required.")

    session["pending_registration"] = {"name": name, "place": place, "phone": phone}
    session["capture_stage"] = CAPTURE_STEPS[0]
    return redirect(url_for("capture_stage", step=CAPTURE_STEPS[0]))


@app.route("/user/capture/<step>")
@login_required(role="user")
def capture_stage(step):
    pending = session.get("pending_registration")
    active_stage = normalize_capture_stage(session.get("capture_stage"))
    session["capture_stage"] = active_stage
    if not pending:
        return redirect(url_for("user_register"))
    if step not in CAPTURE_STEPS:
        return redirect(url_for("capture_stage", step=active_stage))
    if step != active_stage:
        return redirect(url_for("capture_stage", step=active_stage))

    prompts = {
        "left": "Stage 1/3: Turn your head slowly to the LEFT.",
        "right": "Stage 2/3: Turn your head slowly to the RIGHT.",
        "final": "Stage 3/3: Look straight ahead at the camera.",
    }
    return render_template(
        "capture_stage.html",
        username=session.get("username"),
        step=step,
        prompt=prompts[step],
        stages=CAPTURE_STEPS,
    )


@app.route("/user/capture/verify", methods=["POST"])
@login_required(role="user")
def verify_capture_stage():
    payload = request.get_json(force=True)
    step = payload.get("step")
    image = payload.get("image", "")
    active_stage = normalize_capture_stage(session.get("capture_stage"))
    session["capture_stage"] = active_stage

    if not step or not image or step != active_stage:
        return jsonify({"status": "failed", "message": "Invalid stage request."}), 400

    frame = decode_base64_image(image)
    analysis = analyze_liveness_actions(frame)
    print(f"[BiometricVerify] step={step} | eyes_open={analysis.get('eyes_open')} | ear={analysis.get('ear')} | head_direction={analysis.get('head_direction')} | yaw_ratio={analysis.get('yaw_ratio', 'N/A')}")
    if analysis["status"] != "ok":
        return jsonify({"status": "failed", "message": "Face not detected clearly. Retry this stage."}), 400

    valid = False
    if step == "left":
        valid = analysis.get("head_direction") == "left"
    elif step == "right":
        valid = analysis.get("head_direction") == "right"
    elif step == "final":
        valid = analysis.get("head_direction") == "center" and analysis.get("eyes_open", True)

    if not valid:
        messages = {
            "left": "Please turn head LEFT while capturing.",
            "right": "Please turn head RIGHT while capturing.",
            "final": "Please keep face centered and retry.",
        }
        return jsonify({"status": "failed", "message": messages[step]}), 400

    # Save cropped face to temp directory for training
    faces = detect_faces(frame)
    if len(faces) > 0:
        x, y, w, h = faces[0]
        face_crop = frame[y : y + h, x : x + w]
    else:
        face_crop = frame

    pending = session.get("pending_registration")
    if pending:
        import os
        temp_dir = os.path.join("dataset", "temp", pending["phone"])
        os.makedirs(temp_dir, exist_ok=True)
        cv2.imwrite(os.path.join(temp_dir, f"{step}.jpg"), face_crop)

    current_idx = CAPTURE_STEPS.index(step)
    if step == "final":
        return finalize_registration(image)

    next_step = CAPTURE_STEPS[current_idx + 1]
    session["capture_stage"] = next_step
    return jsonify({"status": "ok", "next_step_url": url_for("capture_stage", step=next_step)})


@app.route("/process_frame", methods=["POST"])
@login_required(role="admin")
def process_frame():
    frame = decode_base64_image(request.json["image"])
    faces = detect_faces(frame)
    training_active = is_model_training()

    if len(faces) == 0:
        return jsonify({"status": "scanning", "message": "Scanning...", "is_training": training_active})

    x, y, w, h = faces[0]
    face = frame[y : y + h, x : x + w]

    key, score = recognize(face)
    person = get_person_by_embedding_key(key) if key != "Unknown" else None

    if person and score >= 0.82:
        mark_present(person["id"], datetime.now().isoformat(timespec="seconds"))
        return jsonify(
            {
                "status": "captured",
                "user": person["name"],
                "confidence": round(score * 100, 2),
                "message": "Captured",
                "box": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                "is_training": training_active,
            }
        )

    return jsonify(
        {
            "status": "capturing",
            "user": "Unknown",
            "confidence": round(score * 100, 2),
            "message": "Capturing...",
            "box": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
            "is_training": training_active,
        }
    )


@app.route("/register", methods=["POST"])
@login_required(role="user")
def register_person():
    payload = request.get_json(force=True)
    name = payload.get("name", "").strip()
    place = payload.get("place", "").strip()
    phone = payload.get("phone", "").strip()
    image = payload.get("image", "")

    if not name or not place or not phone or not image:
        return jsonify({"status": "failed", "message": "All fields are required"}), 400

    frame = decode_base64_image(image)
    faces = detect_faces(frame)

    if len(faces) == 0:
        return jsonify({"status": "failed", "message": "No face detected"}), 400

    x, y, w, h = faces[0]
    face = frame[y : y + h, x : x + w]

    embedding_key = f"{name.lower()}|{phone}"

    try:
        person = create_person(name, place, phone, embedding_key)
    except sqlite3.IntegrityError:
        return jsonify({"status": "failed", "message": "Phone already registered"}), 400

    register_face(embedding_key, face)

    return jsonify(
        {
            "status": "registered",
            "message": "Registration completed",
            "person": {
                "name": person["name"],
                "place": person["place"],
                "phone": person["phone"],
                "registered_at": person["created_at"],
            },
        }
    )


def finalize_registration(image):
    pending = session.get("pending_registration")
    if not pending:
        return jsonify({"status": "failed", "message": "Registration details missing. Restart registration."}), 400

    frame = decode_base64_image(image)
    faces = detect_faces(frame)
    if len(faces) == 0:
        return jsonify({"status": "failed", "message": "No face detected in final capture."}), 400

    x, y, w, h = faces[0]
    face = frame[y : y + h, x : x + w]
    embedding_key = f"{pending['name'].lower()}|{pending['phone']}"

    # Save final crop to temp directory
    phone = pending["phone"]
    import os
    temp_dir = os.path.join("dataset", "temp", phone)
    os.makedirs(temp_dir, exist_ok=True)
    cv2.imwrite(os.path.join(temp_dir, "final.jpg"), face)

    try:
        person = upsert_person_by_phone(pending["name"], pending["place"], pending["phone"], embedding_key)
    except sqlite3.OperationalError:
        return jsonify({"status": "failed", "message": "Database busy. Please click Final Register again."}), 503

    register_face_multi(embedding_key, phone)
    session.pop("pending_registration", None)
    session.pop("capture_stage", None)

    return jsonify(
        {
            "status": "registered",
            "message": "Registration completed successfully.",
            "person": {
                "name": person["name"],
                "place": person["place"],
                "phone": person["phone"],
                "registered_at": person["created_at"],
            },
            "redirect_url": url_for("user_register"),
        }
    )


@app.route("/liveness_challenge", methods=["POST"])
@login_required(role="user")
def liveness_challenge():
    frame = decode_base64_image(request.json["image"])
    return jsonify(analyze_liveness_actions(frame))


if __name__ == "__main__":
    init_db()
    ensure_default_users()
    train_model()
    app.run(debug=True, use_reloader=False)
