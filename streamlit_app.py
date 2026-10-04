"""Streamlit edition of StudyAssist, with per-account SQLite data."""

from __future__ import annotations

import calendar
import html
import json
import os
import sqlite3
import urllib.error
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import streamlit as st
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("STUDYASSIST_DB_PATH", BASE_DIR / "study_assistant_streamlit.db"))
SUBJECT_COLORS = ["#907aa9", "#ea9d34", "#b4637a", "#286983", "#56949f"]
QUOTES = (
    ("Education is the most powerful weapon which you can use to change the world.", "Nelson Mandela"),
    ("Dream transforms into thoughts. Thoughts result into action.", "A. P. J. Abdul Kalam"),
    ("Your time is limited, so don't waste it living someone else's life.", "Steve Jobs"),
    ("One child, one teacher, one book and one pen can change the world.", "Malala Yousafzai"),
    ("Like what you do; then you will do your best.", "Katherine Johnson"),
    ("Intelligence plus character—that is the goal of true education.", "Martin Luther King Jr."),
)

st.set_page_config(page_title="StudyAssist", page_icon="📚", layout="wide")


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root { color-scheme: light; }
        .stApp { background: #faf4ed; color: #575279; }
        [data-testid="stSidebar"] { background: #fffaf3; border-right: 1px solid #dfdad9; }
        [data-testid="stMetric"] { background: #fffaf3; border: 1px solid #dfdad9;
            border-radius: 14px; padding: 16px 18px; }
        [data-testid="stMetricLabel"] { color: #797593; }
        div.stButton > button, div.stFormSubmitButton > button {
            border-radius: 10px; border: 1px solid #907aa9; color: #575279;
            background: #f2e9e1; font-weight: 650; }
        div.stButton > button:hover, div.stFormSubmitButton > button:hover {
            border-color: #765d91; color: #575279; background: #eadfee; }
        div[data-testid="stForm"] { background: #fffaf3; border: 1px solid #dfdad9;
            border-radius: 14px; padding: 18px; }
        .hero { padding: 1.25rem 1.5rem; border: 1px solid #cecacd; border-radius: 18px;
            background: linear-gradient(115deg, #fffaf3, #f2e9e1 70%, #eadfee); margin-bottom: 1rem; }
        .quote { font-size: 1.25rem; line-height: 1.5; color: #575279; margin-top: .45rem; }
        .quote-author { font-weight: 750; color: #575279; margin-top: .45rem; }
        .streak { border-radius: 14px; background: linear-gradient(105deg,#f2e9e1,#eadfee);
            border: 1px solid #cecacd; padding: 14px 18px; margin: .75rem 0 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                color TEXT NOT NULL DEFAULT '#907aa9',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name)
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
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
                due_date TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'Medium',
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS task_completion_days (
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                completion_date TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(user_id, completion_date)
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL,
                content TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                minutes INTEGER NOT NULL,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS attendance_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
                attendance_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('Present', 'Absent')),
                note TEXT NOT NULL DEFAULT '',
                UNIQUE(subject_id, attendance_date)
            );
            """
        )


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with db_connection() as db:
        return db.execute(sql, params).fetchall()


def execute(sql: str, params: tuple = ()) -> int:
    with db_connection() as db:
        cursor = db.execute(sql, params)
        return cursor.lastrowid or 0


def current_user_id() -> int | None:
    value = st.session_state.get("user_id")
    return int(value) if value is not None else None


def get_subjects(user_id: int) -> list[sqlite3.Row]:
    return query(
        """SELECT s.*, COUNT(t.id) AS topic_count,
                  COALESCE(SUM(t.completed), 0) AS topics_done
           FROM subjects s LEFT JOIN topics t ON t.subject_id = s.id
           WHERE s.user_id = ? GROUP BY s.id ORDER BY s.name""",
        (user_id,),
    )


def get_tasks(user_id: int, *, due_today: bool = False) -> list[sqlite3.Row]:
    sql = """SELECT tasks.*, subjects.name AS subject_name
             FROM tasks LEFT JOIN subjects ON subjects.id = tasks.subject_id
             WHERE tasks.user_id = ?"""
    params: tuple = (user_id,)
    if due_today:
        sql += " AND tasks.due_date = ?"
        params += (date.today().isoformat(),)
    sql += (
        " ORDER BY tasks.completed, tasks.due_date, "
        "CASE tasks.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, tasks.id DESC"
    )
    return query(sql, params)


def mark_task_day(user_id: int) -> None:
    execute(
        "INSERT OR IGNORE INTO task_completion_days (user_id, completion_date) VALUES (?, ?)",
        (user_id, date.today().isoformat()),
    )


def get_streak(user_id: int) -> tuple[int, bool]:
    records = query(
        "SELECT completion_date FROM task_completion_days WHERE user_id = ?", (user_id,)
    )
    days = {date.fromisoformat(row["completion_date"]) for row in records}
    today = date.today()
    completed_today = today in days
    cursor = today if completed_today else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count, completed_today


def safe_gemini_key() -> str:
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    try:
        return str(st.secrets.get("GEMINI_API_KEY", ""))
    except (FileNotFoundError, KeyError):
        return ""


def local_plan(question: str, subjects: list[sqlite3.Row], tasks: list[sqlite3.Row]) -> str:
    names = [row["name"] for row in subjects]
    matched = next((name for name in names if name.casefold() in question.casefold()), None)
    subject = matched or "your topic"
    pending = [row["title"] for row in tasks if not row["completed"]][:3]
    first_step = f"Start with: {pending[0]}." if pending else "Add one small task to your task list before you begin."
    return (
        f"Here is a simple plan for {subject}:\n\n"
        "1. Spend 25 minutes reviewing one concept and write a 3-line summary.\n"
        "2. Take a 5-minute break, then solve two practice questions.\n"
        "3. Check your answers and note one question to ask your teacher.\n\n"
        f"{first_step}\nKeep the goal small enough to finish today."
    )


def gemini_answer(question: str, subjects: list[sqlite3.Row], tasks: list[sqlite3.Row]) -> str | None:
    key = safe_gemini_key()
    if not key:
        return None
    context = ", ".join(row["name"] for row in subjects) or "no subjects added yet"
    pending = ", ".join(row["title"] for row in tasks if not row["completed"]) or "no pending tasks"
    body = json.dumps({
        "contents": [{"parts": [{"text": (
            "You are StudyAssist, a warm, practical study coach for a first-semester college student. "
            "Give clear, short plans and never claim to do schoolwork for the student. "
            f"Student subjects: {context}. Pending tasks: {pending}. Student request: {question}"
        )}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 700},
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent",
        data=body,
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError):
        return None


def auth_screen() -> None:
    st.markdown("<div class='hero'><h1>StudyAssist 📚</h1><p>Your semester, organized.</p></div>", unsafe_allow_html=True)
    left, right = st.columns([1, 1.05], gap="large")
    with left:
        st.subheader("Welcome to your study space")
        st.caption("Sign in, or create an account to keep your study data private to you.")
        mode = st.radio("Account", ["Log in", "Create account"], horizontal=True, label_visibility="collapsed")
        with st.form("auth_form", clear_on_submit=False):
            username = st.text_input("Username", max_chars=40).strip()
            password = st.text_input("Password", type="password", max_chars=128)
            submitted = st.form_submit_button("Log in" if mode == "Log in" else "Create account", use_container_width=True)
        if submitted:
            if not username or not password:
                st.error("Enter both a username and password.")
            elif len(password) < 8:
                st.error("Use a password with at least 8 characters.")
            elif mode == "Create account":
                try:
                    user_id = execute(
                        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                        (username, generate_password_hash(password)),
                    )
                    st.session_state.user_id = user_id
                    st.session_state.username = username
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That username is already taken. Try logging in instead.")
            else:
                users = query("SELECT id, username, password_hash FROM users WHERE username = ? COLLATE NOCASE", (username,))
                if users and check_password_hash(users[0]["password_hash"], password):
                    st.session_state.user_id = users[0]["id"]
                    st.session_state.username = users[0]["username"]
                    st.rerun()
                else:
                    st.error("The username or password is incorrect.")
    with right:
        st.markdown("### Make today count")
        st.write("Manage subjects, tasks, attendance, notes and focused study time in one place.")
        st.info("Each account has its own study records. On Streamlit’s free hosting, local database files can be cleared when the app restarts or is redeployed.")


def page_dashboard(user_id: int, username: str) -> None:
    today = date.today()
    now = datetime.now()
    greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
    quote, author = QUOTES[today.toordinal() % len(QUOTES)]
    st.markdown(
        f"<div class='hero'><div style='letter-spacing:.12em;font-size:.78rem;font-weight:700'>{today.strftime('%A, %d %b %Y').upper()} &nbsp; · &nbsp; {now.strftime('%H:%M')}</div>"
        f"<h1 style='margin:.5rem 0'>{greeting}, {html.escape(username)} 👋</h1><div class='quote'>“{quote}”</div>"
        f"<div class='quote-author'>— {author}</div></div>",
        unsafe_allow_html=True,
    )
    subjects = get_subjects(user_id)
    tasks = get_tasks(user_id)
    notes_count = query("SELECT COUNT(*) AS n FROM notes WHERE user_id = ?", (user_id,))[0]["n"]
    focused = query(
        "SELECT COALESCE(SUM(minutes), 0) AS mins FROM focus_sessions WHERE user_id = ? AND date(completed_at) = ?",
        (user_id, today.isoformat()),
    )[0]["mins"]
    columns = st.columns(4)
    columns[0].metric("Subjects", len(subjects))
    columns[1].metric("Open tasks", sum(not row["completed"] for row in tasks))
    columns[2].metric("Study hours today", f"{focused / 60:.1f}")
    columns[3].metric("Saved notes", notes_count)
    streak, completed = get_streak(user_id)
    streak_text = "Today's task is complete. Your streak is safe until tomorrow." if completed else "Complete one task today to keep your streak going." if streak else "Complete one task today to start your streak."
    st.markdown(
        f"<div class='streak'><b>🔥 &nbsp; DAILY TASK STREAK</b><br><span style='font-size:1.35rem;font-weight:800'>{streak} day{'s' if streak != 1 else ''} in a row</span><br>{streak_text}</div>",
        unsafe_allow_html=True,
    )
    main, aside = st.columns([1.55, 1], gap="large")
    with main:
        st.subheader("Today's tasks")
        today_tasks = get_tasks(user_id, due_today=True)
        if not today_tasks:
            st.caption("No tasks due today. Add one from the Tasks page.")
        for task in today_tasks:
            c1, c2 = st.columns([.08, 1])
            value = c1.checkbox("Done", value=bool(task["completed"]), key=f"dash_task_{task['id']}", label_visibility="collapsed")
            c2.markdown(f"{'~~' if value else ''}**{task['title']}**{'~~' if value else ''}  ·  {task['subject_name'] or 'Unassigned'}  ·  {task['priority']}")
            if value != bool(task["completed"]):
                execute("UPDATE tasks SET completed = ? WHERE id = ? AND user_id = ?", (int(value), task["id"], user_id))
                if value:
                    mark_task_day(user_id)
                st.rerun()
        st.subheader("Subject progress")
        if not subjects:
            st.caption("Add your first subject to start tracking progress.")
        for subject in subjects:
            total = subject["topic_count"]
            progress = (subject["topics_done"] / total) if total else 0
            st.progress(progress, text=f"{subject['name']} · {round(progress * 100)}%")
    with aside:
        st.subheader("Study timer")
        timer_widget(user_id)
        st.subheader("Study suggestion")
        pending = [task for task in tasks if not task["completed"]]
        if pending:
            st.info(f"Start with **{pending[0]['title']}**. Try 25 focused minutes, then take a short break.")
        else:
            st.info("Choose one topic and spend 25 focused minutes reviewing it.")


@st.fragment(run_every="1s")
def timer_widget(user_id: int) -> None:
    if "timer_end" not in st.session_state:
        st.session_state.timer_end = None
    if "timer_minutes" not in st.session_state:
        st.session_state.timer_minutes = 25
    if st.session_state.timer_end:
        remaining = max(0, int(st.session_state.timer_end - datetime.now().timestamp()))
        st.markdown(f"<div style='text-align:center;font-size:2.5rem;font-weight:800'>{remaining // 60:02d}:{remaining % 60:02d}</div>", unsafe_allow_html=True)
        if remaining == 0:
            st.success("Focus session complete!")
            if st.button("Save completed session", key=f"save_timer_{user_id}"):
                execute("INSERT INTO focus_sessions (user_id, minutes) VALUES (?, ?)", (user_id, st.session_state.timer_minutes))
                st.session_state.timer_end = None
                st.rerun()
        elif st.button("Stop timer", key=f"stop_timer_{user_id}"):
            st.session_state.timer_end = None
            st.rerun()
    else:
        minutes = st.selectbox("Focus minutes", [25, 30, 45, 50], index=0, key="timer_duration")
        if st.button("Start focus session", use_container_width=True, key=f"start_timer_{user_id}"):
            st.session_state.timer_minutes = minutes
            st.session_state.timer_end = datetime.now().timestamp() + minutes * 60
            st.rerun()


def page_subjects(user_id: int) -> None:
    st.title("Subjects")
    st.caption("Organize courses and track completed topics.")
    with st.form("add_subject"):
        name = st.text_input("Subject name")
        color = st.selectbox("Color", SUBJECT_COLORS)
        if st.form_submit_button("Add subject"):
            if not name.strip():
                st.error("Enter a subject name.")
            else:
                try:
                    execute("INSERT INTO subjects (user_id, name, color) VALUES (?, ?, ?)", (user_id, name.strip(), color))
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("That subject already exists.")
    subjects = get_subjects(user_id)
    if not subjects:
        st.info("No subjects yet. Add your first course above.")
    for subject in subjects:
        with st.container(border=True):
            left, right = st.columns([4, 1])
            left.subheader(subject["name"])
            left.caption(f"{subject['topics_done']} of {subject['topic_count']} topics complete")
            left.progress(subject["topics_done"] / subject["topic_count"] if subject["topic_count"] else 0)
            if right.button("Delete", key=f"delete_subject_{subject['id']}"):
                execute("DELETE FROM subjects WHERE id = ? AND user_id = ?", (subject["id"], user_id))
                st.rerun()
            with st.form(f"topic_add_{subject['id']}"):
                topic_name = st.text_input("New topic", key=f"topic_name_{subject['id']}")
                if st.form_submit_button("Add topic"):
                    if topic_name.strip():
                        execute("INSERT INTO topics (subject_id, name) VALUES (?, ?)", (subject["id"], topic_name.strip()))
                        st.rerun()
            topics = query("SELECT * FROM topics WHERE subject_id = ? ORDER BY id", (subject["id"],))
            for topic in topics:
                done = st.checkbox(topic["name"], value=bool(topic["completed"]), key=f"topic_{topic['id']}")
                if done != bool(topic["completed"]):
                    execute("UPDATE topics SET completed = ? WHERE id = ?", (int(done), topic["id"]))
                    st.rerun()


def page_tasks(user_id: int) -> None:
    st.title("Tasks")
    subjects = get_subjects(user_id)
    with st.form("add_task"):
        title = st.text_input("Task")
        subject_options = {"Unassigned": None, **{item["name"]: item["id"] for item in subjects}}
        chosen = st.selectbox("Subject", list(subject_options))
        c1, c2 = st.columns(2)
        due = c1.date_input("Due date", value=date.today())
        priority = c2.selectbox("Priority", ["Low", "Medium", "High"], index=1)
        if st.form_submit_button("Add task"):
            if title.strip():
                execute("INSERT INTO tasks (user_id, title, subject_id, due_date, priority) VALUES (?, ?, ?, ?, ?)",
                        (user_id, title.strip(), subject_options[chosen], due.isoformat(), priority))
                st.rerun()
            else:
                st.error("Enter a task name.")
    view = st.radio("Show", ["Today", "Upcoming", "All", "Completed"], horizontal=True)
    sql = """SELECT tasks.*, subjects.name AS subject_name FROM tasks LEFT JOIN subjects ON subjects.id = tasks.subject_id WHERE tasks.user_id = ?"""
    params: tuple = (user_id,)
    if view == "Today":
        sql += " AND tasks.due_date = ? AND tasks.completed = 0"; params += (date.today().isoformat(),)
    elif view == "Upcoming":
        sql += " AND tasks.due_date > ? AND tasks.completed = 0"; params += (date.today().isoformat(),)
    elif view == "Completed":
        sql += " AND tasks.completed = 1"
    sql += " ORDER BY tasks.completed, tasks.due_date, tasks.id DESC"
    tasks = query(sql, params)
    if not tasks:
        st.info("No tasks in this view.")
    for task in tasks:
        a, b, c = st.columns([.08, 1, .2])
        checked = a.checkbox("Done", bool(task["completed"]), key=f"task_{task['id']}", label_visibility="collapsed")
        b.markdown(f"**{task['title']}**  ·  {task['subject_name'] or 'Unassigned'}  ·  {task['priority']}  ·  {task['due_date']}")
        if checked != bool(task["completed"]):
            execute("UPDATE tasks SET completed = ? WHERE id = ? AND user_id = ?", (int(checked), task["id"], user_id))
            if checked:
                mark_task_day(user_id)
            st.rerun()
        if c.button("Delete", key=f"task_delete_{task['id']}"):
            execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task["id"], user_id))
            st.rerun()


def page_attendance(user_id: int) -> None:
    st.title("Attendance tracker")
    subjects = get_subjects(user_id)
    if not subjects:
        st.info("Add a subject before recording attendance.")
        return
    selected = st.date_input("Choose a day", value=date.today(), key="attendance_date")
    by_name = {subject["name"]: subject["id"] for subject in subjects}
    with st.form("attendance_form"):
        subject_name = st.selectbox("Subject", list(by_name))
        status = st.selectbox("Status", ["Present", "Absent"])
        note = st.text_input("Note (optional)", max_chars=160)
        if st.form_submit_button("Save attendance"):
            execute(
                """INSERT INTO attendance_entries (subject_id, attendance_date, status, note) VALUES (?, ?, ?, ?)
                   ON CONFLICT(subject_id, attendance_date) DO UPDATE SET status = excluded.status, note = excluded.note""",
                (by_name[subject_name], selected.isoformat(), status, note.strip()),
            )
            st.rerun()
    month_start = selected.replace(day=1)
    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(month_start.year, month_start.month)
    st.subheader(month_start.strftime("%B %Y"))
    entries = query(
        """SELECT attendance_entries.*, subjects.name AS subject_name FROM attendance_entries
           JOIN subjects ON subjects.id = attendance_entries.subject_id
           WHERE subjects.user_id = ? AND attendance_date >= ? AND attendance_date < ?""",
        (user_id, weeks[0][0].isoformat(), (weeks[-1][-1] + timedelta(days=1)).isoformat()),
    )
    by_day: dict[str, list[sqlite3.Row]] = {}
    for entry in entries:
        by_day.setdefault(entry["attendance_date"], []).append(entry)
    labels = st.columns(7)
    for col, label in zip(labels, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
        col.caption(label)
    for week in weeks:
        cols = st.columns(7)
        for col, day in zip(cols, week):
            marks = by_day.get(day.isoformat(), [])
            icon = "🟢" if any(item["status"] == "Present" for item in marks) else "🔴" if marks else "·"
            title = f"{day.day} {icon}"
            col.markdown(f"**{title}**" if day.month == month_start.month else f":gray[{title}]")
    stats = query(
        """SELECT COUNT(*) AS held, COALESCE(SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END), 0) AS attended
           FROM attendance_entries JOIN subjects ON subjects.id = attendance_entries.subject_id WHERE subjects.user_id = ?""",
        (user_id,),
    )[0]
    attended, held = stats["attended"], stats["held"]
    st.metric("Attendance rate", f"{round(attended / held * 100) if held else 0}%", f"{attended} present of {held} recorded")
    st.subheader("Recent records")
    for entry in query(
        """SELECT attendance_entries.*, subjects.name AS subject_name FROM attendance_entries
           JOIN subjects ON subjects.id = attendance_entries.subject_id WHERE subjects.user_id = ?
           ORDER BY attendance_date DESC LIMIT 20""", (user_id,)
    ):
        st.write(f"**{entry['attendance_date']} · {entry['subject_name']}** — {entry['status']} {('· ' + entry['note']) if entry['note'] else ''}")


def page_notes(user_id: int) -> None:
    st.title("Notes")
    subjects = get_subjects(user_id)
    subject_options = {"Unassigned": None, **{item["name"]: item["id"] for item in subjects}}
    with st.form("add_note"):
        title = st.text_input("Title")
        subject_name = st.selectbox("Subject", list(subject_options))
        content = st.text_area("Note", height=150)
        if st.form_submit_button("Save note"):
            if title.strip():
                execute("INSERT INTO notes (user_id, title, subject_id, content) VALUES (?, ?, ?, ?)",
                        (user_id, title.strip(), subject_options[subject_name], content.strip()))
                st.rerun()
            else:
                st.error("Add a title to this note.")
    search = st.text_input("Search notes")
    notes = query(
        """SELECT notes.*, subjects.name AS subject_name FROM notes LEFT JOIN subjects ON subjects.id = notes.subject_id
           WHERE notes.user_id = ? AND (notes.title LIKE ? OR notes.content LIKE ?) ORDER BY notes.updated_at DESC""",
        (user_id, f"%{search}%", f"%{search}%"),
    )
    for note in notes:
        with st.expander(f"{note['title']} · {note['subject_name'] or 'Unassigned'}"):
            new_title = st.text_input("Title", value=note["title"], key=f"note_title_{note['id']}")
            new_content = st.text_area("Content", value=note["content"], key=f"note_content_{note['id']}")
            c1, c2 = st.columns(2)
            if c1.button("Update", key=f"note_update_{note['id']}"):
                execute("UPDATE notes SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND user_id = ?",
                        (new_title.strip(), new_content, note["id"], user_id))
                st.rerun()
            if c2.button("Delete", key=f"note_delete_{note['id']}"):
                execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note["id"], user_id))
                st.rerun()


def page_pomodoro(user_id: int) -> None:
    st.title("Pomodoro timer")
    st.caption("Choose a focus length on the dashboard timer; sessions you save appear here.")
    sessions = query(
        "SELECT minutes, completed_at FROM focus_sessions WHERE user_id = ? ORDER BY completed_at DESC LIMIT 30",
        (user_id,),
    )
    today = date.today().isoformat()
    today_minutes = sum(row["minutes"] for row in sessions if row["completed_at"].startswith(today))
    st.metric("Focused today", f"{today_minutes // 60}h {today_minutes % 60}m", f"{sum(row['completed_at'].startswith(today) for row in sessions)} sessions")
    if sessions:
        st.dataframe([{"Date": row["completed_at"], "Minutes": row["minutes"]} for row in sessions], use_container_width=True, hide_index=True)
    else:
        st.info("No completed sessions yet.")


def page_assistant(user_id: int) -> None:
    st.title("AI Study Assistant")
    st.caption("Ask for a manageable study plan based on your subjects and tasks.")
    subjects = get_subjects(user_id)
    tasks = get_tasks(user_id)
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    question = st.chat_input("What are you studying today?")
    if question:
        st.session_state.chat_messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        answer = gemini_answer(question, subjects, tasks)
        if answer is None:
            answer = local_plan(question, subjects, tasks)
            st.session_state.assistant_demo = True
        else:
            st.session_state.assistant_demo = False
        st.session_state.chat_messages.append({"role": "assistant", "content": answer})
        with st.chat_message("assistant"):
            st.markdown(answer)
    if st.session_state.get("assistant_demo", False):
        st.caption("Showing the built-in study plan. Add GEMINI_API_KEY in Streamlit app secrets for Gemini-generated answers.")
    elif not safe_gemini_key():
        st.caption("Gemini is optional. Add GEMINI_API_KEY in Streamlit app secrets to enable AI-generated answers.")


def page_analytics(user_id: int) -> None:
    st.title("Progress tracker")
    tasks = query("SELECT COUNT(*) AS total, COALESCE(SUM(completed),0) AS done FROM tasks WHERE user_id = ?", (user_id,))[0]
    notes = query("SELECT COUNT(*) AS n FROM notes WHERE user_id = ?", (user_id,))[0]["n"]
    focus = query("SELECT COALESCE(SUM(minutes),0) AS n FROM focus_sessions WHERE user_id = ?", (user_id,))[0]["n"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Tasks completed", f"{tasks['done']} / {tasks['total']}")
    c2.metric("Total focused time", f"{focus / 60:.1f} hours")
    c3.metric("Notes saved", notes)
    recent = query(
        """SELECT date(completed_at) AS day, SUM(minutes) AS minutes FROM focus_sessions
           WHERE user_id = ? GROUP BY date(completed_at) ORDER BY day DESC LIMIT 14""", (user_id,)
    )
    if recent:
        st.subheader("Study time by day")
        st.bar_chart([{"Date": row["day"], "Minutes": row["minutes"]} for row in reversed(recent)], x="Date", y="Minutes")
    streak, done_today = get_streak(user_id)
    st.metric("Current task streak", f"{streak} days", "Today's check-in complete" if done_today else "Complete one task today to continue")


def main() -> None:
    apply_theme()
    init_db()
    user_id = current_user_id()
    if user_id is None:
        auth_screen()
        return
    with st.sidebar:
        st.markdown("## ✨ StudyAssist")
        st.caption(f"Signed in as **{st.session_state.get('username', 'Student')}**")
        page = st.radio(
            "Workspace",
            ["Dashboard", "Subjects", "Tasks", "Attendance", "Notes", "Pomodoro", "AI Assistant", "Progress tracker"],
            label_visibility="collapsed",
        )
        st.divider()
        if st.button("Log out", use_container_width=True):
            for key in ("user_id", "username", "chat_messages", "timer_end"):
                st.session_state.pop(key, None)
            st.rerun()
    username = str(st.session_state.get("username", "Student"))
    if page == "Dashboard":
        page_dashboard(user_id, username)
    elif page == "Subjects":
        page_subjects(user_id)
    elif page == "Tasks":
        page_tasks(user_id)
    elif page == "Attendance":
        page_attendance(user_id)
    elif page == "Notes":
        page_notes(user_id)
    elif page == "Pomodoro":
        page_pomodoro(user_id)
    elif page == "AI Assistant":
        page_assistant(user_id)
    else:
        page_analytics(user_id)


main()
