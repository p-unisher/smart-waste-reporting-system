import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, session, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import database
import sqlite3
import random
from datetime import datetime


app = Flask(__name__)

app.secret_key = "smart_waste_secret_key"


# Add the viewport meta tag to every HTML page that does not have it,
# so pages fit the screen on phones
@app.after_request
def add_viewport_meta(response):

    if response.mimetype == "text/html" and not response.direct_passthrough:

        html = response.get_data(as_text=True)

        if 'name="viewport"' not in html and "<head>" in html:

            html = html.replace(
                "<head>",
                '<head>\n<meta name="viewport" '
                'content="width=device-width, initial-scale=1.0">',
                1
            )

            response.set_data(html)

    return response


# ==================================================
# PASSWORD HELPERS
# ==================================================

def is_hashed(password):
    return password.startswith(("scrypt:", "pbkdf2:"))


def verify_password(stored_password, entered_password):
    # If the password is hashed, verify it with the hash.
    # If it is an old plain text password, compare it directly.
    if is_hashed(stored_password):
        return check_password_hash(stored_password, entered_password)

    return stored_password == entered_password


# ==================================================
# UPLOAD FOLDER
# ==================================================

UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ==================================================
# DATABASE
# ==================================================

database.create_database()


# Add new columns if they do not already exist
try:
    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()

    for column, column_type in (
        ("submitted_at", "TEXT"),
        ("after_photo", "TEXT"),
        ("tracking_number", "TEXT"),
        ("latitude", "REAL"),
        ("longitude", "REAL"),
    ):
        try:
            cursor.execute(
                f"ALTER TABLE waste_reports ADD COLUMN {column} {column_type}"
            )
        except sqlite3.OperationalError:
            # The column already exists
            pass

    # Create report counter table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_counter (
            id INTEGER PRIMARY KEY,
            next_number INTEGER NOT NULL
        )
    """)

    # Start tracking numbers from 1
    cursor.execute("""
        INSERT OR IGNORE INTO report_counter (id, next_number)
        VALUES (1, 1)
    """)

    connection.commit()
    connection.close()

except sqlite3.OperationalError:
    pass


# ==================================================
# CONVERT OLD PLAIN TEXT PASSWORDS TO HASH
# ==================================================

def hash_existing_passwords():
    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()

    for table in ("users", "admins"):
        cursor.execute(f"SELECT id, password FROM {table}")

        for row_id, password in cursor.fetchall():
            if password and not is_hashed(password):
                cursor.execute(
                    f"UPDATE {table} SET password = ? WHERE id = ?",
                    (generate_password_hash(password), row_id)
                )

    connection.commit()
    connection.close()


hash_existing_passwords()


# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():
    return render_template("index.html")


# ==================================================
# SINGLE LOGIN (ADMIN AND USER)
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"].strip().lower()
        password = request.form["password"]

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        # Step 1: check the admins table first
        cursor.execute("""
            SELECT * FROM admins WHERE LOWER(email) = ?
        """, (email,))

        admin = cursor.fetchone()

        # admin columns: id, name, email, password
        if admin and verify_password(admin[3], password):

            connection.close()

            session.clear()
            session["admin_id"] = admin[0]
            session["admin_name"] = admin[1]
            session["admin_email"] = admin[2]

            return redirect(url_for("admin_dashboard"))

        # Step 2: check the users table
        cursor.execute("""
            SELECT * FROM users WHERE LOWER(email) = ?
        """, (email,))

        user = cursor.fetchone()

        connection.close()

        # user columns: id, name, email, phone, password
        if user and verify_password(user[4], password):

            session.clear()
            session["user_id"] = user[0]
            session["user_name"] = user[1]
            session["user_email"] = user[2]

            # The header shows "Welcome, <name>" after a successful login
            return redirect(url_for("home"))

        return render_template(
            "login.html",
            message="Invalid email or password."
        )

    return render_template("login.html")


# The old admin login URL now opens the single login page
@app.route("/admin-login")
def admin_login():
    return redirect(url_for("login"))


# ==================================================
# REGISTER
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"].strip().lower()
        phone = request.form["phone"]
        password = request.form["password"]

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        cursor.execute("""
            SELECT id FROM users WHERE LOWER(email) = ?
        """, (email,))

        existing_user = cursor.fetchone()

        # An admin email cannot be used for a user account
        cursor.execute("""
            SELECT id FROM admins WHERE LOWER(email) = ?
        """, (email,))

        existing_admin = cursor.fetchone()

        if existing_user or existing_admin:

            connection.close()

            return render_template(
                "register.html",
                message="Email already registered."
            )

        cursor.execute("""
            INSERT INTO users (name, email, phone, password)
            VALUES (?, ?, ?, ?)
        """, (name, email, phone, generate_password_hash(password)))

        connection.commit()
        connection.close()

        # "success" is shown in green, "message" is shown in red
        return render_template(
            "login.html",
            success="Registration successful! Please login."
        )

    return render_template("register.html")


# ==================================================
# SINGLE FORGOT PASSWORD (ADMIN AND USER)
# ==================================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"].strip().lower()

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        # Check the admins table first
        cursor.execute("""
            SELECT id FROM admins WHERE LOWER(email) = ?
        """, (email,))

        admin = cursor.fetchone()

        user = None

        # If it is not an admin, check the users table
        if not admin:
            cursor.execute("""
                SELECT id FROM users WHERE LOWER(email) = ?
            """, (email,))

            user = cursor.fetchone()

        connection.close()

        if not admin and not user:
            return render_template(
                "forgot_password.html",
                message="Email not found."
            )

        otp = str(random.randint(100000, 999999))

        session["reset_email"] = email
        session["reset_type"] = "admin" if admin else "user"
        session["reset_otp"] = otp
        session.pop("otp_verified", None)

        # The OTP is printed in the server log
        print("--------------------------------")
        print("PASSWORD RESET OTP:", otp)
        print("--------------------------------")

        return redirect(url_for("verify_otp"))

    return render_template("forgot_password.html")


@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():

    # The reset must start from the forgot password page
    if not session.get("reset_email"):
        return redirect(url_for("forgot_password"))

    if request.method == "POST":

        entered_otp = request.form["otp"].strip()
        saved_otp = session.get("reset_otp")

        if saved_otp and entered_otp == saved_otp:
            session["otp_verified"] = True
            return redirect(url_for("reset_password"))

        return render_template("verify_otp.html", message="Invalid OTP.")

    return render_template("verify_otp.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():

    if not session.get("otp_verified") or not session.get("reset_email"):
        return redirect(url_for("forgot_password"))

    if request.method == "POST":

        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        if new_password == "":
            return render_template(
                "reset_password.html",
                message="Password cannot be empty."
            )

        if new_password != confirm_password:
            return render_template(
                "reset_password.html",
                message="Passwords do not match."
            )

        email = session.get("reset_email")

        # Update the table of the account type that was found earlier
        if session.get("reset_type") == "admin":
            table = "admins"
        else:
            table = "users"

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        cursor.execute(
            f"UPDATE {table} SET password = ? WHERE LOWER(email) = ?",
            (generate_password_hash(new_password), email)
        )

        connection.commit()
        connection.close()

        session.pop("reset_email", None)
        session.pop("reset_type", None)
        session.pop("reset_otp", None)
        session.pop("otp_verified", None)

        return render_template(
            "login.html",
            success="Password reset successfully! Please login."
        )

    return render_template("reset_password.html")


# The old admin forgot password URL now opens the single page
@app.route("/admin-forgot-password")
def admin_forgot_password():
    return redirect(url_for("forgot_password"))


# ==================================================
# CHANGE USER PASSWORD
# ==================================================

@app.route("/change-password", methods=["GET", "POST"])
def change_password():

    if not session.get("user_id"):
        return "Please login before changing your password."

    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        cursor.execute("""
            SELECT password FROM users WHERE id = ?
        """, (session["user_id"],))

        user = cursor.fetchone()

        if not user:
            connection.close()
            return render_template(
                "change_password.html",
                message="User account not found."
            )

        if not verify_password(user[0], current_password):
            connection.close()
            return render_template(
                "change_password.html",
                message="Current password is incorrect."
            )

        if new_password == "":
            connection.close()
            return render_template(
                "change_password.html",
                message="New password cannot be empty."
            )

        if new_password != confirm_password:
            connection.close()
            return render_template(
                "change_password.html",
                message="New passwords do not match."
            )

        cursor.execute("""
            UPDATE users SET password = ? WHERE id = ?
        """, (generate_password_hash(new_password), session["user_id"]))

        connection.commit()
        connection.close()

        return render_template(
            "change_password.html",
            success="Password changed successfully!"
        )

    return render_template("change_password.html")


# ==================================================
# USER LOGOUT
# ==================================================

@app.route("/logout")
def logout():

    session.pop("user_id", None)
    session.pop("user_name", None)
    session.pop("user_email", None)

    return redirect(url_for("home"))


# ==================================================
# REPORT WASTE
# ==================================================

@app.route("/report", methods=["GET", "POST"])
def report():

    if not session.get("user_id"):
        return "Please login before submitting a report."

    if request.method == "POST":

        waste_type = request.form["waste_type"]
        location = request.form["location"]
        description = request.form["description"]

        # Live location (optional)
        latitude = request.form.get("latitude", "").strip()
        longitude = request.form.get("longitude", "").strip()

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except ValueError:
            latitude = None
            longitude = None

        photo = request.files.get("photo")

        filename = None

        allowed_extensions = {"jpg", "jpeg", "png", "gif", "webp"}

        if photo and photo.filename:

            original_filename = secure_filename(photo.filename)

            extension = ""

            if "." in original_filename:
                extension = original_filename.rsplit(".", 1)[1].lower()

            if extension not in allowed_extensions:
                return render_template(
                    "report.html",
                    message="Invalid photo format. Please upload JPG, JPEG, PNG, GIF or WEBP."
                )

            random_number = random.randint(100000, 999999)

            filename = (
                os.path.splitext(original_filename)[0]
                + "_"
                + str(random_number)
                + "."
                + extension
            )

            photo.save(
                os.path.join(app.config["UPLOAD_FOLDER"], filename)
            )

        submitted_at = datetime.now().strftime("%d-%m-%Y %I:%M %p")

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        # Get the next unique tracking number
        cursor.execute("""
            SELECT next_number FROM report_counter WHERE id = 1
        """)

        counter = cursor.fetchone()

        next_number = counter[0]

        tracking_number = f"WR{next_number:03d}"

        # Increase the counter
        cursor.execute("""
            UPDATE report_counter SET next_number = ? WHERE id = 1
        """, (next_number + 1,))

        # Insert the report
        cursor.execute("""
            INSERT INTO waste_reports
            (
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
            filename,
            "Pending",
            submitted_at,
            tracking_number,
            latitude,
            longitude
        ))

        connection.commit()

        report_id = cursor.lastrowid

        connection.close()

        return render_template(
            "report_success.html",
            report_id=report_id,
            tracking_number=tracking_number
        )

    return render_template("report.html")


# ==================================================
# TRACK STATUS
# ==================================================

@app.route("/track", methods=["GET", "POST"])
def track():

    if not session.get("user_id"):
        return redirect(url_for("login"))

    result = None
    message = None

    if request.method == "POST":

        tracking_number = request.form["tracking_number"].strip().upper()

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        cursor.execute("""
            SELECT
                id, waste_type, location, description, photo,
                status, submitted_at, after_photo, tracking_number
            FROM waste_reports
            WHERE tracking_number = ? AND user_id = ?
        """, (tracking_number, session["user_id"]))

        result = cursor.fetchone()

        connection.close()

        if not result:
            message = "Report not found. Please check your Tracking Number."

    return render_template("track.html", result=result, message=message)


# ==================================================
# MY REPORTS
# ==================================================

@app.route("/my-reports")
def my_reports():

    if not session.get("user_id"):
        return "Please login before viewing your reports."

    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id, waste_type, location, description, photo,
            status, submitted_at, after_photo, tracking_number
        FROM waste_reports
        WHERE user_id = ?
        ORDER BY id DESC
    """, (session["user_id"],))

    reports = cursor.fetchall()

    connection.close()

    return render_template("my_reports.html", reports=reports)


# ==================================================
# UPLOADED FILES
# ==================================================

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ==================================================
# ABOUT, FAQ, CONTACT
# ==================================================

@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/faq")
def faq():
    return render_template("faq.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


# ==================================================
# ADMIN LOGOUT
# ==================================================

@app.route("/admin-logout")
def admin_logout():

    session.pop("admin_id", None)
    session.pop("admin_name", None)
    session.pop("admin_email", None)

    return redirect(url_for("login"))


# ==================================================
# GET ALL REPORTS
# ==================================================

def get_reports():

    connection = sqlite3.connect("waste_system.db")
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            waste_reports.id,
            waste_reports.tracking_number,
            users.name,
            users.email,
            waste_reports.waste_type,
            waste_reports.location,
            waste_reports.description,
            waste_reports.photo,
            waste_reports.status,
            waste_reports.submitted_at,
            waste_reports.after_photo,
            waste_reports.latitude,
            waste_reports.longitude
        FROM waste_reports
        LEFT JOIN users ON waste_reports.user_id = users.id
        ORDER BY waste_reports.id DESC
    """)

    reports = cursor.fetchall()

    connection.close()

    return reports


# ==================================================
# ADMIN DASHBOARD
# ==================================================

@app.route("/admin-dashboard")
def admin_dashboard():

    if not session.get("admin_id"):
        return redirect(url_for("login"))

    reports = get_reports()

    total_reports = len(reports)

    pending_reports = 0
    progress_reports = 0
    resolved_reports = 0

    for report in reports:

        status = report[8]

        if status == "Pending":
            pending_reports += 1
        elif status == "In Progress":
            progress_reports += 1
        elif status == "Resolved":
            resolved_reports += 1

    return render_template(
        "admin_dashboard.html",
        reports=reports,
        total_reports=total_reports,
        pending_reports=pending_reports,
        progress_reports=progress_reports,
        resolved_reports=resolved_reports
    )


# ==================================================
# UPDATE REPORT STATUS
# ==================================================

@app.route("/update-status", methods=["POST"])
def update_status():

    if not session.get("admin_id"):
        return redirect(url_for("login"))

    report_id = request.form["report_id"]
    status = request.form["status"]

    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE waste_reports SET status = ? WHERE id = ?
    """, (status, report_id))

    connection.commit()
    connection.close()

    return redirect(url_for("admin_dashboard"))


# ==================================================
# ADMIN UPLOAD AFTER CLEANING PHOTO
# ==================================================

@app.route("/admin-upload-after-photo/<int:report_id>", methods=["POST"])
def admin_upload_after_photo(report_id):

    if not session.get("admin_id"):
        return redirect(url_for("login"))

    photo = request.files.get("after_photo")

    if not photo or photo.filename == "":
        return redirect(url_for("admin_dashboard"))

    allowed_extensions = {"jpg", "jpeg", "png", "gif", "webp"}

    if "." not in photo.filename:
        return redirect(url_for("admin_dashboard"))

    extension = photo.filename.rsplit(".", 1)[1].lower()

    if extension not in allowed_extensions:
        return redirect(url_for("admin_dashboard"))

    original_filename = secure_filename(photo.filename)

    unique_filename = (
        f"after_{report_id}_"
        f"{int(datetime.now().timestamp())}_"
        f"{original_filename}"
    )

    photo.save(os.path.join(app.config["UPLOAD_FOLDER"], unique_filename))

    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE waste_reports SET after_photo = ? WHERE id = ?
    """, (unique_filename, report_id))

    connection.commit()
    connection.close()

    return redirect(url_for("admin_dashboard"))


# ==================================================
# ADMIN DELETE REPORT
# ==================================================

@app.route("/admin-delete-report/<int:report_id>", methods=["POST"])
def admin_delete_report(report_id):

    if not session.get("admin_id"):
        return redirect(url_for("login"))

    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()

    cursor.execute("""
        SELECT photo, after_photo FROM waste_reports WHERE id = ?
    """, (report_id,))

    report = cursor.fetchone()

    if not report:
        connection.close()
        return "Report not found."

    before_photo = report[0]
    after_photo = report[1]

    cursor.execute("DELETE FROM waste_reports WHERE id = ?", (report_id,))

    connection.commit()
    connection.close()

    # Delete the before-cleaning and after-cleaning photos
    for photo_name in (before_photo, after_photo):

        if photo_name:

            photo_path = os.path.join(
                app.config["UPLOAD_FOLDER"],
                photo_name
            )

            if os.path.exists(photo_path):
                os.remove(photo_path)

    return redirect(url_for("admin_dashboard"))


# ==================================================
# ADMIN SETTINGS
# ==================================================

@app.route("/admin-settings", methods=["GET", "POST"])
def admin_settings():

    if not session.get("admin_id"):
        return redirect(url_for("login"))

    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()

        cursor.execute("""
            SELECT password FROM admins WHERE id = ?
        """, (session["admin_id"],))

        admin = cursor.fetchone()

        if not admin:
            connection.close()
            return render_template(
                "admin_settings.html",
                message="Admin account not found."
            )

        if not verify_password(admin[0], current_password):
            connection.close()
            return render_template(
                "admin_settings.html",
                message="Current password is incorrect."
            )

        if new_password == "":
            connection.close()
            return render_template(
                "admin_settings.html",
                message="New password cannot be empty."
            )

        if new_password != confirm_password:
            connection.close()
            return render_template(
                "admin_settings.html",
                message="New passwords do not match."
            )

        cursor.execute("""
            UPDATE admins SET password = ? WHERE id = ?
        """, (generate_password_hash(new_password), session["admin_id"]))

        connection.commit()
        connection.close()

        return render_template(
            "admin_settings.html",
            success="Admin password changed successfully!"
        )

    return render_template("admin_settings.html")


# ==================================================
# DATABASE CHECK (admin only)
# ==================================================

@app.route("/database-check")
def database_check():

    if not session.get("admin_id"):
        return redirect(url_for("login"))

    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    users_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM waste_reports")
    reports_count = cursor.fetchone()[0]

    connection.close()

    return (
        f"Database connected successfully.<br>"
        f"Users: {users_count}<br>"
        f"Reports: {reports_count}"
    )


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(debug=True)
