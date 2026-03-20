from flask import Flask, render_template, request, redirect, session, flash, jsonify, make_response
import sqlite3, os, base64, face_recognition, numpy as np
from PIL import Image
from io import BytesIO, StringIO
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import csv

app = Flask(__name__)
app.secret_key = "frs_secret_2024"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

ATTENDANCE_START = 9
ATTENDANCE_END   = 16

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin@123"

os.makedirs("static/faces", exist_ok=True)

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            face_image TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS working_days (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT UNIQUE NOT NULL,
            marked_by TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            marked_by TEXT NOT NULL,
            UNIQUE(student_id, date)
        );
    """)
    conn.commit()
    conn.close()

init_db()

def today():
    return datetime.now().strftime("%Y-%m-%d")

def now_time():
    return datetime.now().strftime("%H:%M:%S")

def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_sunday():
    return datetime.now().weekday() == 6

def is_attendance_time():
    h = datetime.now().hour
    return ATTENDANCE_START <= h < ATTENDANCE_END

def get_working_day_today():
    conn = get_db()
    wd = conn.execute("SELECT * FROM working_days WHERE date=?", (today(),)).fetchone()
    conn.close()
    return wd

def load_all_face_encodings():
    conn = get_db()
    students = conn.execute("SELECT id, name, roll_no, face_image FROM students").fetchall()
    conn.close()
    encodings = []
    for s in students:
        path = f"static/faces/{s['face_image']}"
        if os.path.exists(path):
            try:
                img = face_recognition.load_image_file(path)
                encs = face_recognition.face_encodings(img)
                if encs:
                    encodings.append({
                        "id": s["id"], "name": s["name"],
                        "roll_no": s["roll_no"], "encoding": encs[0]
                    })
            except:
                pass
    return encodings

def get_report_data(start_date, end_date):
    conn = get_db()
    all_students = conn.execute("SELECT * FROM students ORDER BY name").fetchall()
    working_days = conn.execute(
        "SELECT date FROM working_days WHERE date>=? AND date<=? ORDER BY date",
        (start_date, end_date)).fetchall()
    working_dates = [w["date"] for w in working_days]
    total_working = len(working_dates)
    rows = []
    for s in all_students:
        att = conn.execute(
            "SELECT date, time FROM attendance WHERE student_id=? AND date>=? AND date<=? ORDER BY date",
            (s["id"], start_date, end_date)).fetchall()
        present_dates = {a["date"]: a["time"] for a in att}
        present_count = len(present_dates)
        pct = round(present_count / total_working * 100, 1) if total_working > 0 else 0
        rows.append({
            "name": s["name"], "roll_no": s["roll_no"],
            "present": present_count,
            "absent": total_working - present_count,
            "total": total_working, "pct": pct,
            "dates": working_dates, "present_dates": present_dates
        })
    conn.close()
    return rows, working_dates, total_working

# ===== HOME =====
@app.route("/")
def home():
    if "faculty" in session: return redirect("/dashboard")
    if "admin" in session: return redirect("/admin")
    return redirect("/login")

# ===== FACULTY LOGIN =====
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = get_db()
        f = conn.execute("SELECT * FROM faculty WHERE username=?", (username,)).fetchone()
        conn.close()
        if f and check_password_hash(f["password"], password):
            session.permanent = True
            session["faculty"] = f["name"]
            session["faculty_user"] = username
            return redirect("/dashboard")
        flash("Invalid username or password")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ===== ADMIN LOGIN =====
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session.permanent = True
            session["admin"] = True
            return redirect("/admin")
        flash("Invalid admin credentials")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin/login")

# ===== ADMIN PANEL =====
@app.route("/admin", methods=["GET","POST"])
def admin_panel():
    if "admin" not in session:
        return redirect("/admin/login")
    conn = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name     = request.form["name"].strip()
            username = request.form["username"].strip()
            password = request.form["password"]
            if name and username and password:
                try:
                    conn.execute("INSERT INTO faculty(name,username,password) VALUES(?,?,?)",
                                 (name, username, generate_password_hash(password)))
                    conn.commit()
                    flash(f"✅ Faculty '{name}' added!")
                except sqlite3.IntegrityError:
                    flash("❌ Username already exists!")
        elif action == "delete":
            fid = request.form.get("faculty_id")
            conn.execute("DELETE FROM faculty WHERE id=?", (fid,))
            conn.commit()
            flash("Faculty deleted.")
    faculties = conn.execute("SELECT * FROM faculty ORDER BY name").fetchall()
    total_students = conn.execute("SELECT COUNT(*) as c FROM students").fetchone()["c"]
    total_working  = conn.execute("SELECT COUNT(*) as c FROM working_days").fetchone()["c"]
    total_att      = conn.execute("SELECT COUNT(*) as c FROM attendance").fetchone()["c"]
    conn.close()
    return render_template("admin.html",
                           faculties=faculties,
                           total_students=total_students,
                           total_working=total_working,
                           total_att=total_att)

# ===== DASHBOARD =====
@app.route("/dashboard")
def dashboard():
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    total_students = conn.execute("SELECT COUNT(*) as c FROM students").fetchone()["c"]
    present_today  = conn.execute("SELECT COUNT(*) as c FROM attendance WHERE date=?", (today(),)).fetchone()["c"]
    working_day    = get_working_day_today()
    total_working  = conn.execute("SELECT COUNT(*) as c FROM working_days").fetchone()["c"]
    recent = conn.execute("""
        SELECT s.name, s.roll_no, a.time
        FROM attendance a JOIN students s ON a.student_id=s.id
        WHERE a.date=? ORDER BY a.time DESC LIMIT 8
    """, (today(),)).fetchall()
    conn.close()
    return render_template("dashboard.html",
                           faculty=session["faculty"],
                           total=total_students,
                           present=present_today,
                           absent=total_students - present_today,
                           recent=recent,
                           today=today(),
                           is_sunday=is_sunday(),
                           is_time=is_attendance_time(),
                           working_day=working_day,
                           total_working=total_working)

@app.route("/mark_working_day", methods=["POST"])
def mark_working_day():
    if "faculty" not in session: return redirect("/login")
    if is_sunday():
        flash("❌ Sunday is never a working day!")
        return redirect("/dashboard")
    conn = get_db()
    try:
        conn.execute("INSERT INTO working_days(date,marked_by) VALUES(?,?)",
                     (today(), session["faculty_user"]))
        conn.commit()
        flash(f"✅ {today()} marked as working day!")
    except sqlite3.IntegrityError:
        flash("Today is already marked as a working day.")
    conn.close()
    return redirect("/dashboard")

@app.route("/unmark_working_day", methods=["POST"])
def unmark_working_day():
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM attendance WHERE date=?", (today(),)).fetchone()["c"]
    if count > 0:
        flash("❌ Cannot undo — attendance already taken today!")
    else:
        conn.execute("DELETE FROM working_days WHERE date=?", (today(),))
        conn.commit()
        flash("↩️ Today removed from working days.")
    conn.close()
    return redirect("/dashboard")

# ===== SCAN =====
@app.route("/scan")
def scan():
    if "faculty" not in session: return redirect("/login")
    if is_sunday():
        flash("❌ Today is Sunday — no attendance!")
        return redirect("/dashboard")
    if not is_attendance_time():
        flash("❌ Attendance allowed only between 9:00 AM – 4:00 PM!")
        return redirect("/dashboard")
    if not get_working_day_today():
        flash("⚠️ Mark today as a working day first!")
        return redirect("/dashboard")
    return render_template("scan.html")

@app.route("/api/recognize", methods=["POST"])
def recognize():
    if "faculty" not in session: return jsonify({"error":"unauthorized"}), 401
    if not is_attendance_time():
        return jsonify({"error":"Outside attendance hours (9 AM–4 PM)"}), 403
    data = request.get_json()
    image_b64 = data.get("image","").split(",")[-1]
    try:
        img_bytes = base64.b64decode(image_b64)
        img = Image.open(BytesIO(img_bytes)).convert("RGB")
        unknown_img = np.array(img)
    except:
        return jsonify({"error":"Invalid image"}), 400
    unknown_encs = face_recognition.face_encodings(unknown_img)
    if not unknown_encs:
        return jsonify({"match":False, "message":"No face detected. Move closer."})
    known = load_all_face_encodings()
    if not known:
        return jsonify({"match":False, "message":"No students registered yet!"})
    distances = face_recognition.face_distance([k["encoding"] for k in known], unknown_encs[0])
    best_idx  = int(np.argmin(distances))
    best_dist = float(distances[best_idx])
    if best_dist < 0.45:
        student = known[best_idx]
        conn = get_db()
        already = conn.execute(
            "SELECT id FROM attendance WHERE student_id=? AND date=?",
            (student["id"], today())).fetchone()
        conn.close()
        return jsonify({
            "match": True,
            "student_id": student["id"],
            "name": student["name"],
            "roll_no": student["roll_no"],
            "already_marked": already is not None,
            "confidence": round((1 - best_dist) * 100, 1)
        })
    return jsonify({"match":False, "message":"Face not recognized. Try again."})

@app.route("/api/mark", methods=["POST"])
def mark_attendance():
    if "faculty" not in session: return jsonify({"error":"unauthorized"}), 401
    if not is_attendance_time():
        return jsonify({"success":False, "message":"Outside attendance hours!"}), 403
    data = request.get_json()
    student_id = data.get("student_id")
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO attendance(student_id,date,time,marked_by) VALUES(?,?,?,?)",
            (student_id, today(), now_time(), session["faculty_user"]))
        conn.commit()
        student = conn.execute("SELECT name,roll_no FROM students WHERE id=?", (student_id,)).fetchone()
        conn.close()
        return jsonify({"success":True, "name":student["name"], "roll_no":student["roll_no"]})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success":False, "message":"Already marked"})

@app.route("/api/today_status")
def today_status():
    if "faculty" not in session: return jsonify({"error":"unauthorized"}), 401
    conn = get_db()
    all_s = conn.execute("SELECT id,name,roll_no FROM students ORDER BY name").fetchall()
    present_ids = {r["student_id"] for r in
                   conn.execute("SELECT student_id FROM attendance WHERE date=?", (today(),)).fetchall()}
    conn.close()
    return jsonify([{"id":s["id"],"name":s["name"],"roll_no":s["roll_no"],
                     "present":s["id"] in present_ids} for s in all_s])

# ===== STUDENTS =====
@app.route("/register_student", methods=["GET","POST"])
def register_student():
    if "faculty" not in session: return redirect("/login")
    if request.method == "POST":
        name       = request.form["name"].strip()
        roll_no    = request.form["roll_no"].strip()
        image_data = request.form.get("image_data","")
        if not image_data:
            flash("Please capture face photo!")
            return redirect("/register_student")
        try:
            img_bytes = base64.b64decode(image_data.split(",")[1])
            img = Image.open(BytesIO(img_bytes))
            filename = f"{roll_no}.jpg"
            path = f"static/faces/{filename}"
            img.save(path)
            loaded = face_recognition.load_image_file(path)
            encs = face_recognition.face_encodings(loaded)
            if not encs:
                os.remove(path)
                flash("No face detected! Retake in good lighting.")
                return redirect("/register_student")
            conn = get_db()
            conn.execute("INSERT INTO students(name,roll_no,face_image) VALUES(?,?,?)",
                         (name, roll_no, filename))
            conn.commit(); conn.close()
            flash(f"✅ '{name}' registered!")
            return redirect("/students")
        except sqlite3.IntegrityError:
            flash("Roll number already exists!")
    return render_template("register_student.html")

@app.route("/students")
def students():
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    all_students = conn.execute("SELECT * FROM students ORDER BY name").fetchall()
    conn.close()
    return render_template("students.html", students=all_students)

@app.route("/delete_student/<int:sid>", methods=["POST"])
def delete_student(sid):
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    s = conn.execute("SELECT face_image FROM students WHERE id=?", (sid,)).fetchone()
    if s:
        path = f"static/faces/{s['face_image']}"
        if os.path.exists(path): os.remove(path)
        conn.execute("DELETE FROM attendance WHERE student_id=?", (sid,))
        conn.execute("DELETE FROM students WHERE id=?", (sid,))
        conn.commit()
    conn.close()
    flash("Student deleted.")
    return redirect("/students")

# ===== REPORT =====
@app.route("/report")
def report():
    if "faculty" not in session: return redirect("/login")
    mode      = request.args.get("mode","daily")
    date_from = request.args.get("from", today())
    date_to   = request.args.get("to", today())
    if mode == "daily":
        date_from = date_to = request.args.get("date", today())
    elif mode == "weekly":
        dt = datetime.strptime(date_from, "%Y-%m-%d")
        monday = dt - timedelta(days=dt.weekday())
        date_from = monday.strftime("%Y-%m-%d")
        date_to   = (monday + timedelta(days=5)).strftime("%Y-%m-%d")
    rows, working_dates, total_working = get_report_data(date_from, date_to)
    return render_template("report.html",
                           rows=rows, working_dates=working_dates,
                           total_working=total_working, mode=mode,
                           date_from=date_from, date_to=date_to, today=today())

@app.route("/download/csv")
def download_csv():
    if "faculty" not in session: return redirect("/login")
    date_from = request.args.get("from", today())
    date_to   = request.args.get("to", today())
    rows, working_dates, total_working = get_report_data(date_from, date_to)
    si = StringIO()
    writer = csv.writer(si)
    header = ["Roll No","Name","Present","Absent","Total Working Days","Attendance %"] + working_dates
    writer.writerow(header)
    for r in rows:
        row = [r["roll_no"],r["name"],r["present"],r["absent"],r["total"],f"{r['pct']}%"]
        for d in working_dates:
            row.append(f"P {r['present_dates'][d]}" if d in r["present_dates"] else "A")
        writer.writerow(row)
    response = make_response(si.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=attendance_{date_from}_to_{date_to}.csv"
    response.headers["Content-type"] = "text/csv"
    return response

@app.route("/download/pdf")
def download_pdf():
    if "faculty" not in session: return redirect("/login")
    date_from = request.args.get("from", today())
    date_to   = request.args.get("to", today())
    rows, working_dates, total_working = get_report_data(date_from, date_to)
    return render_template("pdf_report.html",
                           rows=rows, working_dates=working_dates,
                           total_working=total_working,
                           date_from=date_from, date_to=date_to,
                           faculty=session["faculty"],
                           generated_at=now_str())

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, ssl_context="adhoc")
