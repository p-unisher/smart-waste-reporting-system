
import os
import sqlite3
import random
from datetime import datetime

from flask import (
    Flask, render_template, request, session,
    redirect, url_for, send_from_directory
)
from werkzeug.utils import secure_filename

import database


# ---------------- APP CONFIGURATION ----------------

app = Flask(__name__)
app.secret_key = os.environ.get(
    "SECRET_KEY", "smart_waste_secret_key"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(BASE_DIR, "waste_system.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


# ---------------- DATABASE FUNCTIONS ----------------

def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def add_column_if_missing(connection, table, column, definition):
    columns = [
        row["name"]
        for row in connection.execute(
            f"PRAGMA table_info({table})"
        ).fetchall()
    ]

    if column not in columns:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
        )


def initialize_database():
    database.create_database()

    connection = get_connection()

    add_column_if_missing(
        connection, "waste_reports", "submitted_at", "TEXT"
    )
    add_column_if_missing(
        connection, "waste_reports", "after_photo", "TEXT"
    )
    add_column_if_missing(
        connection, "waste_reports", "tracking_number", "TEXT"
    )
    add_column_if_missing(
        connection, "waste_reports", "latitude", "REAL"
    )
    add_column_if_missing(
        connection, "waste_reports", "longitude", "REAL"
    )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS report_counter (
            id INTEGER PRIMARY KEY,
            next_number INTEGER NOT NULL
        )
    """)

    connection.execute("""
        INSERT OR IGNORE INTO report_counter (id, next_number)
        VALUES (1, 1)
    """)

    old_reports = connection.execute("""
        SELECT id FROM waste_reports
        WHERE tracking_number IS NULL OR tracking_number = ''
        ORDER BY id
    """).fetchall()

    counter = connection.execute("""
        SELECT next_number FROM report_counter WHERE id = 1
    """).fetchone()

    next_number = counter["next_number"] if counter else 1

    for report in old_reports:
        tracking_number = f"SWR{next_number:06d}"

        connection.execute("""
            UPDATE waste_reports
            SET tracking_number = ?
            WHERE id = ?
        """, (tracking_number, report["id"]))

        next_number += 1

    existing_numbers = connection.execute("""
        SELECT tracking_number FROM waste_reports
        WHERE tracking_number LIKE 'SWR%'
    """).fetchall()

    for row in existing_numbers:
        try:
            number = int(row["tracking_number"][3:])
            next_number = max(next_number, number + 1)
        except (ValueError, TypeError):
            pass

    connection.execute("""
        UPDATE report_counter SET next_number = ? WHERE id = 1
    """, (next_number,))

    connection.commit()
    connection.close()


initialize_database()


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_uploaded_file(file):
    if not file or not file.filename:
        return None

    if not allowed_file(file.filename):
        return None

    filename = secure_filename(file.filename)

    unique_name = (
        datetime.now().strftime("%Y%m%d%H%M%S%f")
        + "_" + filename
    )

    file.save(os.path.join(UPLOAD_FOLDER, unique_name))
    return unique_name


def is_user_logged_in():
    return "user_id" in session


def is_admin_logged_in():
    return "admin_id" in session


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- SHARED LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_connection()

        admin = connection.execute("""
            SELECT * FROM admins
            WHERE LOWER(email) = ? AND password = ?
        """, (email, password)).fetchone()

        if admin:
            connection.close()
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_name"] = admin["name"]
            session["admin_email"] = admin["email"]

            return redirect(url_for("admin_dashboard"))

        user = connection.execute("""
            SELECT * FROM users
            WHERE LOWER(email) = ? AND password = ?
        """, (email, password)).fetchone()

        connection.close()

        if user:
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]

            return redirect(url_for("home"))

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    return render_template("login.html")


@app.route("/admin-login")
def admin_login():
    return redirect(url_for("login"))


# ---------------- USER REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        if not all([name, email, phone, password]):
            return render_template(
                "register.html",
                error="Please fill in all fields."
            )

        connection = get_connection()

        existing_user = connection.execute("""
            SELECT id FROM users WHERE LOWER(email) = ?
        """, (email,)).fetchone()

        existing_admin = connection.execute("""
            SELECT id FROM admins WHERE LOWER(email) = ?
        """, (email,)).fetchone()

        if existing_user or existing_admin:
            connection.close()
            return render_template(
                "register.html",
                error="This email is already registered."
            )

        connection.execute("""
            INSERT INTO users (name, email, phone, password)
            VALUES (?, ?, ?, ?)
        """, (name, email, phone, password))

        connection.commit()
        connection.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# ---------------- USER FORGOT PASSWORD ----------------

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        connection = get_connection()

        user = connection.execute("""
            SELECT email FROM users WHERE LOWER(email) = ?
        """, (email,)).fetchone()

        connection.close()

        if not user:
            return render_template(
                "forgot_password.html",
                error="Email address was not found."
            )

        otp = str(random.randint(100000, 999999))

        session["reset_email"] = user["email"]
        session["reset_otp"] = otp
        session["otp_verified"] = False

        print(f"User password reset OTP: {otp}")

        return render_template(
            "verify_otp.html",
            message="OTP generated. Check the Flask terminal."
        )

    return render_template("forgot_password.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if "reset_email" not in session:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        if entered_otp == session.get("reset_otp"):
            session["otp_verified"] = True
            return redirect(url_for("reset_password"))

        return render_template(
            "verify_otp.html",
            error="Incorrect OTP. Try again."
        )

    return render_template("verify_otp.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if (
        not session.get("otp_verified")
        or "reset_email" not in session
    ):
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or password != confirm_password:
            return render_template(
                "reset_password.html",
                error="Passwords are empty or do not match."
            )

        connection = get_connection()

        connection.execute("""
            UPDATE users SET password = ?
            WHERE LOWER(email) = ?
        """, (password, session["reset_email"].lower()))

        connection.commit()
        connection.close()

        session.pop("reset_email", None)
        session.pop("reset_otp", None)
        session.pop("otp_verified", None)

        return redirect(url_for("login"))

    return render_template("reset_password.html")


# ---------------- USER CHANGE PASSWORD ----------------

@app.route("/change-password", methods=["GET", "POST"])
def change_password():
    if not is_user_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        connection = get_connection()

        user = connection.execute("""
            SELECT password FROM users WHERE id = ?
        """, (session["user_id"],)).fetchone()

        if not user or user["password"] != old_password:
            connection.close()
            return render_template(
                "change_password.html",
                error="Current password is incorrect."
            )

        if not new_password or new_password != confirm_password:
            connection.close()
            return render_template(
                "change_password.html",
                error="New passwords do not match."
            )

        connection.execute("""
            UPDATE users SET password = ? WHERE id = ?
        """, (new_password, session["user_id"]))

        connection.commit()
        connection.close()

        return render_template(
            "change_password.html",
            message="Password changed successfully."
        )

    return render_template("change_password.html")


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ---------------- SUBMIT WASTE REPORT ----------------

@app.route("/report", methods=["GET", "POST"])
def report():
    if not is_user_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        waste_type = request.form.get("waste_type", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()

        latitude_text = request.form.get("latitude", "").strip()
        longitude_text = request.form.get("longitude", "").strip()

        photo = request.files.get("photo")

        if not waste_type or not location or not description:
            return render_template(
                "report.html",
                error="Please fill in all required fields."
            )

        if not photo or not photo.filename:
            return render_template(
                "report.html",
                error="Please upload a waste photo."
            )

        if not allowed_file(photo.filename):
            return render_template(
                "report.html",
                error="Use JPG, JPEG, PNG, GIF or WEBP photo."
            )

        latitude = None
        longitude = None

        if latitude_text or longitude_text:
            try:
                latitude = float(latitude_text)
                longitude = float(longitude_text)

                if not -90 <= latitude <= 90:
                    raise ValueError

                if not -180 <= longitude <= 180:
                    raise ValueError

            except (ValueError, TypeError):
                return render_template(
                    "report.html",
                    error="Invalid GPS coordinates."
                )

        photo_name = save_uploaded_file(photo)

        if not photo_name:
            return render_template(
                "report.html",
                error="Photo could not be uploaded."
            )

        connection = get_connection()

        counter = connection.execute("""
            SELECT next_number FROM report_counter WHERE id = 1
        """).fetchone()

        next_number = counter["next_number"] if counter else 1
        tracking_number = f"SWR{next_number:06d}"

        submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            connection.execute("""
                INSERT INTO waste_reports (
                    user_id, waste_type, location, description,
                    photo, status, submitted_at, tracking_number,
                    latitude, longitude
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session["user_id"],
                waste_type,
                location,
                description,
                photo_name,
                "Pending",
                submitted_at,
                tracking_number,
                latitude,
                longitude
            ))

            connection.execute("""
                UPDATE report_counter SET next_number = ?
                WHERE id = 1
            """, (next_number + 1,))

            connection.commit()

        except sqlite3.Error:
            connection.rollback()
            connection.close()

            return render_template(
                "report.html",
                error="Could not save report. Please try again."
            )

        connection.close()

        return render_template(
            "report.html",
            message="Waste report submitted successfully!",
            tracking_number=tracking_number
        )

    return render_template("report.html")


# ---------------- TRACK REPORT ----------------

@app.route("/track", methods=["GET", "POST"])
def track():
    if not is_user_logged_in():
        return redirect(url_for("login"))

    report_data = None
    error = None

    if request.method == "POST":
        tracking_number = request.form.get(
            "tracking_number", ""
        ).strip()

        if not tracking_number:
            error = "Please enter your tracking number."
        else:
            connection = get_connection()

            report_data = connection.execute("""
                SELECT * FROM waste_reports
                WHERE tracking_number = ? AND user_id = ?
            """, (
                tracking_number,
                session["user_id"]
            )).fetchone()

            connection.close()

            if not report_data:
                error = "Report not found. Check the tracking number."

    return render_template(
        "track.html",
        report=report_data,
        error=error
    )


# ---------------- MY REPORTS ----------------

@app.route("/my-reports")
def my_reports():
    if not is_user_logged_in():
        return redirect(url_for("login"))

    connection = get_connection()

    reports = connection.execute("""
        SELECT * FROM waste_reports
        WHERE user_id = ?
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()

    connection.close()

    return render_template("my_reports.html", reports=reports)


# ---------------- UPLOADED PHOTOS ----------------

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


# ---------------- INFORMATION PAGES ----------------

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            return render_template(
                "contact.html",
                error="Please fill in all fields."
            )

        return render_template(
            "contact.html",
            message="Thank you. Your message has been received."
        )

    return render_template("contact.html")


# ---------------- ADMIN FORGOT PASSWORD ----------------

@app.route("/admin-forgot-password", methods=["GET", "POST"])
def admin_forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        connection = get_connection()

        admin = connection.execute("""
            SELECT email FROM admins WHERE LOWER(email) = ?
        """, (email,)).fetchone()

        connection.close()

        if not admin:
            return render_template(
                "admin_forgot_password.html",
                error="Admin email was not found."
            )

        otp = str(random.randint(100000, 999999))

        session["admin_reset_email"] = admin["email"]
        session["admin_reset_otp"] = otp
        session["admin_otp_verified"] = False

        print(f"Admin password reset OTP: {otp}")

        return render_template(
            "admin_verify_otp.html",
            message="OTP generated. Check the Flask terminal."
        )

    return render_template("admin_forgot_password.html")


@app.route("/admin-verify-otp", methods=["GET", "POST"])
def admin_verify_otp():
    if "admin_reset_email" not in session:
        return redirect(url_for("admin_forgot_password"))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()

        if entered_otp == session.get("admin_reset_otp"):
            session["admin_otp_verified"] = True
            return redirect(url_for("admin_reset_password"))

        return render_template(
            "admin_verify_otp.html",
            error="Incorrect OTP. Try again."
        )

    return render_template("admin_verify_otp.html")


@app.route("/admin-reset-password", methods=["GET", "POST"])
def admin_reset_password():
    if (
        not session.get("admin_otp_verified")
        or "admin_reset_email" not in session
    ):
        return redirect(url_for("admin_forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password or password != confirm_password:
            return render_template(
                "admin_reset_password.html",
                error="Passwords are empty or do not match."
            )

        connection = get_connection()

        connection.execute("""
            UPDATE admins SET password = ?
            WHERE LOWER(email) = ?
        """, (password, session["admin_reset_email"].lower()))

        connection.commit()
        connection.close()

        session.pop("admin_reset_email", None)
        session.pop("admin_reset_otp", None)
        session.pop("admin_otp_verified", None)

        return redirect(url_for("login"))

    return render_template("admin_reset_password.html")


# ---------------- ADMIN LOGOUT ----------------

@app.route("/admin-logout")
def admin_logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin-dashboard")
def admin_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    connection = get_connection()

    reports = connection.execute("""
        SELECT
            wr.*,
            u.name AS user_name,
            u.email AS user_email,
            u.phone AS user_phone
        FROM waste_reports wr
        LEFT JOIN users u ON wr.user_id = u.id
        ORDER BY wr.id DESC
    """).fetchall()

    total_reports = connection.execute("""
        SELECT COUNT(*) AS total FROM waste_reports
    """).fetchone()["total"]

    pending_reports = connection.execute("""
        SELECT COUNT(*) AS total FROM waste_reports
        WHERE status = 'Pending'
    """).fetchone()["total"]

    completed_reports = connection.execute("""
        SELECT COUNT(*) AS total FROM waste_reports
        WHERE status = 'Completed'
    """).fetchone()["total"]

    connection.close()

    return render_template(
        "admin_dashboard.html",
        reports=reports,
        total_reports=total_reports,
        pending_reports=pending_reports,
        completed_reports=completed_reports
    )


# ---------------- UPDATE REPORT STATUS ----------------

@app.route("/update-status/<int:report_id>", methods=["POST"])
def update_status(report_id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    status = request.form.get("status", "").strip()

    allowed_statuses = {
        "Pending", "In Progress", "Completed", "Rejected"
    }

    if status not in allowed_statuses:
        return redirect(url_for("admin_dashboard"))

    connection = get_connection()

    connection.execute("""
        UPDATE waste_reports SET status = ?
        WHERE id = ?
    """, (status, report_id))

    connection.commit()
    connection.close()

    return redirect(url_for("admin_dashboard"))


# ---------------- AFTER-CLEANING PHOTO ----------------

@app.route("/upload-after-photo/<int:report_id>", methods=["POST"])
def upload_after_photo(report_id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    photo = request.files.get("after_photo")

    if not photo or not photo.filename or not allowed_file(photo.filename):
        return redirect(url_for("admin_dashboard"))

    photo_name = save_uploaded_file(photo)

    if not photo_name:
        return redirect(url_for("admin_dashboard"))

    connection = get_connection()

    connection.execute("""
        UPDATE waste_reports
        SET after_photo = ?, status = 'Completed'
        WHERE id = ?
    """, (photo_name, report_id))

    connection.commit()
    connection.close()

    return redirect(url_for("admin_dashboard"))


# ---------------- DELETE REPORT ----------------

@app.route("/delete-report/<int:report_id>", methods=["POST"])
def delete_report(report_id):
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    connection = get_connection()

    report = connection.execute("""
        SELECT photo, after_photo
        FROM waste_reports WHERE id = ?
    """, (report_id,)).fetchone()

    if report:
        connection.execute("""
            DELETE FROM waste_reports WHERE id = ?
        """, (report_id,))

        connection.commit()

        for column in ("photo", "after_photo"):
            filename = report[column]

            if filename:
                filepath = os.path.join(UPLOAD_FOLDER, filename)

                try:
                    if os.path.isfile(filepath):
                        os.remove(filepath)
                except OSError:
                    pass

    connection.close()

    return redirect(url_for("admin_dashboard"))


# ---------------- ADMIN SETTINGS ----------------

@app.route("/admin-settings", methods=["GET", "POST"])
def admin_settings():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    if request.method == "POST":
        old_password = request.form.get("old_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        connection = get_connection()

        admin = connection.execute("""
            SELECT password FROM admins WHERE id = ?
        """, (session["admin_id"],)).fetchone()

        if not admin or admin["password"] != old_password:
            connection.close()

            return render_template(
                "admin_settings.html",
                error="Current password is incorrect."
            )

        if not new_password or new_password != confirm_password:
            connection.close()

            return render_template(
                "admin_settings.html",
                error="New passwords do not match."
            )

        connection.execute("""
            UPDATE admins SET password = ? WHERE id = ?
        """, (new_password, session["admin_id"]))

        connection.commit()
        connection.close()

        return render_template(
            "admin_settings.html",
            message="Admin password updated successfully."
        )

    return render_template("admin_settings.html")


# ---------------- DATABASE CHECK ----------------

@app.route("/database-check")
def database_check():
    if not is_admin_logged_in():
        return redirect(url_for("login"))

    connection = get_connection()

    users_count = connection.execute(
        "SELECT COUNT(*) AS total FROM users"
    ).fetchone()["total"]

    reports_count = connection.execute(
        "SELECT COUNT(*) AS total FROM waste_reports"
    ).fetchone()["total"]

    admins_count = connection.execute(
        "SELECT COUNT(*) AS total FROM admins"
    ).fetchone()["total"]

    connection.close()

    return (
        f"Database connected successfully.<br>"
        f"Users: {users_count}<br>"
        f"Reports: {reports_count}<br>"
        f"Admins: {admins_count}"
    )


# ---------------- START APPLICATION ----------------

if __name__ == "__main__":
    app.run(debug=True)
