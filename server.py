import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras

app = Flask(__name__)
CORS(app, resources={r"/*": {
    "origins": "*",
    "methods": ["GET", "POST", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"]
}})

# ── Database Config ──────────────────────────────────────
# Use environment variables so the password isn't hardcoded
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST", "localhost"),
    "dbname":   os.environ.get("DB_NAME", "postgres"),
    "user":     os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "port":     int(os.environ.get("DB_PORT", 5432))
}

# ── Get Database Connection ──────────────────────────────
# FIX 1: Added try/except so a DB failure returns None instead of crashing
def get_db_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.cursor_factory = psycopg2.extras.DictCursor
        return conn
    except Exception as e:
        print("Database connection failed:", e)
        return None

# ── Create Tables ────────────────────────────────────────
def create_table():
    conn = None
    cur  = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("Could not connect to DB to create tables.")
            return
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS server (
                id       SERIAL PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        """)
        conn.commit()
        print("Table 'server' is ready!")

    except Exception as error:
        print("Error creating table:", error)
        if conn: conn.rollback()

    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ── Create Login History Table ───────────────────────────
def create_login_history_table():
    conn = None
    cur  = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("Could not connect to DB to create login_history table.")
            return
        cur = conn.cursor()
        # FIX 2: Removed login_count column — it was referenced in INSERT but
        #         never defined in the table, crashing every login attempt.
        #         Login count is now derived by COUNT(*) in the /login_history route.
        cur.execute("""
            CREATE TABLE IF NOT EXISTS login_history (
                id         SERIAL PRIMARY KEY,
                email      VARCHAR(255) NOT NULL,
                login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address VARCHAR(50)
            )
        """)
        conn.commit()
        print("Table 'login_history' is ready!")

    except Exception as error:
        print("Error creating login_history table:", error)
        if conn: conn.rollback()

    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ── Register Route ───────────────────────────────────────
@app.route('/create-user', methods=['POST'])
def create_user():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({"error": "Invalid email format."}), 400

    # Password strength checks — FIX 3: aligned with frontend (both now require 8)
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if not any(c.isdigit() for c in password):
        return jsonify({"error": "Password must contain at least one number."}), 400
    if not any(c.islower() for c in password):
        return jsonify({"error": "Password must contain at least one lowercase letter."}), 400

    conn = None
    cur  = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM server WHERE username = %s", (email,))
        if cur.fetchone():
            return jsonify({"error": "This email is already registered."}), 409

        hashed = generate_password_hash(password)
        cur.execute(
            "INSERT INTO server (username, password) VALUES (%s, %s)",
            (email, hashed)
        )
        conn.commit()
        return jsonify({"message": "User registered successfully!"}), 201

    except Exception as error:
        print("Register error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Registration failed."}), 500

    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ── Login Route ──────────────────────────────────────────
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400

    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    conn = None
    cur  = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()

        cur.execute("SELECT * FROM server WHERE username = %s", (email,))
        user = cur.fetchone()

        if user and check_password_hash(user['password'], password):
            ip_address = request.remote_addr

            # Count this user's previous logins
            cur.execute(
                "SELECT COUNT(*) FROM login_history WHERE email = %s", (email,)
            )
            count = cur.fetchone()[0]

            # FIX 2: INSERT without login_count — column doesn't exist in table
            cur.execute(
                "INSERT INTO login_history (email, ip_address) VALUES (%s, %s)",
                (email, ip_address)
            )
            conn.commit()
            return jsonify({
                "message":     "Login successful!",
                "login_count": count + 1
            }), 200
        else:
            return jsonify({"error": "Invalid email or password."}), 401

    except Exception as error:
        print("Login error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Login failed."}), 500

    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ── Delete User Route ────────────────────────────────────
@app.route('/delete_user', methods=['DELETE', 'OPTIONS'])
def delete_user():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    data  = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()

    if not email:
        return jsonify({"error": "Email is required."}), 400

    conn = None
    cur  = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()

        # FIX 4: Also delete login history so no orphan records remain
        cur.execute("DELETE FROM login_history WHERE email = %s", (email,))

        cur.execute("DELETE FROM server WHERE username = %s", (email,))

        # FIX 5: Check if the user actually existed before claiming success
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"error": "User not found."}), 404

        conn.commit()
        return jsonify({"message": f"User {email} deleted successfully."}), 200

    except Exception as error:
        print("Delete error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Delete failed."}), 500

    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ── Login History Route ──────────────────────────────────
@app.route('/login_history', methods=['GET', 'OPTIONS'])
def login_counter():
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    conn = None
    cur  = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute("""
            SELECT email, COUNT(*) as total_logins
            FROM login_history
            GROUP BY email
            ORDER BY total_logins DESC
        """)
        rows   = cur.fetchall()
        result = [{"email": row['email'], "total_logins": row['total_logins']} for row in rows]
        return jsonify(result), 200

    except Exception as error:
        print("Login history error:", error)
        return jsonify({"error": "Failed to fetch login history."}), 500

    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ── Initialize Tables on startup (runs under gunicorn too) ──
create_table()
create_login_history_table()

# ── Run Server ───────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)