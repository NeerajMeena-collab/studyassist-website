"""StudyAssist: a small Flask + SQLite study planner for a first semester project."""

from __future__ import annotations

import json
import calendar
import os
import re
import sqlite3
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "study_assistant.db"
DAILY_QUOTES = (
    ("Education is the most powerful weapon which you can use to change the world.", "Nelson Mandela"),
    ("Dream transforms into thoughts. Thoughts result into action.", "A. P. J. Abdul Kalam"),
    ("Your time is limited, so don't waste it living someone else's life.", "Steve Jobs"),
    ("One child, one teacher, one book and one pen can change the world.", "Malala Yousafzai"),
    ("Like what you do; then you will do your best.", "Katherine Johnson"),
    ("Intelligence plus character—that is the goal of true education.", "Martin Luther King Jr."),
)


def load_local_env() -> None:
    """Load simple KEY=VALUE entries from a private project .env file."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        if key and value and not os.environ.get(key):
            os.environ[key] = value


load_local_env()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-for-deployment")


def connect_db() -> sqlite3.Connection:
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
    with connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT NOT NULL DEFAULT '#6958e8',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                due_date TEXT,
                completed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
                due_date TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'Medium',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS task_completion_days (
                completion_date TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                minutes INTEGER NOT NULL,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS attendance_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                attendance_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('Present', 'Absent')),
                note TEXT NOT NULL DEFAULT '',
                UNIQUE (subject_id, attendance_date)
            );
            """
        )
        # New installations intentionally start empty so students can add their own data.


def get_subjects() -> list[sqlite3.Row]:
    with connect_db() as db:
        return db.execute(
            """SELECT s.*,
                      COUNT(t.id) AS topic_count,
                      COALESCE(SUM(t.completed), 0) AS topics_done
               FROM subjects s LEFT JOIN topics t ON t.subject_id = s.id
               GROUP BY s.id ORDER BY s.name"""
        ).fetchall()


def today_string() -> str:
    return date.today().isoformat()


def daily_motivational_quote(today: date | None = None) -> tuple[str, str]:
    current_day = today or date.today()
    return DAILY_QUOTES[current_day.toordinal() % len(DAILY_QUOTES)]


def task_streak_summary(today: date | None = None) -> tuple[int, bool]:
    current_day = today or date.today()
    with connect_db() as db:
        completion_days = {
            date.fromisoformat(row["completion_date"])
            for row in db.execute("SELECT completion_date FROM task_completion_days").fetchall()
        }

    completed_today = current_day in completion_days
    streak_day = current_day if completed_today else current_day - timedelta(days=1)
    streak = 0
    while streak_day in completion_days:
        streak += 1
        streak_day -= timedelta(days=1)
    return streak, completed_today


def get_dashboard_suggestion(tasks: list[sqlite3.Row]) -> str:
    pending = [task for task in tasks if not task["completed"]]
    if not pending:
        return "You are all caught up. Choose one topic and spend 25 focused minutes reviewing it."
    high_priority = next((task for task in pending if task["priority"] == "High"), None)
    if high_priority:
        return f"Start with ‘{high_priority['title']}’. A short focused session on your highest-priority task is a good next step."
    return f"Try completing ‘{pending[0]['title']}’ next, then take a short break."


@app.context_processor
def add_template_data():
    return {"nav_subjects": get_subjects(), "today": today_string()}


@app.before_request
def require_login():
    if request.endpoint in {"login", "register", "static"} or request.endpoint is None:
        return None
    if session.get("user_id"):
        return None
    with connect_db() as db:
        has_account = db.execute("SELECT EXISTS(SELECT 1 FROM users)").fetchone()[0]
    return redirect(url_for("login" if has_account else "register"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with connect_db() as db:
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        flash("Username or password is incorrect.", "error")
    with connect_db() as db:
        has_account = bool(db.execute("SELECT EXISTS(SELECT 1 FROM users)").fetchone()[0])
    return render_template("login.html", has_account=has_account)


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    with connect_db() as db:
        has_account = bool(db.execute("SELECT EXISTS(SELECT 1 FROM users)").fetchone()[0])
    if has_account:
        flash("This local project already has its student account. Please log in.", "error")
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,32}", username):
            flash("Use 3–32 letters, numbers, underscores, or hyphens for your username.", "error")
        elif len(password) < 8:
            flash("Choose a password with at least 8 characters.", "error")
        elif password != confirm_password:
            flash("The passwords do not match.", "error")
        else:
            try:
                with connect_db() as db:
                    cursor = db.execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, generate_password_hash(password)),
                    )
                session.clear()
                session["user_id"] = cursor.lastrowid
                session["username"] = username
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That username is already in use.", "error")
    return render_template("register.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/")
def dashboard():
    with connect_db() as db:
        tasks = db.execute(
            """SELECT tasks.*, subjects.name AS subject_name, subjects.color AS subject_color
               FROM tasks LEFT JOIN subjects ON subjects.id = tasks.subject_id
               WHERE tasks.due_date = ? ORDER BY tasks.completed, 
               CASE tasks.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, tasks.id DESC""",
            (today_string(),),
        ).fetchall()
        subject_count = db.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        pending_count = db.execute("SELECT COUNT(*) FROM tasks WHERE completed = 0").fetchone()[0]
        notes_count = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        study_minutes = db.execute(
            "SELECT COALESCE(SUM(minutes), 0) FROM focus_sessions WHERE date(completed_at) = ?",
            (today_string(),),
        ).fetchone()[0]
        sessions_today = db.execute(
            "SELECT COUNT(*) FROM focus_sessions WHERE date(completed_at) = ?", (today_string(),)
        ).fetchone()[0]
    subjects = get_subjects()
    task_streak, task_completed_today = task_streak_summary()
    if task_completed_today:
        streak_message = "Today's task is complete. Your streak is safe until tomorrow."
    elif task_streak:
        streak_message = "Complete one task today to keep your streak going."
    else:
        streak_message = "Complete one task today to start your streak."
    return render_template(
        "dashboard.html", tasks=tasks, subjects=subjects, subject_count=subject_count,
        pending_count=pending_count, notes_count=notes_count, study_hours=study_minutes / 60,
        sessions_today=sessions_today, suggestion=get_dashboard_suggestion(tasks),
        task_streak=task_streak, task_completed_today=task_completed_today,
        streak_message=streak_message, daily_quote=daily_motivational_quote(),
    )


@app.get("/subjects")
def subjects_page():
    subjects = get_subjects()
    selected_id = request.args.get("subject", type=int)
    with connect_db() as db:
        topics = db.execute(
            """SELECT topics.*, subjects.name AS subject_name FROM topics
               JOIN subjects ON subjects.id = topics.subject_id
               WHERE (? IS NULL OR subjects.id = ?) ORDER BY subjects.name, topics.due_date, topics.id""",
            (selected_id, selected_id),
        ).fetchall()
    return render_template("subjects.html", subjects=subjects, topics=topics, selected_id=selected_id)


@app.post("/subjects/add")
def add_subject():
    name = request.form.get("name", "").strip()
    color = request.form.get("color", "#6958e8")
    if not name:
        flash("Please enter a subject name.", "error")
    else:
        try:
            with connect_db() as db:
                db.execute("INSERT INTO subjects (name, color) VALUES (?, ?)", (name, color))
            flash(f"{name} was added.", "success")
        except sqlite3.IntegrityError:
            flash("That subject already exists.", "error")
    return redirect(url_for("subjects_page"))


@app.post("/subjects/<int:subject_id>/delete")
def delete_subject(subject_id: int):
    with connect_db() as db:
        db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    flash("Subject deleted. Its topics were removed; related tasks and notes were kept without a subject.", "success")
    return redirect(url_for("subjects_page"))


@app.post("/topics/add")
def add_topic():
    subject_id = request.form.get("subject_id", type=int)
    name = request.form.get("name", "").strip()
    due_date = request.form.get("due_date", "").strip() or None
    if not subject_id or not name:
        flash("Choose a subject and enter a topic name.", "error")
    else:
        with connect_db() as db:
            db.execute("INSERT INTO topics (subject_id, name, due_date) VALUES (?, ?, ?)", (subject_id, name, due_date))
        flash("Topic added.", "success")
    return redirect(url_for("subjects_page", subject=subject_id))


@app.post("/topics/<int:topic_id>/toggle")
def toggle_topic(topic_id: int):
    with connect_db() as db:
        db.execute("UPDATE topics SET completed = 1 - completed WHERE id = ?", (topic_id,))
    return redirect(url_for("subjects_page", subject=request.form.get("subject_id", type=int)))


@app.post("/topics/<int:topic_id>/delete")
def delete_topic(topic_id: int):
    with connect_db() as db:
        db.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
    return redirect(url_for("subjects_page", subject=request.form.get("subject_id", type=int)))


@app.get("/tasks")
def tasks_page():
    view = request.args.get("view", "today")
    conditions = {
        "today": ("due_date = ? AND completed = 0", [today_string()]),
        "upcoming": ("due_date > ? AND completed = 0", [today_string()]),
        "completed": ("completed = 1", []),
        "all": ("1 = 1", []),
    }
    condition, params = conditions.get(view, conditions["today"])
    with connect_db() as db:
        tasks = db.execute(
            f"""SELECT tasks.*, subjects.name AS subject_name, subjects.color AS subject_color
                FROM tasks LEFT JOIN subjects ON subjects.id = tasks.subject_id
                WHERE {condition} ORDER BY tasks.completed, tasks.due_date,
                CASE tasks.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, tasks.id DESC""",
            params,
        ).fetchall()
    return render_template("tasks.html", tasks=tasks, subjects=get_subjects(), view=view)


@app.post("/tasks/add")
def add_task():
    title = request.form.get("title", "").strip()
    due_date = request.form.get("due_date", "").strip() or today_string()
    subject_id = request.form.get("subject_id", type=int) or None
    priority = request.form.get("priority", "Medium")
    if not title:
        flash("Please enter a task name.", "error")
    else:
        with connect_db() as db:
            db.execute(
                "INSERT INTO tasks (title, subject_id, due_date, priority) VALUES (?, ?, ?, ?)",
                (title, subject_id, due_date, priority if priority in {"Low", "Medium", "High"} else "Medium"),
            )
        flash("Task added.", "success")
    return redirect(url_for("tasks_page"))


@app.post("/tasks/<int:task_id>/toggle")
def toggle_task(task_id: int):
    with connect_db() as db:
        task = db.execute("SELECT completed FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task and task["completed"]:
            db.execute("UPDATE tasks SET completed = 0 WHERE id = ?", (task_id,))
        elif task:
            db.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
            db.execute(
                "INSERT OR IGNORE INTO task_completion_days (completion_date) VALUES (?)",
                (today_string(),),
            )
    return redirect(url_for("tasks_page", view=request.form.get("view", "today")))


@app.post("/tasks/<int:task_id>/delete")
def delete_task(task_id: int):
    with connect_db() as db:
        db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    flash("Task deleted.", "success")
    return redirect(url_for("tasks_page", view=request.form.get("view", "today")))


@app.get("/attendance")
def attendance_page():
    today = date.today()
    requested_date = request.args.get("date", "").strip()
    try:
        selected_date = date.fromisoformat(requested_date) if requested_date else None
    except ValueError:
        selected_date = None

    requested_month = request.args.get("month", "").strip()
    try:
        year, month_number = (int(part) for part in requested_month.split("-", 1))
        month_start = date(year, month_number, 1)
    except (ValueError, TypeError):
        month_start = (selected_date or today).replace(day=1)
    if selected_date:
        month_start = selected_date.replace(day=1)
    selected_date = selected_date or (today if month_start == today.replace(day=1) else month_start)

    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
    display_start = weeks[0][0]
    display_end = weeks[-1][-1] + timedelta(days=1)
    with connect_db() as db:
        subject_stats = db.execute(
            """SELECT subjects.id, subjects.name, subjects.color,
                      COUNT(attendance_entries.id) AS classes_held,
                      COALESCE(SUM(CASE WHEN attendance_entries.status = 'Present' THEN 1 ELSE 0 END), 0) AS attended
               FROM subjects LEFT JOIN attendance_entries ON attendance_entries.subject_id = subjects.id
               GROUP BY subjects.id ORDER BY subjects.name"""
        ).fetchall()
        records = db.execute(
            """SELECT attendance_entries.*, subjects.name AS subject_name, subjects.color AS subject_color
               FROM attendance_entries JOIN subjects ON subjects.id = attendance_entries.subject_id
               ORDER BY attendance_entries.attendance_date DESC, attendance_entries.id DESC LIMIT 40"""
        ).fetchall()
        visible_records = db.execute(
            """SELECT attendance_entries.*, subjects.name AS subject_name, subjects.color AS subject_color
               FROM attendance_entries JOIN subjects ON subjects.id = attendance_entries.subject_id
               WHERE attendance_entries.attendance_date >= ? AND attendance_entries.attendance_date < ?
               ORDER BY attendance_entries.attendance_date, subjects.name""",
            (display_start.isoformat(), display_end.isoformat()),
        ).fetchall()
        totals = db.execute(
            """SELECT COUNT(*) AS classes_held,
                      COALESCE(SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END), 0) AS attended
               FROM attendance_entries"""
        ).fetchone()
    entries_by_date = {}
    for record in visible_records:
        entries_by_date.setdefault(record["attendance_date"], []).append(record)
    calendar_weeks = []
    for week in weeks:
        calendar_week = []
        for calendar_date in week:
            day_entries = entries_by_date.get(calendar_date.isoformat(), [])
            calendar_week.append({
                "date": calendar_date.isoformat(),
                "month": calendar_date.strftime("%Y-%m"),
                "number": calendar_date.day,
                "in_month": calendar_date.month == month_start.month,
                "is_today": calendar_date == today,
                "is_selected": calendar_date == selected_date,
                "entries": day_entries,
                "present": sum(entry["status"] == "Present" for entry in day_entries),
                "absent": sum(entry["status"] == "Absent" for entry in day_entries),
            })
        calendar_weeks.append(calendar_week)
    previous_month = (month_start - timedelta(days=1)).strftime("%Y-%m")
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m")
    held = totals["classes_held"]
    attended = totals["attended"]
    attendance_rate = round(attended / held * 100) if held else 0
    return render_template(
        "attendance.html", subjects=subject_stats, records=records, calendar_weeks=calendar_weeks,
        month_label=month_start.strftime("%B %Y"), previous_month=previous_month,
        next_month=next_month, selected_date=selected_date.isoformat(),
        classes_held=held, attended=attended, attendance_rate=attendance_rate,
    )


@app.post("/attendance/save")
def save_attendance():
    subject_id = request.form.get("subject_id", type=int)
    attendance_date = request.form.get("attendance_date", "").strip() or today_string()
    status = request.form.get("status", "Present")
    note = request.form.get("note", "").strip()[:160]
    try:
        date.fromisoformat(attendance_date)
    except ValueError:
        flash("Choose a valid attendance date.", "error")
        return redirect(url_for("attendance_page"))
    if status not in {"Present", "Absent"}:
        status = "Present"
    with connect_db() as db:
        subject_exists = db.execute("SELECT 1 FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        if not subject_exists:
            flash("Choose a subject before saving attendance.", "error")
            return redirect(url_for("attendance_page", month=attendance_date[:7], date=attendance_date) + "#mark-attendance")
        db.execute(
            """INSERT INTO attendance_entries (subject_id, attendance_date, status, note)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(subject_id, attendance_date)
               DO UPDATE SET status = excluded.status, note = excluded.note""",
            (subject_id, attendance_date, status, note),
        )
    flash("Attendance saved. You can update a subject's record for that date any time.", "success")
    return redirect(url_for("attendance_page", month=attendance_date[:7], date=attendance_date) + "#mark-attendance")


@app.post("/attendance/<int:entry_id>/delete")
def delete_attendance(entry_id: int):
    with connect_db() as db:
        record = db.execute("SELECT attendance_date FROM attendance_entries WHERE id = ?", (entry_id,)).fetchone()
        db.execute("DELETE FROM attendance_entries WHERE id = ?", (entry_id,))
    flash("Attendance record removed.", "success")
    if record:
        attendance_date = record["attendance_date"]
        return redirect(url_for("attendance_page", month=attendance_date[:7], date=attendance_date) + "#attendance-history")
    return redirect(url_for("attendance_page"))


@app.get("/notes")
def notes_page():
    search = request.args.get("q", "").strip()
    selected_id = request.args.get("note", type=int)
    with connect_db() as db:
        notes = db.execute(
            """SELECT notes.*, subjects.name AS subject_name, subjects.color AS subject_color
               FROM notes LEFT JOIN subjects ON subjects.id = notes.subject_id
               WHERE notes.title LIKE ? OR notes.content LIKE ? ORDER BY notes.updated_at DESC, notes.id DESC""",
            (f"%{search}%", f"%{search}%"),
        ).fetchall()
        selected = next((note for note in notes if note["id"] == selected_id), None)
    return render_template("notes.html", notes=notes, selected=selected, subjects=get_subjects(), search=search)


@app.post("/notes/save")
def save_note():
    note_id = request.form.get("note_id", type=int)
    title = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    subject_id = request.form.get("subject_id", type=int) or None
    if not title:
        flash("A note needs a title.", "error")
        return redirect(url_for("notes_page", note=note_id) if note_id else url_for("notes_page", new=1))
    with connect_db() as db:
        if note_id:
            db.execute(
                "UPDATE notes SET title = ?, content = ?, subject_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title, content, subject_id, note_id),
            )
        else:
            cursor = db.execute(
                "INSERT INTO notes (title, content, subject_id) VALUES (?, ?, ?)", (title, content, subject_id)
            )
            note_id = cursor.lastrowid
    flash("Note saved.", "success")
    return redirect(url_for("notes_page", note=note_id))


@app.post("/notes/<int:note_id>/delete")
def delete_note(note_id: int):
    with connect_db() as db:
        db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    flash("Note deleted.", "success")
    return redirect(url_for("notes_page"))


@app.get("/pomodoro")
def pomodoro_page():
    with connect_db() as db:
        sessions = db.execute(
            "SELECT * FROM focus_sessions WHERE date(completed_at) = ? ORDER BY id DESC LIMIT 8", (today_string(),)
        ).fetchall()
        total_minutes = db.execute(
            "SELECT COALESCE(SUM(minutes), 0) FROM focus_sessions WHERE date(completed_at) = ?", (today_string(),)
        ).fetchone()[0]
    return render_template("pomodoro.html", sessions=sessions, total_minutes=total_minutes)


@app.post("/pomodoro/complete")
def complete_session():
    payload = request.get_json(silent=True) or {}
    minutes = max(1, min(int(payload.get("minutes", 25)), 180))
    with connect_db() as db:
        db.execute("INSERT INTO focus_sessions (minutes) VALUES (?)", (minutes,))
        total = db.execute(
            "SELECT COUNT(*), COALESCE(SUM(minutes), 0) FROM focus_sessions WHERE date(completed_at) = ?",
            (today_string(),),
        ).fetchone()
    return jsonify({"ok": True, "sessions_today": total[0], "hours_today": round(total[1] / 60, 1)})


def local_study_plan(question: str, subjects: list[sqlite3.Row], tasks: list[sqlite3.Row]) -> str:
    words = re.findall(r"[a-z0-9]+", question.lower())
    filler_words = {
        "a", "an", "and", "for", "give", "help", "i", "in", "make", "me", "my",
        "of", "please", "study", "the", "to", "want", "with", "plan", "can", "how",
    }
    useful_words = [word for word in words if word not in filler_words]
    has_vowel = any(char in "aeiou" for char in question.lower())
    if len(words) < 2 or not useful_words or not has_vowel:
        return (
            "I need a study topic to make a useful plan. Try something like: "
            "‘Help me revise Ohm’s law in 30 minutes’ or ‘Make a 1-week plan for C programming.’"
        )

    subject_names = [subject["name"] for subject in subjects]
    question_lower = question.lower()
    subject = next((name for name in subject_names if name.lower() in question_lower), None)
    if subject is None:
        tokens = set(words)
        if "physics" in tokens or "mechanics" in tokens or "ohm" in tokens:
            subject = next((name for name in subject_names if "physics" in name.lower()), None)
        elif "math" in tokens or "mathematics" in tokens or "algebra" in tokens:
            subject = next((name for name in subject_names if "math" in name.lower()), None)
        elif "programming" in tokens or "coding" in tokens or "loops" in tokens:
            subject = next((name for name in subject_names if "programming" in name.lower()), None)
    subject_label = subject or "your topic"
    pending = [task["title"] for task in tasks if not task["completed"]][:3]
    task_line = f"Start with: {', '.join(pending)}." if pending else "Add one small task to your task list before you begin."
    return (
        f"Here is a simple plan for {subject_label}:\n\n"
        f"1. Spend 25 minutes reviewing one concept and write a 3-line summary.\n"
        f"2. Take a 5-minute break, then solve two practice questions.\n"
        f"3. Check your answers and note one question to ask your teacher.\n\n"
        f"{task_line}\nKeep the goal small enough to finish today."
    )


def ask_openai(question: str, context: str) -> str | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    body = json.dumps({
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "messages": [
            {"role": "system", "content": "You are a kind study coach for a first-semester college student. Give practical, simple study advice with a short numbered plan."},
            {"role": "user", "content": f"Student's subjects and pending tasks: {context}\n\nRequest: {question}"},
        ],
        "temperature": 0.6,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, TimeoutError):
        return None


@app.route("/assistant", methods=["GET", "POST"])
def assistant_page():
    answer = None
    question = ""
    ai_enabled = bool(os.environ.get("OPENAI_API_KEY"))
    ai_used = False
    assistant_status = "Built-in demo response. Add an API key for AI-generated answers."
    with connect_db() as db:
        tasks = db.execute(
            "SELECT title, priority, completed FROM tasks WHERE completed = 0 ORDER BY due_date, id DESC LIMIT 6"
        ).fetchall()
    subjects = get_subjects()
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        if question:
            context = "; ".join([s["name"] for s in subjects]) + " | " + "; ".join(
                f"{task['title']} ({task['priority']} priority)" for task in tasks
            )
            answer = ask_openai(question, context) if ai_enabled else None
            ai_used = answer is not None
            if ai_used:
                assistant_status = "AI-generated answer from your configured API."
            else:
                answer = local_study_plan(question, subjects, tasks)
                assistant_status = (
                    "Built-in demo response. Your API key is set, but the AI service could not be reached."
                    if ai_enabled else "Built-in demo response. Add an API key for AI-generated answers."
                )
    return render_template(
        "assistant.html", answer=answer, question=question,
        ai_enabled=ai_enabled, ai_used=ai_used, assistant_status=assistant_status,
    )


@app.get("/analytics")
def analytics_page():
    with connect_db() as db:
        completed_tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE completed = 1").fetchone()[0]
        total_tasks = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        total_notes = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        total_minutes = db.execute("SELECT COALESCE(SUM(minutes), 0) FROM focus_sessions").fetchone()[0]
        recent = db.execute(
            "SELECT date(completed_at) AS day, SUM(minutes) AS minutes FROM focus_sessions GROUP BY date(completed_at) ORDER BY day DESC LIMIT 7"
        ).fetchall()
    return render_template(
        "analytics.html", completed_tasks=completed_tasks, total_tasks=total_tasks,
        total_notes=total_notes, total_hours=round(total_minutes / 60, 1), recent=list(reversed(recent)),
    )


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


init_db()

if __name__ == "__main__":
    app.run(debug=True)
