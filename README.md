# StudyAssist — AI Student Study Assistant

A first-semester project built with **Python, Flask, SQLite, HTML, CSS, and JavaScript**. It includes a dashboard, subject and topic tracking, a task checklist, attendance tracking, notes, a Pomodoro timer, simple analytics, and study suggestions. A fresh database starts empty so you can create your account and add your own subjects, tasks, topics, notes, and attendance from the beginning.

## Run it on Windows

1. Install Python 3.10 or newer from [python.org](https://www.python.org/downloads/). During setup, select **Add Python to PATH**.
2. Open PowerShell in this folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

4. Install Flask and start the app:

   ```powershell
   pip install -r requirements.txt
   python app.py
   ```

5. Open <http://127.0.0.1:5000> in your browser and create your one local student account. The SQLite database is created automatically the first time the app runs.

On macOS or Linux, replace `py` with `python3` and activate with `source .venv/bin/activate`.

## Optional AI connection

Study suggestions work without an API key using a small local rule-based helper. To connect the optional OpenAI API, copy `.env.example` to `.env`, add your key on the `OPENAI_API_KEY=` line, and restart Flask. You can set `OPENAI_MODEL` too; it defaults to `gpt-4o-mini`. The `.env` file is ignored by Git and excluded from the project ZIP. Never put a real API key in a public repository or in frontend JavaScript.

PowerShell alternative (for the current terminal only):

```powershell
$env:OPENAI_API_KEY = "your-key"
python app.py
```

## Project layout

```text
study-assistant/
├── app.py                 # Flask routes, SQLite setup, and optional AI call
├── study_assistant.db     # Created automatically at runtime (not committed)
├── requirements.txt
├── templates/             # Jinja HTML pages
└── static/
    ├── css/style.css
    └── js/app.js
```

## Features

- Add and remove subjects; add topics and mark them complete.
- Create tasks with due dates and Low, Medium, or High priority; mark them complete or delete them.
- Build a daily task streak by completing at least one task per local calendar day. The dashboard shows whether today's check-in is complete and refreshes at midnight; completing a task the next day continues the streak.
- Create, search, edit, and delete notes.
- Record attendance by subject and date in a month calendar, update an existing day's status, and review overall and per-subject attendance rates.
- Run Pomodoro, short-break, and long-break timers. Completed focus sessions are stored in SQLite.
- View task and focus-time totals on the dashboard and analytics page.
- See an original motivational quote that changes with the local calendar day.
- See a live local clock on the dashboard.
- Create a local account, log in, and log out. Passwords are stored as hashes.
- Switch between light and dark themes; your choice is remembered in the browser.
- Use a custom flame hand cursor on mouse and trackpad devices.
- Ask for a study plan. The app uses a local fallback when no API key is set or the API cannot be reached.

## Database tables

`subjects`, `topics`, `tasks`, `task_completion_days`, `notes`, `focus_sessions`, and `attendance_entries`. A streak day is saved once per calendar date, even if multiple tasks are completed. Attendance is saved once per subject per date. Foreign keys keep related records consistent when a subject is removed.

## College project walkthrough

The Flask app handles browser requests and runs SQL queries through Python's built-in `sqlite3` library. Jinja templates display the results. JavaScript runs the timer in the browser and sends a completed session back to Flask. This is a learning prototype for one local student account; before deploying it for real users, add separate accounts with private data, CSRF protection, and a production secret key.
