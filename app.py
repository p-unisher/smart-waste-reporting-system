from flask import Flask, render_template, request, session, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename
import os
import database
import sqlite3
import random
from datetime import datetime


app = Flask(__name__)

app.secret_key = "smart_waste_secret_key"


# ==================================================
# UPLOAD FOLDER
# ==================================================

UPLOAD_FOLDER = "uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# Create upload folder if it does not exist

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


    # Add submitted_at column

    try:

        cursor.execute("""
            ALTER TABLE waste_reports
            ADD COLUMN submitted_at TEXT
        """)

    except sqlite3.OperationalError:

        pass


    # Add after_photo column

    try:

        cursor.execute("""
            ALTER TABLE waste_reports
            ADD COLUMN after_photo TEXT
        """)

    except sqlite3.OperationalError:

        pass


    # Add tracking_number column

    try:

        cursor.execute("""
            ALTER TABLE waste_reports
            ADD COLUMN tracking_number TEXT
        """)

    except sqlite3.OperationalError:

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
        INSERT OR IGNORE INTO report_counter
        (id, next_number)
        VALUES (1, 1)
    """)


    connection.commit()
    connection.close()


except sqlite3.OperationalError:

    pass


# ==================================================
# HOME
# ==================================================

@app.route("/")
def home():

    return render_template("index.html")


# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            SELECT *
            FROM users
            WHERE email = ? AND password = ?
        """, (
            email,
            password
        ))


        user = cursor.fetchone()

        connection.close()


        if user:

            session["user_id"] = user[0]
            session["user_name"] = user[1]
            session["user_email"] = user[2]


            return render_template(
                "index.html",
                message="Login successful!"
            )


        else:

            return render_template(
                "login.html",
                message="Invalid email or password."
            )


    return render_template("login.html")


# ==================================================
# REGISTER
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (
            email,
        ))


        existing_user = cursor.fetchone()


        if existing_user:

            connection.close()


            return render_template(
                "register.html",
                message="Email already registered."
            )


        cursor.execute("""
            INSERT INTO users
            (name, email, phone, password)
            VALUES (?, ?, ?, ?)
        """, (
            name,
            email,
            phone,
            password
        ))


        connection.commit()
        connection.close()


        return render_template(
            "login.html",
            message="Registration successful! Please login."
        )


    return render_template("register.html")


# ==================================================
# FORGOT PASSWORD
# ==================================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if request.method == "POST":

        email = request.form["email"]


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            SELECT *
            FROM users
            WHERE email = ?
        """, (
            email,
        ))


        user = cursor.fetchone()

        connection.close()


        if not user:

            return render_template(
                "forgot_password.html",
                message="Email not found."
            )


        otp = random.randint(100000, 999999)


        session["reset_email"] = email
        session["reset_otp"] = str(otp)


        print("--------------------------------")
        print("PASSWORD RESET OTP:", otp)
        print("--------------------------------")


        return redirect(url_for("verify_otp"))


    return render_template("forgot_password.html")


# ==================================================
# VERIFY OTP
# ==================================================

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():

    if request.method == "POST":

        entered_otp = request.form["otp"]

        saved_otp = session.get("reset_otp")


        if saved_otp and entered_otp == saved_otp:

            session["otp_verified"] = True

            return redirect(url_for("reset_password"))


        else:

            return render_template(
                "verify_otp.html",
                message="Invalid OTP."
            )


    return render_template("verify_otp.html")


# ==================================================
# RESET PASSWORD
# ==================================================

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():

    if not session.get("otp_verified"):

        return "Please verify OTP first."


    if request.method == "POST":

        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]


        if new_password != confirm_password:

            return render_template(
                "reset_password.html",
                message="Passwords do not match."
            )


        if new_password == "":

            return render_template(
                "reset_password.html",
                message="Password cannot be empty."
            )


        email = session.get("reset_email")


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            UPDATE users
            SET password = ?
            WHERE email = ?
        """, (
            new_password,
            email
        ))


        connection.commit()
        connection.close()


        session.pop("reset_email", None)
        session.pop("reset_otp", None)
        session.pop("otp_verified", None)


        return render_template(
            "login.html",
            message="Password reset successfully! Please login."
        )


    return render_template("reset_password.html")


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
            SELECT password
            FROM users
            WHERE id = ?
        """, (
            session["user_id"],
        ))


        user = cursor.fetchone()


        if not user:

            connection.close()


            return render_template(
                "change_password.html",
                message="User account not found."
            )


        if current_password != user[0]:

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
            UPDATE users
            SET password = ?
            WHERE id = ?
        """, (
            new_password,
            session["user_id"]
        ))


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


        photo = request.files.get("photo")

        filename = None


        allowed_extensions = {
            "jpg",
            "jpeg",
            "png",
            "gif",
            "webp"
        }


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
                os.path.join(
                    app.config["UPLOAD_FOLDER"],
                    filename
                )
            )


        submitted_at = datetime.now().strftime(
            "%d-%m-%Y %I:%M %p"
        )


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        # Get next unique tracking number

        cursor.execute("""
            SELECT next_number
            FROM report_counter
            WHERE id = 1
        """)


        counter = cursor.fetchone()


        next_number = counter[0]


        tracking_number = f"WR{next_number:03d}"


        # Increase counter

        cursor.execute("""
            UPDATE report_counter
            SET next_number = ?
            WHERE id = 1
        """, (
            next_number + 1,
        ))


        # Insert report

        cursor.execute("""
            INSERT INTO waste_reports
            (
                user_id,
                waste_type,
                location,
                description,
                photo,
                status,
                submitted_at,
                tracking_number
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["user_id"],
            waste_type,
            location,
            description,
            filename,
            "Pending",
            submitted_at,
            tracking_number
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
                id,
                waste_type,
                location,
                description,
                photo,
                status,
                submitted_at,
                after_photo,
                tracking_number
            FROM waste_reports
            WHERE tracking_number = ?
            AND user_id = ?
        """, (
            tracking_number,
            session["user_id"]
        ))

        result = cursor.fetchone()

        connection.close()

        if not result:
            message = "Report not found. Please check your Tracking Number."

    return render_template(
        "track.html",
        result=result,
        message=message
    )


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
            id,
            waste_type,
            location,
            description,
            photo,
            status,
            submitted_at,
            after_photo,
            tracking_number
        FROM waste_reports
        WHERE user_id = ?
        ORDER BY id DESC
    """, (
        session["user_id"],
    ))


    reports = cursor.fetchall()


    connection.close()


    return render_template(
        "my_reports.html",
        reports=reports
    )


# ==================================================
# UPLOADED FILES
# ==================================================

@app.route("/uploads/<filename>")
def uploaded_file(filename):

    return send_from_directory(
        app.config["UPLOAD_FOLDER"],
        filename
    )


# ==================================================
# ABOUT
# ==================================================

@app.route("/about")
def about():

    return render_template("about.html")


# ==================================================
# FAQ
# ==================================================

@app.route("/faq")
def faq():

    return render_template("faq.html")


# ==================================================
# CONTACT
# ==================================================

@app.route("/contact")
def contact():

    return render_template("contact.html")


# ==================================================
# ADMIN SECTION
# ==================================================


# ==================================================
# ADMIN LOGIN
# ==================================================

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            SELECT *
            FROM admins
            WHERE email = ? AND password = ?
        """, (
            email,
            password
        ))


        admin = cursor.fetchone()


        connection.close()


        if admin:

            session["admin_id"] = admin[0]
            session["admin_name"] = admin[1]
            session["admin_email"] = admin[2]


            return redirect(url_for("admin_dashboard"))


        else:

            return render_template(
                "admin_login.html",
                message="Invalid admin email or password."
            )


    return render_template("admin_login.html")


# ==================================================
# ADMIN FORGOT PASSWORD
# ==================================================

@app.route("/admin-forgot-password", methods=["GET", "POST"])
def admin_forgot_password():

    if request.method == "POST":

        email = request.form["email"].strip()


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            SELECT id
            FROM admins
            WHERE email = ?
        """, (
            email,
        ))


        admin = cursor.fetchone()


        connection.close()


        if not admin:

            return render_template(
                "admin_forgot_password.html",
                message="Admin email not found."
            )


        otp = random.randint(100000, 999999)


        session["admin_reset_email"] = email
        session["admin_reset_otp"] = str(otp)


        print("--------------------------------")
        print("ADMIN PASSWORD RESET OTP:", otp)
        print("--------------------------------")


        return redirect(url_for("admin_verify_otp"))


    return render_template("admin_forgot_password.html")


# ==================================================
# ADMIN VERIFY OTP
# ==================================================

@app.route("/admin-verify-otp", methods=["GET", "POST"])
def admin_verify_otp():

    if not session.get("admin_reset_email"):

        return redirect(url_for("admin_forgot_password"))


    if request.method == "POST":

        entered_otp = request.form["otp"]

        saved_otp = session.get("admin_reset_otp")


        if saved_otp and entered_otp == saved_otp:

            session["admin_otp_verified"] = True

            return redirect(url_for("admin_reset_password"))


        else:

            return render_template(
                "admin_verify_otp.html",
                message="Invalid OTP."
            )


    return render_template("admin_verify_otp.html")


# ==================================================
# ADMIN RESET PASSWORD
# ==================================================

@app.route("/admin-reset-password", methods=["GET", "POST"])
def admin_reset_password():

    if not session.get("admin_otp_verified"):

        return "Please verify OTP first."


    if request.method == "POST":

        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]


        if new_password == "":

            return render_template(
                "admin_reset_password.html",
                message="Password cannot be empty."
            )


        if new_password != confirm_password:

            return render_template(
                "admin_reset_password.html",
                message="Passwords do not match."
            )


        email = session.get("admin_reset_email")


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            UPDATE admins
            SET password = ?
            WHERE email = ?
        """, (
            new_password,
            email
        ))


        connection.commit()
        connection.close()


        session.pop("admin_reset_email", None)
        session.pop("admin_reset_otp", None)
        session.pop("admin_otp_verified", None)


        return render_template(
            "admin_login.html",
            message="Admin password reset successfully! Please login."
        )


    return render_template("admin_reset_password.html")


# ==================================================
# ADMIN LOGOUT
# ==================================================

@app.route("/admin-logout")
def admin_logout():

    session.pop("admin_id", None)
    session.pop("admin_name", None)
    session.pop("admin_email", None)


    return redirect(url_for("admin_login"))


# ==================================================
# GET ALL REPORTS
# ==================================================

def get_reports():

    connection = sqlite3.connect("waste_system.db")
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
            waste_reports.after_photo
        FROM waste_reports
        LEFT JOIN users
        ON waste_reports.user_id = users.id
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

        return redirect(url_for("admin_login"))


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

        return redirect(url_for("admin_login"))


    report_id = request.form["report_id"]
    status = request.form["status"]


    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()


    cursor.execute("""
        UPDATE waste_reports
        SET status = ?
        WHERE id = ?
    """, (
        status,
        report_id
    ))


    connection.commit()
    connection.close()


    return redirect(url_for("admin_dashboard"))


# ==================================================
# ADMIN UPLOAD AFTER CLEANING PHOTO
# ==================================================

@app.route("/admin-upload-after-photo/<int:report_id>", methods=["POST"])
def admin_upload_after_photo(report_id):

    if not session.get("admin_id"):

        return redirect(url_for("admin_login"))


    photo = request.files.get("after_photo")


    if not photo or photo.filename == "":

        return redirect(url_for("admin_dashboard"))


    allowed_extensions = {
        "jpg",
        "jpeg",
        "png",
        "gif",
        "webp"
    }


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


    photo_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        unique_filename
    )


    photo.save(photo_path)


    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()


    cursor.execute("""
        UPDATE waste_reports
        SET after_photo = ?
        WHERE id = ?
    """, (
        unique_filename,
        report_id
    ))


    connection.commit()
    connection.close()


    return redirect(url_for("admin_dashboard"))


# ==================================================
# ADMIN DELETE REPORT
# ==================================================

@app.route("/admin-delete-report/<int:report_id>", methods=["POST"])
def admin_delete_report(report_id):

    if not session.get("admin_id"):

        return redirect(url_for("admin_login"))


    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()


    cursor.execute("""
        SELECT photo, after_photo
        FROM waste_reports
        WHERE id = ?
    """, (
        report_id,
    ))


    report = cursor.fetchone()


    if not report:

        connection.close()

        return "Report not found."


    before_photo = report[0]
    after_photo = report[1]


    cursor.execute("""
        DELETE FROM waste_reports
        WHERE id = ?
    """, (
        report_id,
    ))


    connection.commit()
    connection.close()


    # Delete before-cleaning photo

    if before_photo:

        photo_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            before_photo
        )


        if os.path.exists(photo_path):

            os.remove(photo_path)


    # Delete after-cleaning photo

    if after_photo:

        after_photo_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            after_photo
        )


        if os.path.exists(after_photo_path):

            os.remove(after_photo_path)


    return redirect(url_for("admin_dashboard"))


# ==================================================
# ADMIN SETTINGS
# ==================================================

@app.route("/admin-settings", methods=["GET", "POST"])
def admin_settings():

    if not session.get("admin_id"):

        return redirect(url_for("admin_login"))


    if request.method == "POST":

        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]


        connection = sqlite3.connect("waste_system.db")
        cursor = connection.cursor()


        cursor.execute("""
            SELECT password
            FROM admins
            WHERE id = ?
        """, (
            session["admin_id"],
        ))


        admin = cursor.fetchone()


        if not admin:

            connection.close()


            return render_template(
                "admin_settings.html",
                message="Admin account not found."
            )


        if current_password != admin[0]:

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
            UPDATE admins
            SET password = ?
            WHERE id = ?
        """, (
            new_password,
            session["admin_id"]
        ))


        connection.commit()
        connection.close()


        return render_template(
            "admin_settings.html",
            success="Admin password changed successfully!"
        )


    return render_template("admin_settings.html")


# ==================================================
# DATABASE CHECK
# ==================================================

@app.route("/database-check")
def database_check():

    connection = sqlite3.connect("waste_system.db")
    cursor = connection.cursor()


    cursor.execute("""
        SELECT *
        FROM users
    """)


    users = cursor.fetchall()


    connection.close()


    return str(users)


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    app.run(debug=True)