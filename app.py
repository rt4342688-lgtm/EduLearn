import os
import sqlite3
from functools import wraps
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database" / "edulearn.db"
UPLOAD_DIR = BASE_DIR / "uploads" / "notes"
VIDEO_DIR = BASE_DIR / "uploads" / "videos"
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mov", "webm"}

app = Flask(__name__)

@app.template_filter('select_icon')
def select_icon(index):
    return ['🐍', '💻', '🗄️', '📘', '🎓'][((int(index or 1)-1) % 5)]
app.config["SECRET_KEY"] = os.environ.get("EDULEARN_SECRET", "change-this-secret-key-before-deployment")
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # 1 GB maximum upload
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    (BASE_DIR / "database").mkdir(exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student'
        );
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'General',
            video_url TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            quiz_id INTEGER,
            question TEXT NOT NULL,
            question_type TEXT NOT NULL DEFAULT 'mcq',
            option_a TEXT NOT NULL DEFAULT '',
            option_b TEXT NOT NULL DEFAULT '',
            option_c TEXT NOT NULL DEFAULT '',
            option_d TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
            FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            filename TEXT NOT NULL,
            FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            score INTEGER NOT NULL,
            total INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(course_id) REFERENCES courses(id)
        );
        """)
        qcols = [r["name"] for r in db.execute("PRAGMA table_info(questions)").fetchall()]
        if "quiz_id" not in qcols:
            db.execute("ALTER TABLE questions ADD COLUMN quiz_id INTEGER")
        if "question_type" not in qcols:
            db.execute("ALTER TABLE questions ADD COLUMN question_type TEXT NOT NULL DEFAULT 'mcq'")
        # Keep the existing course-wise questions working by placing them in a default quiz.
        for c in db.execute("SELECT id,title FROM courses").fetchall():
            quiz = db.execute("SELECT id FROM quizzes WHERE course_id=? ORDER BY id LIMIT 1", (c["id"],)).fetchone()
            if not quiz:
                cur = db.execute("INSERT INTO quizzes(course_id,title) VALUES(?,?)", (c["id"], "General Quiz"))
                quiz_id = cur.lastrowid
            else:
                quiz_id = quiz["id"]
            db.execute("UPDATE questions SET quiz_id=? WHERE course_id=? AND quiz_id IS NULL", (quiz_id, c["id"]))
        admin = db.execute("SELECT id FROM users WHERE email=?", ("admin@edulearn.local",)).fetchone()
        if not admin:
            db.execute(
                "INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,?)",
                ("EduLearn Admin", "admin@edulearn.local", generate_password_hash("Admin@123"), "admin")
            )
        count = db.execute("SELECT COUNT(*) AS n FROM courses").fetchone()["n"]
        if count == 0:
            course_data = [
                ("Python Programming", "Learn Python basics, variables, conditions and loops.", "Programming", "https://www.youtube.com/results?search_query=python+beginner+lessons"),
                ("Web Development", "Learn HTML, CSS and JavaScript for building websites.", "Web Design", "https://www.youtube.com/results?search_query=html+css+javascript+beginner"),
                ("Database Basics", "Understand tables, records, SQL and database concepts.", "Database", "https://www.youtube.com/results?search_query=database+sql+beginner")
            ]
            db.executemany("INSERT INTO courses(title,description,category,video_url) VALUES(?,?,?,?)", course_data)
            course_ids = [row["id"] for row in db.execute("SELECT id FROM courses ORDER BY id").fetchall()]
            sample_questions = [
                (course_ids[0], "Which keyword defines a function in Python?", "func", "def", "function", "define", "B"),
                (course_ids[0], "Which data type stores True or False?", "int", "str", "bool", "list", "C"),
                (course_ids[1], "What does HTML stand for?", "HyperText Markup Language", "HighText Machine Language", "HyperTool Multi Language", "Home Tool Markup Language", "A"),
                (course_ids[1], "Which language styles a web page?", "HTML", "CSS", "SQL", "Python", "B"),
                (course_ids[2], "Which SQL command retrieves data?", "GET", "OPEN", "SELECT", "READ", "C")
            ]
            db.executemany("""INSERT INTO questions(course_id,question,option_a,option_b,option_c,option_d,answer)
                              VALUES(?,?,?,?,?,?,?)""", sample_questions)
            for cid in course_ids:
                cur = db.execute("INSERT INTO quizzes(course_id,title) VALUES(?,?)", (cid, "General Quiz"))
                db.execute("UPDATE questions SET quiz_id=? WHERE course_id=? AND quiz_id IS NULL", (cur.lastrowid, cid))

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped

def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_user():
    return {"current_user": session.get("name"), "current_role": session.get("role")}

@app.route("/")
def index():
    with get_db() as db:
        courses = db.execute("SELECT * FROM courses ORDER BY id DESC").fetchall()
    return render_template("index.html", courses=courses)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name, a valid email and a password of at least 8 characters.", "danger")
            return render_template("register.html")
        try:
            with get_db() as db:
                db.execute("INSERT INTO users(name,email,password_hash) VALUES(?,?,?)",
                           (name, email, generate_password_hash(password)))
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("This email is already registered.", "danger")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session.update(user_id=user["id"], name=user["name"], role=user["role"])
            return redirect(url_for("admin") if user["role"] == "admin" else url_for("dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    with get_db() as db:
        courses = db.execute("SELECT * FROM courses ORDER BY title").fetchall()
        results = db.execute("""SELECT results.*, courses.title FROM results
                                JOIN courses ON courses.id=results.course_id
                                WHERE user_id=? ORDER BY results.id DESC LIMIT 5""",
                             (session["user_id"],)).fetchall()
    return render_template("dashboard.html", courses=courses, results=results)

@app.route("/courses")
@login_required
def courses():
    with get_db() as db:
        all_courses = db.execute("SELECT * FROM courses ORDER BY title").fetchall()
    return render_template("courses.html", courses=all_courses)

@app.route("/course/<int:course_id>")
@login_required
def course_detail(course_id):
    with get_db() as db:
        course = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
        if not course:
            abort(404)
        notes = db.execute("SELECT * FROM notes WHERE course_id=? ORDER BY id DESC", (course_id,)).fetchall()
        question_count = db.execute("SELECT COUNT(*) AS n FROM questions WHERE course_id=?", (course_id,)).fetchone()["n"]
        videos = db.execute("SELECT * FROM videos WHERE course_id=? ORDER BY id DESC", (course_id,)).fetchall()
    return render_template("course_detail.html", course=course, notes=notes, question_count=question_count, videos=videos)

@app.route("/notes/<int:note_id>")
@login_required
def download_note(note_id):
    with get_db() as db:
        note = db.execute("SELECT filename FROM notes WHERE id=?", (note_id,)).fetchone()
    if not note:
        abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], note["filename"], as_attachment=True)

@app.route("/quiz/<int:course_id>")
@login_required
def quiz(course_id):
    with get_db() as db:
        course = db.execute("SELECT * FROM courses WHERE id=?", (course_id,)).fetchone()
        if not course:
            abort(404)
        quizzes = db.execute("SELECT quizzes.*, (SELECT COUNT(*) FROM questions WHERE quiz_id=quizzes.id) AS question_count FROM quizzes WHERE course_id=? ORDER BY id", (course_id,)).fetchall()
    return render_template("quiz_list.html", course=course, quizzes=quizzes)

@app.route("/take-quiz/<int:quiz_id>", methods=["GET", "POST"])
@login_required
def take_quiz(quiz_id):
    with get_db() as db:
        quiz_row = db.execute("SELECT quizzes.*, quizzes.title AS quiz_title, courses.title AS course_title FROM quizzes JOIN courses ON courses.id=quizzes.course_id WHERE quizzes.id=?", (quiz_id,)).fetchone()
        if not quiz_row:
            abort(404)
        questions = db.execute("SELECT * FROM questions WHERE quiz_id=? ORDER BY id", (quiz_id,)).fetchall()
        if request.method == "POST":
            score = 0
            for q in questions:
                if request.form.get(f"q{q['id']}", "") == q["answer"]:
                    score += 1
            db.execute("INSERT INTO results(user_id,course_id,score,total) VALUES(?,?,?,?)", (session["user_id"], quiz_row["course_id"], score, len(questions)))
            flash(f"Quiz submitted! You scored {score} out of {len(questions)}.", "success")
            return redirect(url_for("results"))
    return render_template("quiz.html", course=quiz_row, questions=questions)

@app.route("/results")
@login_required
def results():
    with get_db() as db:
        rows = db.execute("""SELECT results.*, courses.title FROM results
                             JOIN courses ON courses.id=results.course_id
                             WHERE user_id=? ORDER BY results.id DESC""",
                          (session["user_id"],)).fetchall()
    return render_template("results.html", results=rows)

@app.route("/admin", methods=["GET", "POST"])
@admin_required
def admin():
    if request.method == "POST":
        action = request.form.get("action")
        with get_db() as db:
            if action == "course":
                title=request.form.get("title", "").strip(); description=request.form.get("description", "").strip(); category=request.form.get("category", "General").strip()
                if title and description:
                    cur=db.execute("INSERT INTO courses(title,description,category,video_url) VALUES(?,?,?,?)", (title,description,category,""))
                    db.execute("INSERT INTO quizzes(course_id,title) VALUES(?,?)", (cur.lastrowid,"General Quiz"))
                    flash("Course added.","success")
                else: flash("Course title and description are required.","danger")
            elif action == "edit_course":
                db.execute("UPDATE courses SET title=?,description=?,category=? WHERE id=?", (request.form.get("title","").strip(),request.form.get("description","").strip(),request.form.get("category","General").strip(),request.form.get("course_id",type=int)))
                flash("Course updated.","success")
            elif action == "delete_course":
                cid=request.form.get("course_id",type=int)
                for row in db.execute("SELECT filename FROM videos WHERE course_id=?",(cid,)).fetchall(): (VIDEO_DIR/row["filename"]).unlink(missing_ok=True)
                for row in db.execute("SELECT filename FROM notes WHERE course_id=?",(cid,)).fetchall(): (UPLOAD_DIR/row["filename"]).unlink(missing_ok=True)
                db.execute("DELETE FROM results WHERE course_id=?",(cid,))
                db.execute("DELETE FROM courses WHERE id=?",(cid,)); flash("Course and its content deleted.","success")
            elif action == "note":
                cid=request.form.get("course_id",type=int); title=request.form.get("note_title","").strip(); file=request.files.get("pdf")
                if file and file.filename.lower().endswith(".pdf") and title and db.execute("SELECT id FROM courses WHERE id=?",(cid,)).fetchone():
                    stored=f"{os.urandom(12).hex()}.pdf"; file.save(UPLOAD_DIR/stored); db.execute("INSERT INTO notes(course_id,title,filename) VALUES(?,?,?)",(cid,title,stored)); flash("PDF note uploaded.","success")
                else: flash("Choose a course, title and valid PDF file.","danger")
            elif action == "delete_note":
                nid=request.form.get("note_id",type=int); row=db.execute("SELECT filename FROM notes WHERE id=?",(nid,)).fetchone()
                if row: (UPLOAD_DIR/row["filename"]).unlink(missing_ok=True); db.execute("DELETE FROM notes WHERE id=?",(nid,)); flash("PDF note deleted.","success")
            elif action == "video":
                cid=request.form.get("course_id",type=int); title=request.form.get("video_title","").strip(); file=request.files.get("video")
                ext=(file.filename.rsplit(".",1)[-1].lower() if file and file.filename and "." in file.filename else "")
                if ext in ALLOWED_VIDEO_EXTENSIONS and title and db.execute("SELECT id FROM courses WHERE id=?",(cid,)).fetchone():
                    stored=f"{os.urandom(12).hex()}.{ext}"; file.save(VIDEO_DIR/stored); db.execute("INSERT INTO videos(course_id,title,filename) VALUES(?,?,?)",(cid,title,stored)); flash("Video uploaded.","success")
                else: flash("Choose a course, title and MP4, MOV or WebM video.","danger")
            elif action == "delete_video":
                vid=request.form.get("video_id",type=int); row=db.execute("SELECT filename FROM videos WHERE id=?",(vid,)).fetchone()
                if row: (VIDEO_DIR/row["filename"]).unlink(missing_ok=True); db.execute("DELETE FROM videos WHERE id=?",(vid,)); flash("Video deleted.","success")
            elif action == "add_quiz":
                cid=request.form.get("course_id",type=int); title=request.form.get("quiz_title","").strip()
                if title and db.execute("SELECT id FROM courses WHERE id=?",(cid,)).fetchone(): db.execute("INSERT INTO quizzes(course_id,title) VALUES(?,?)",(cid,title)); flash("Quiz added.","success")
                else: flash("Enter a quiz title and valid course.","danger")
            elif action == "delete_quiz":
                qid=request.form.get("quiz_id",type=int); db.execute("DELETE FROM quizzes WHERE id=?",(qid,)); flash("Quiz and its questions deleted.","success")
            elif action == "add_question":
                qid=request.form.get("quiz_id",type=int); question=request.form.get("question","").strip(); kind=request.form.get("question_type","mcq"); answer=request.form.get("answer","")
                quizrow=db.execute("SELECT course_id FROM quizzes WHERE id=?",(qid,)).fetchone()
                if quizrow and question and kind in ("mcq","true_false"):
                    if kind=="mcq":
                        opts=[request.form.get(f"option_{x}","").strip() for x in "abcd"]
                        if all(opts) and answer in "ABCD": db.execute("INSERT INTO questions(course_id,quiz_id,question,question_type,option_a,option_b,option_c,option_d,answer) VALUES(?,?,?,?,?,?,?,?,?)",(quizrow["course_id"],qid,question,kind,*opts,answer)); flash("Question added.","success")
                        else: flash("MCQ needs four options and a correct answer.","danger")
                    elif answer in ("true","false"):
                        db.execute("INSERT INTO questions(course_id,quiz_id,question,question_type,answer) VALUES(?,?,?,?,?)",(quizrow["course_id"],qid,question,kind,answer)); flash("True/False question added.","success")
                    else: flash("Choose True or False as the answer.","danger")
                else: flash("Enter a question and select a valid quiz.","danger")
            elif action == "delete_question":
                db.execute("DELETE FROM questions WHERE id=?",(request.form.get("question_id",type=int),)); flash("Question deleted.","success")
        return redirect(url_for("admin"))
    with get_db() as db:
        courses=db.execute("SELECT * FROM courses ORDER BY title").fetchall()
        users=db.execute("SELECT id,name,email,role FROM users ORDER BY id DESC").fetchall()
        total_results=db.execute("SELECT COUNT(*) AS n FROM results").fetchone()["n"]
        quizzes=db.execute("SELECT quizzes.*,courses.title AS course_title FROM quizzes JOIN courses ON courses.id=quizzes.course_id ORDER BY courses.title,quizzes.id").fetchall()
        questions=db.execute("SELECT questions.*,quizzes.title AS quiz_title,courses.title AS course_title FROM questions JOIN quizzes ON quizzes.id=questions.quiz_id JOIN courses ON courses.id=questions.course_id ORDER BY questions.id DESC").fetchall()
        notes=db.execute("SELECT notes.*,courses.title AS course_title FROM notes JOIN courses ON courses.id=notes.course_id ORDER BY notes.id DESC").fetchall()
        videos=db.execute("SELECT videos.*,courses.title AS course_title FROM videos JOIN courses ON courses.id=videos.course_id ORDER BY videos.id DESC").fetchall()
    return render_template("admin.html",courses=courses,users=users,total_results=total_results,quizzes=quizzes,questions=questions,notes=notes,videos=videos)

@app.route("/videos/<int:video_id>")
@login_required
def watch_video(video_id):
    with get_db() as db: row=db.execute("SELECT filename FROM videos WHERE id=?",(video_id,)).fetchone()
    if not row: abort(404)
    return send_from_directory(VIDEO_DIR,row["filename"],as_attachment=False,conditional=True)

@app.errorhandler(403)
def forbidden(_error):
    return render_template("message.html", heading="Access denied", message="Only an administrator can open this page."), 403

@app.errorhandler(413)
def too_large(_error):
    flash("The uploaded file is too large. Maximum upload size is 1 GB.", "danger")
    return redirect(url_for("admin"))

init_db()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
