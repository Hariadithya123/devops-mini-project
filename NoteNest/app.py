
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid4
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_from_directory,
    abort,
    session,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash


# --------------------------------------------------
# Application configuration
# --------------------------------------------------

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.environ.get(
    "UPLOAD_FOLDER",
    os.path.join(BASE_DIR, "uploads"),
)

DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(BASE_DIR, "notes.db"),
)

ALLOWED_EXTENSIONS = {"pdf"}

app = Flask(__name__)

secret_key = os.environ.get("SECRET_KEY")

if not secret_key:
    if os.environ.get("RENDER"):
        raise RuntimeError(
            "SECRET_KEY must be configured in Render environment variables."
        )
    secret_key = "change-this-development-key"

app.config["SECRET_KEY"] = secret_key
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# Use absolute paths so SQLite can locate the database reliably.
os.makedirs(os.path.dirname(os.path.abspath(DATABASE)), exist_ok=True)


# --------------------------------------------------
# Database connection
# --------------------------------------------------

@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                semester TEXT NOT NULL,
                unit TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                owner_id INTEGER,
                FOREIGN KEY(owner_id) REFERENCES users(id)
            )
        """)

        # Support databases created by older versions.
        columns = [
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(notes)"
            ).fetchall()
        ]

        if "owner_id" not in columns:
            conn.execute(
                "ALTER TABLE notes ADD COLUMN owner_id INTEGER"
            )


# --------------------------------------------------
# Authentication helpers
# --------------------------------------------------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash(
                "Please log in to share or delete your notes.",
                "error",
            )
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# --------------------------------------------------
# Home page, search and filters
# --------------------------------------------------

@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    subject = request.args.get("subject", "").strip()
    semester = request.args.get("semester", "").strip()

    sql = """
        SELECT notes.*, users.username AS owner_name
        FROM notes
        LEFT JOIN users ON notes.owner_id = users.id
        WHERE 1=1
    """

    params = []

    if query:
        sql += """
            AND (
                notes.title LIKE ?
                OR notes.subject LIKE ?
                OR notes.unit LIKE ?
            )
        """
        params.extend([f"%{query}%"] * 3)

    if subject:
        sql += " AND notes.subject = ?"
        params.append(subject)

    if semester:
        sql += " AND notes.semester = ?"
        params.append(semester)

    sql += " ORDER BY notes.uploaded_at DESC"

    with get_db() as conn:
        notes = conn.execute(sql, params).fetchall()

        subjects = [
            row["subject"]
            for row in conn.execute("""
                SELECT DISTINCT subject
                FROM notes
                ORDER BY subject
            """).fetchall()
        ]

        total = conn.execute(
            "SELECT COUNT(*) FROM notes"
        ).fetchone()[0]

        subject_count = conn.execute(
            "SELECT COUNT(DISTINCT subject) FROM notes"
        ).fetchone()[0]

    return render_template(
        "index.html",
        notes=notes,
        subjects=subjects,
        query=query,
        selected_subject=subject,
        selected_semester=semester,
        total=total,
        subject_count=subject_count,
        current_user=session.get("username"),
    )


# --------------------------------------------------
# Registration
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if len(username) < 3 or len(username) > 30:
            flash(
                "Username must be between 3 and 30 characters.",
                "error",
            )

        elif len(password) < 6:
            flash(
                "Password must contain at least 6 characters.",
                "error",
            )

        else:
            try:
                with get_db() as conn:
                    conn.execute(
                        """
                        INSERT INTO users (username, password_hash)
                        VALUES (?, ?)
                        """,
                        (
                            username,
                            generate_password_hash(password),
                        ),
                    )

                flash(
                    "Account created! You can now log in.",
                    "success",
                )
                return redirect(url_for("login"))

            except sqlite3.IntegrityError:
                flash(
                    "That username is already taken. Please choose another.",
                    "error",
                )

    return render_template("auth.html", mode="register")


# --------------------------------------------------
# Login and logout
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,),
            ).fetchone()

        if user and check_password_hash(
            user["password_hash"],
            password,
        ):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            flash(
                f"Welcome back, {user['username']}!",
                "success",
            )
            return redirect(url_for("index"))

        flash("Invalid username or password.", "error")

    return render_template("auth.html", mode="login")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------
# Upload PDF notes
# --------------------------------------------------

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    title = request.form.get("title", "").strip()
    subject = request.form.get("subject", "").strip()
    semester = request.form.get("semester", "").strip()
    unit = request.form.get("unit", "").strip()
    file = request.files.get("file")

    if (
        not all([title, subject, semester, unit])
        or not file
        or not file.filename
    ):
        flash(
            "Please complete every field and choose a PDF file.",
            "error",
        )
        return redirect(url_for("index"))

    if not allowed_file(file.filename):
        flash(
            "Only PDF files are supported in this version.",
            "error",
        )
        return redirect(url_for("index"))

    original_filename = secure_filename(file.filename)

    if not original_filename:
        flash("Please choose a valid filename.", "error")
        return redirect(url_for("index"))

    stored_filename = f"{uuid4().hex}.pdf"
    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        stored_filename,
    )

    file.save(file_path)

    try:
        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO notes (
                    title,
                    subject,
                    semester,
                    unit,
                    original_filename,
                    stored_filename,
                    uploaded_at,
                    owner_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    subject,
                    semester,
                    unit,
                    original_filename,
                    stored_filename,
                    datetime.now().strftime(
                        "%d %b %Y, %I:%M %p"
                    ),
                    session["user_id"],
                ),
            )

    except Exception:
        # Avoid leaving an unreferenced uploaded file behind.
        if os.path.exists(file_path):
            os.remove(file_path)
        raise

    flash(
        "Your notes have been shared successfully!",
        "success",
    )
    return redirect(url_for("index"))


# --------------------------------------------------
# Download notes
# --------------------------------------------------

@app.route("/download/<int:note_id>")
def download(note_id):
    with get_db() as conn:
        note = conn.execute(
            "SELECT * FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()

    if not note:
        flash("That note could not be found.", "error")
        return redirect(url_for("index"))

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        note["stored_filename"],
    )

    if not os.path.isfile(file_path):
        flash(
            "Sorry, the PDF file for this note is no longer available on the server.",
            "error",
        )
        return redirect(url_for("index"))

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        note["stored_filename"],
        as_attachment=True,
        download_name=note["original_filename"],
    )


# --------------------------------------------------
# Delete notes
# --------------------------------------------------

@app.route("/delete/<int:note_id>", methods=["POST"])
@login_required
def delete_note(note_id):
    with get_db() as conn:
        note = conn.execute(
            "SELECT * FROM notes WHERE id = ?",
            (note_id,),
        ).fetchone()

        if not note:
            abort(404)

        if (
            note["owner_id"] is not None
            and note["owner_id"] != session["user_id"]
        ):
            abort(403)

        conn.execute(
            "DELETE FROM notes WHERE id = ?",
            (note_id,),
        )

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        note["stored_filename"],
    )

    if os.path.isfile(file_path):
        os.remove(file_path)

    flash("Your note has been deleted.", "success")
    return redirect(url_for("index"))


# --------------------------------------------------
# Error handlers
# --------------------------------------------------

@app.errorhandler(403)
def forbidden(_error):
    return "You can only delete notes uploaded by your own account.", 403


@app.errorhandler(413)
def file_too_large(_error):
    flash(
        "That file is too large. Please upload a PDF smaller than 15 MB.",
        "error",
    )
    return redirect(url_for("index"))


# --------------------------------------------------
# Initialize the database
# --------------------------------------------------

init_db()


# --------------------------------------------------
# Local development server
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5050))
    print(f"Starting NoteNest on port {port}")
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
    )
