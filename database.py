import sqlite3


def create_database():

    connection = sqlite3.connect("waste_system.db")

    cursor = connection.cursor()


    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)


    # Waste Reports table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS waste_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            waste_type TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            photo TEXT,
            after_photo TEXT,
            status TEXT DEFAULT 'Pending',
            submitted_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)


    # Admin table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    """)


    # Create default admin account
    cursor.execute("""
        INSERT OR IGNORE INTO admins
        (name, email, password)
        VALUES (?, ?, ?)
    """, (
        "Administrator",
        "admin@smartwaste.com",
        "admin123"
    ))


    connection.commit()

    connection.close()


create_database()