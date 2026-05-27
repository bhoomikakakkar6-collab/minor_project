import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# ── CORS ─────────────────────────────────────────────────
# FIX 1: Added explicit origins so the browser dashboards on
#         file:// or localhost can actually reach this server.
#         Without this, every fetch() call from the HTML files
#         is blocked by CORS and the dashboards show
#         "⚠ Could not reach appointment server".
CORS(app, resources={r"/*": {"origins": "*"}},
     supports_credentials=True)

# ── Database Config ──────────────────────────────────────
# Uses Supabase Transaction Pooler (port 6543) which supports IPv4
# and works on Render free tier. Direct connection (port 5432) fails
# because Render free tier cannot reach Supabase over IPv6.
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "aws-0-ap-south-1.pooler.supabase.com"),
    "dbname":   os.environ.get("DB_NAME",     "postgres"),
    "user":     os.environ.get("DB_USER",     "postgres.ldnukfbfqjxvzsxggwwt"),
    "password": os.environ.get("DB_PASSWORD", "kakkar3010"),
    "port":     int(os.environ.get("DB_PORT", 6543)),
    "sslmode":  "require"
}

# ── Get Database Connection ──────────────────────────────
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
    conn = cur = None
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
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("Could not connect to DB to create login_history table.")
            return
        cur = conn.cursor()
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
 
def create_appointments_table():
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("Could not connect to DB to create appointments table.")
            return
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id         SERIAL PRIMARY KEY,
                full_name  VARCHAR(255) NOT NULL,
                phone      VARCHAR(50),
                department VARCHAR(100),
                doctor     VARCHAR(100),
                date       DATE,
                status     VARCHAR(20) DEFAULT 'pending',
                reason     TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("Table 'appointments' is ready!")
    except Exception as error:
        print("Error creating appointments table:", error)
        if conn: conn.rollback()
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

def create_patients_table():
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            print("Could not connect to DB to create patients table.")
            return
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                id         SERIAL PRIMARY KEY,
                name       VARCHAR(255) NOT NULL,
                phone      VARCHAR(50),
                age        INTEGER,
                gender     VARCHAR(20),
                relation   VARCHAR(100),
                condition  TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("Table 'patients' is ready!")
    except Exception as error:
        print("Error creating patients table:", error)
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
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if not any(c.isdigit() for c in password):
        return jsonify({"error": "Password must contain at least one number."}), 400
    if not any(c.islower() for c in password):
        return jsonify({"error": "Password must contain at least one lowercase letter."}), 400

    conn = cur = None
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

    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute("SELECT * FROM server WHERE username = %s", (email,))
        user = cur.fetchone()

        if user and check_password_hash(user['password'], password):
            ip_address = request.remote_addr
            cur.execute(
                "SELECT COUNT(*) FROM login_history WHERE email = %s", (email,)
            )
            count = cur.fetchone()[0]
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
@app.route('/record_login', methods=['POST'])
def record_login():
    """Record a login event without password validation.
    Called by the frontend after localStorage-based auth succeeds."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON body."}), 400
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({"error": "Email is required."}), 400
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        ip_address = request.remote_addr
        cur.execute(
            "INSERT INTO login_history (email, ip_address) VALUES (%s, %s)",
            (email, ip_address)
        )
        cur.execute(
            "SELECT COUNT(*) FROM login_history WHERE email = %s", (email,)
        )
        count = cur.fetchone()[0]
        conn.commit()
        return jsonify({"message": "Login recorded.", "login_count": count}), 200
    except Exception as error:
        print("Record login error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Failed to record login."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

@app.route('/delete_user', methods=['DELETE'])
def delete_user():
    data  = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()

    if not email:
        return jsonify({"error": "Email is required."}), 400

    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute("DELETE FROM login_history WHERE email = %s", (email,))
        cur.execute("DELETE FROM server WHERE username = %s", (email,))
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
@app.route('/login_history', methods=['GET'])
def login_counter():
    conn = cur = None
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

# ════════════════════════════════════════════════════════
#  APPOINTMENT ROUTES  (used by doctor_dashboard.html)
# ════════════════════════════════════════════════════════

# FIX 2a: GET /appointments — fetches all appointments
@app.route('/appointments', methods=['GET'])
def get_appointments():
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute("SELECT * FROM appointments ORDER BY created_at DESC")
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as error:
        print("Get appointments error:", error)
        return jsonify({"error": "Failed to fetch appointments."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# FIX 2b: POST /appointments — book a new appointment
@app.route('/appointments', methods=['POST'])
def book_appointment():
    data = request.get_json() or {}
    full_name  = (data.get('full_name')  or '').strip()
    phone      = (data.get('phone')      or '').strip()
    department = (data.get('department') or '').strip()
    doctor     = (data.get('doctor')     or '').strip()
    date       = data.get('date')

    if not full_name or not date:
        return jsonify({"error": "full_name and date are required."}), 400

    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO appointments (full_name, phone, department, doctor, date)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (full_name, phone, department, doctor, date))
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"success": True, "id": new_id, "message": "Appointment booked."}), 201
    except Exception as error:
        print("Book appointment error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Failed to book appointment."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# FIX 2c: POST /appointment/<id>/accept
@app.route('/appointment/<int:appt_id>/accept', methods=['POST'])
def accept_appointment(appt_id):
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute(
            "UPDATE appointments SET status='accepted' WHERE id=%s",
            (appt_id,)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"success": False, "message": "Appointment not found."}), 404
        conn.commit()
        return jsonify({"success": True, "message": "Appointment accepted."}), 200
    except Exception as error:
        print("Accept appointment error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Failed to accept appointment."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# FIX 2d: POST /appointment/<id>/reject
@app.route('/appointment/<int:appt_id>/reject', methods=['POST'])
def reject_appointment(appt_id):
    data   = request.get_json() or {}
    reason = (data.get('reason') or 'Rejected by doctor').strip()

    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute(
            "UPDATE appointments SET status='rejected', reason=%s WHERE id=%s",
            (reason, appt_id)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"success": False, "message": "Appointment not found."}), 404
        conn.commit()
        return jsonify({"success": True, "message": "Appointment rejected."}), 200
    except Exception as error:
        print("Reject appointment error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Failed to reject appointment."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# FIX 2e: POST /appointment/<id>/reset — resets status back to pending
@app.route('/appointment/<int:appt_id>/reset', methods=['POST'])
def reset_appointment(appt_id):
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute(
            "UPDATE appointments SET status='pending', reason=NULL WHERE id=%s",
            (appt_id,)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return jsonify({"success": False, "message": "Appointment not found."}), 404
        conn.commit()
        return jsonify({"success": True, "message": "Appointment reset to pending."}), 200
    except Exception as error:
        print("Reset appointment error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Failed to reset appointment."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ════════════════════════════════════════════════════════
#  PATIENT ROUTES  (used by doctor_dashboard.html &
#                   admin_dashboard.html)
# ════════════════════════════════════════════════════════

# FIX 3a: GET /get-all-patients
@app.route('/get-all-patients', methods=['GET'])
def get_all_patients():
    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute("SELECT * FROM patients ORDER BY created_at DESC")
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as error:
        print("Get patients error:", error)
        return jsonify({"error": "Failed to fetch patients."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# FIX 3b: GET /get-patient?name=...
# admin_dashboard.html pings this route to check if the server is alive.
@app.route('/get-patient', methods=['GET'])
def get_patient():
    name = (request.args.get('name') or '').strip()

    # Ping check used by admin_dashboard health-check
    if name == '__ping__':
        return jsonify({"message": "pong"}), 200

    if not name:
        return jsonify({"error": "name query param required."}), 400

    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM patients WHERE name ILIKE %s ORDER BY created_at DESC",
            (f"%{name}%",)
        )
        rows = cur.fetchall()
        return jsonify([dict(r) for r in rows]), 200
    except Exception as error:
        print("Get patient error:", error)
        return jsonify({"error": "Failed to fetch patient."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# FIX 3c: POST /add-patient
@app.route('/add-patient', methods=['POST'])
def add_patient():
    data      = request.get_json() or {}
    name      = (data.get('name')      or '').strip()
    phone     = (data.get('phone')     or '').strip()
    age       = data.get('age')
    gender    = (data.get('gender')    or '').strip()
    relation  = (data.get('relation')  or '').strip()
    condition = (data.get('condition') or '').strip() or None

    if not name:
        return jsonify({"error": "name is required."}), 400

    conn = cur = None
    try:
        conn = get_db_connection()
        if conn is None:
            return jsonify({"error": "Database connection failed."}), 500
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO patients (name, phone, age, gender, relation, condition)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (name, phone, age, gender, relation, condition))
        new_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({"success": True, "id": new_id, "message": "Patient registered."}), 201
    except Exception as error:
        print("Add patient error:", error)
        if conn: conn.rollback()
        return jsonify({"error": "Failed to add patient."}), 500
    finally:
        if cur  is not None: cur.close()
        if conn is not None: conn.close()

# ── FIX 4: Port mismatch ─────────────────────────────────
# Both HTML dashboards call http://localhost:5002, but the
# original script started Flask on port 5002 yet the print
# banner said "Server: http://localhost:5001" — misleading
# and easy to start on the wrong port.  Both now say 5002.
# ── Initialize Tables on startup (runs under gunicorn too) ──
create_table()
create_login_history_table()
create_appointments_table()
create_patients_table()

if __name__ == '__main__':
    print("----------------------------------")
    print("Server  : http://localhost:5002")
    print("Handles : Auth, Appointments, Patients, Login History")
    print("----------------------------------")
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)