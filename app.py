from flask import Flask, render_template, request, redirect, session, flash, jsonify, make_response
import os, base64, numpy as np
from PIL import Image
from io import BytesIO, StringIO
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import csv, pytz, psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__)
app.secret_key = "frs_secret_2024"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

ATTENDANCE_START = 9
ATTENDANCE_END   = 16
ADMIN_USERNAME   = "admin"
ADMIN_PASSWORD   = "admin@123"
TIMEZONE         = pytz.timezone("Asia/Kolkata")

DATABASE_URL = os.environ.get("DATABASE_URL",
    "postgresql://postgres:@kumar_1729@db.sswoogvrbnlmhkmcfldz.supabase.co:5432/postgres")

os.makedirs("static/faces", exist_ok=True)

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS faculty (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            face_image TEXT NOT NULL,
            face_encoding BYTEA,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS working_days (
            id SERIAL PRIMARY KEY,
            date TEXT UNIQUE NOT NULL,
            marked_by TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            marked_by TEXT NOT NULL,
            UNIQUE(student_id, date)
        )
    """)
    conn.commit()
    conn.close()

try:
    init_db()
except Exception as e:
    print(f"DB init error: {e}")

def today():
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d")

def now_time():
    return datetime.now(TIMEZONE).strftime("%H:%M:%S")

def now_str():
    return datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")

def is_sunday():
    return datetime.now(TIMEZONE).weekday() == 6

def is_attendance_time():
    h = datetime.now(TIMEZONE).hour
    return ATTENDANCE_START <= h < ATTENDANCE_END

def get_working_day_today():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM working_days WHERE date=%s", (today(),))
    wd = c.fetchone()
    conn.close()
    return wd

def detect_face_region(img_array):
    pil_img = Image.fromarray(img_array)
    w, h = pil_img.size
    cropped = pil_img.crop((int(w*0.2), int(h*0.1), int(w*0.8), int(h*0.9)))
    return np.array(cropped.resize((64, 64), Image.LANCZOS))

def encode_face(img_array):
    try:
        face = detect_face_region(img_array)
        gray = np.dot(face[...,:3], [0.299, 0.587, 0.114]).astype(np.uint8)
        hist = np.zeros(256, dtype=np.float32)
        for val in gray.flatten():
            hist[val] += 1
        norm = np.linalg.norm(hist)
        return (hist / norm) if norm > 0 else hist
    except:
        return None

def compare_encodings(enc1, enc2):
    dot = np.dot(enc1, enc2)
    n1, n2 = np.linalg.norm(enc1), np.linalg.norm(enc2)
    if n1 == 0 or n2 == 0: return 0.0
    return float(dot / (n1 * n2))

def load_all_encodings():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, roll_no, face_encoding FROM students WHERE face_encoding IS NOT NULL")
    students = c.fetchall()
    conn.close()
    result = []
    for s in students:
        enc = np.frombuffer(bytes(s["face_encoding"]), dtype=np.float32)
        result.append({"id": s["id"], "name": s["name"],
                       "roll_no": s["roll_no"], "encoding": enc})
    return result

def get_report_data(start_date, end_date):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM students ORDER BY name")
    all_students = c.fetchall()
    c.execute("SELECT date FROM working_days WHERE date>=%s AND date<=%s ORDER BY date",
              (start_date, end_date))
    working_dates = [w["date"] for w in c.fetchall()]
    total_working = len(working_dates)
    rows = []
    for s in all_students:
        c.execute("SELECT date, time FROM attendance WHERE student_id=%s AND date>=%s AND date<=%s ORDER BY date",
                  (s["id"], start_date, end_date))
        att = c.fetchall()
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

# ===== AUTH =====
@app.route("/")
def home():
    if "faculty" in session: return redirect("/dashboard")
    if "admin" in session: return redirect("/admin")
    return redirect("/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM faculty WHERE username=%s", (username,))
        f = c.fetchone()
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

@app.route("/admin", methods=["GET","POST"])
def admin_panel():
    if "admin" not in session: return redirect("/admin/login")
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "add":
            name     = request.form["name"].strip()
            username = request.form["username"].strip()
            password = request.form["password"]
            if name and username and password:
                try:
                    c.execute("INSERT INTO faculty(name,username,password) VALUES(%s,%s,%s)",
                              (name, username, generate_password_hash(password)))
                    conn.commit()
                    flash(f"✅ Faculty '{name}' added!")
                except psycopg2.IntegrityError:
                    conn.rollback()
                    flash("❌ Username already exists!")
        elif action == "delete":
            fid = request.form.get("faculty_id")
            c.execute("DELETE FROM faculty WHERE id=%s", (fid,))
            conn.commit()
            flash("Faculty deleted.")
    c.execute("SELECT * FROM faculty ORDER BY name")
    faculties = c.fetchall()
    c.execute("SELECT COUNT(*) as c FROM students")
    total_students = c.fetchone()["c"]
    c.execute("SELECT COUNT(*) as c FROM working_days")
    total_working = c.fetchone()["c"]
    c.execute("SELECT COUNT(*) as c FROM attendance")
    total_att = c.fetchone()["c"]
    conn.close()
    return render_template("admin.html", faculties=faculties,
                           total_students=total_students,
                           total_working=total_working,
                           total_att=total_att)

# ===== DASHBOARD =====
@app.route("/dashboard")
def dashboard():
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as c FROM students")
    total_students = c.fetchone()["c"]
    c.execute("SELECT COUNT(*) as c FROM attendance WHERE date=%s", (today(),))
    present_today = c.fetchone()["c"]
    working_day = get_working_day_today()
    c.execute("SELECT COUNT(*) as c FROM working_days")
    total_working = c.fetchone()["c"]
    c.execute("""SELECT s.name, s.roll_no, a.time
                 FROM attendance a JOIN students s ON a.student_id=s.id
                 WHERE a.date=%s ORDER BY a.time DESC LIMIT 8""", (today(),))
    recent = c.fetchall()
    conn.close()
    return render_template("dashboard.html",
                           faculty=session["faculty"],
                           total=total_students,
                           present=present_today,
                           absent=total_students - present_today,
                           recent=recent, today=today(),
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
    c = conn.cursor()
    try:
        c.execute("INSERT INTO working_days(date,marked_by) VALUES(%s,%s)",
                  (today(), session["faculty_user"]))
        conn.commit()
        flash(f"✅ {today()} marked as working day!")
    except psycopg2.IntegrityError:
        conn.rollback()
        flash("Today is already marked as a working day.")
    conn.close()
    return redirect("/dashboard")

@app.route("/unmark_working_day", methods=["POST"])
def unmark_working_day():
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as c FROM attendance WHERE date=%s", (today(),))
    count = c.fetchone()["c"]
    if count > 0:
        flash("❌ Cannot undo — attendance already taken today!")
    else:
        c.execute("DELETE FROM working_days WHERE date=%s", (today(),))
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
    unknown_enc = encode_face(unknown_img)
    if unknown_enc is None:
        return jsonify({"match":False, "message":"Could not process image. Try again."})
    known = load_all_encodings()
    if not known:
        return jsonify({"match":False, "message":"No students registered yet!"})
    best_score, best_student = -1, None
    for k in known:
        score = compare_encodings(k["encoding"], unknown_enc)
        if score > best_score:
            best_score, best_student = score, k
    if best_score > 0.85:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM attendance WHERE student_id=%s AND date=%s",
                  (best_student["id"], today()))
        already = c.fetchone()
        conn.close()
        return jsonify({
            "match": True,
            "student_id": best_student["id"],
            "name": best_student["name"],
            "roll_no": best_student["roll_no"],
            "already_marked": already is not None,
            "confidence": round(best_score * 100, 1)
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
    c = conn.cursor()
    try:
        c.execute("INSERT INTO attendance(student_id,date,time,marked_by) VALUES(%s,%s,%s,%s)",
                  (student_id, today(), now_time(), session["faculty_user"]))
        conn.commit()
        c.execute("SELECT name,roll_no FROM students WHERE id=%s", (student_id,))
        student = c.fetchone()
        conn.close()
        return jsonify({"success":True, "name":student["name"], "roll_no":student["roll_no"]})
    except psycopg2.IntegrityError:
        conn.rollback()
        conn.close()
        return jsonify({"success":False, "message":"Already marked"})

@app.route("/api/today_status")
def today_status():
    if "faculty" not in session: return jsonify({"error":"unauthorized"}), 401
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id,name,roll_no FROM students ORDER BY name")
    all_s = c.fetchall()
    c.execute("SELECT student_id FROM attendance WHERE date=%s", (today(),))
    present_ids = {r["student_id"] for r in c.fetchall()}
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
            img = Image.open(BytesIO(img_bytes)).convert("RGB")
            img_array = np.array(img)
            encoding = encode_face(img_array)
            if encoding is None:
                flash("Could not process face! Retake in good lighting.")
                return redirect("/register_student")
            filename = f"{roll_no}.jpg"
            img.save(f"static/faces/{filename}")
            conn = get_db()
            c = conn.cursor()
            c.execute("INSERT INTO students(name,roll_no,face_image,face_encoding) VALUES(%s,%s,%s,%s)",
                      (name, roll_no, filename,
                       psycopg2.Binary(encoding.astype(np.float32).tobytes())))
            conn.commit()
            conn.close()
            flash(f"✅ '{name}' registered!")
            return redirect("/students")
        except psycopg2.IntegrityError:
            flash("Roll number already exists!")
    return render_template("register_student.html")

@app.route("/students")
def students():
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM students ORDER BY name")
    all_students = c.fetchall()
    conn.close()
    return render_template("students.html", students=all_students)

@app.route("/delete_student/<int:sid>", methods=["POST"])
def delete_student(sid):
    if "faculty" not in session: return redirect("/login")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT face_image FROM students WHERE id=%s", (sid,))
    s = c.fetchone()
    if s:
        path = f"static/faces/{s['face_image']}"
        if os.path.exists(path): os.remove(path)
        c.execute("DELETE FROM attendance WHERE student_id=%s", (sid,))
        c.execute("DELETE FROM students WHERE id=%s", (sid,))
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
    rows, working_dates, _ = get_report_data(date_from, date_to)
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
