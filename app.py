import sqlite3
import os
import secrets
from datetime import timedelta
from functools import wraps

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    send_from_directory,
    url_for,
    abort,
    jsonify
)

from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.security import generate_password_hash, check_password_hash

# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

app.secret_key = "mysecretkey"
app.permanent_session_lifetime = timedelta(minutes=30)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

@app.before_request
def csrf_protect():
    if request.method == "POST":
        token = session.get('csrf_token', None)
        if not token or token != request.form.get('csrf_token'):
            abort(403)

def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(16)
    return session['csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in roles and not any(
                admin_previewing(role_name) for role_name in roles
            ):
                return portal_redirect()
            return f(*args, **kwargs)
        return decorated_function
    return decorator

app.jinja_loader = ChoiceLoader([
    app.jinja_loader,
    FileSystemLoader(app.root_path)
])


# =========================================================
# DATABASE
# =========================================================

# food.db will be created beside app.py
DATABASE = os.path.join(app.root_path, "food.db")

ROLE_ADMIN = "Admin"
ROLE_CUSTOMER = "Customer"
ROLE_DELIVERY = "Delivery Partner"

ORDER_STATUSES = (
    "Pending",
    "Placed",
    "Preparing",
    "Dispatched",
    "Picked Up",
    "Out for Delivery",
    "Delivered",
    "Cancelled",
)

DELIVERY_STATUSES = ("Available", "Busy", "Offline")


def portal_redirect():
    """Return a user to the only portal their current role may use."""
    role = session.get("role")
    if role == ROLE_ADMIN:
        return redirect(url_for("admin_dashboard"))
    if role == ROLE_DELIVERY:
        return redirect(url_for("delivery_dashboard"))
    if role == ROLE_CUSTOMER:
        return redirect(url_for("customer_dashboard"))
    return redirect(url_for("login"))


def admin_previewing(role_name):
    return (
        session.get("role") == ROLE_ADMIN
        and session.get("portal_preview") == role_name
    )


def public_access(f):
    """Allow guests/customers to browse; keep staff inside their own portal."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        role = session.get("role")
        if role == ROLE_DELIVERY:
            return portal_redirect()
        if role == ROLE_ADMIN and not admin_previewing(ROLE_CUSTOMER):
            return portal_redirect()
        return f(*args, **kwargs)
    return decorated_function


def actual_role_required(*roles):
    """Require a real signed-in role; admin previews remain read-only."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get("role") not in roles:
                return portal_redirect()
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_db():
    conn = sqlite3.connect(DATABASE)

    # Allows us to use:
    # user["user_name"]
    # instead of:
    # user[1]
    conn.row_factory = sqlite3.Row

    # Turn on foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def add_column_if_missing(conn, table_name, column_name, definition):
    """Apply a small, idempotent migration to an existing SQLite database."""
    columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )


def get_role_id(conn, role_name):
    role = conn.execute(
        "SELECT role_id FROM roles WHERE role_name = ?", (role_name,)
    ).fetchone()
    return role["role_id"] if role else None


def ensure_delivery_partner(conn, user_id):
    """Return the delivery profile, creating it for legacy partner accounts."""
    partner = conn.execute(
        "SELECT * FROM delivery_partners WHERE user_id = ?", (user_id,)
    ).fetchone()
    if partner:
        return partner

    conn.execute(
        """
        INSERT INTO delivery_partners (user_id, availability_status)
        VALUES (?, 'Offline')
        """,
        (user_id,),
    )
    conn.commit()
    return conn.execute(
        "SELECT * FROM delivery_partners WHERE user_id = ?", (user_id,)
    ).fetchone()


def get_current_customer(conn):
    return conn.execute(
        "SELECT * FROM customers WHERE user_id = ?", (session["user_id"],)
    ).fetchone()


def get_current_partner(conn):
    return conn.execute(
        """
        SELECT dp.*, u.user_name, u.user_email, u.phone
        FROM delivery_partners dp
        JOIN users u ON u.user_id = dp.user_id
        WHERE dp.user_id = ?
        """,
        (session["user_id"],),
    ).fetchone()


def add_notification(conn, user_id, title, message, notification_type="system"):
    conn.execute(
        """
        INSERT INTO notifications (user_id, notification_type, title, message)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, notification_type, title, message),
    )


# =========================================================
# CREATE DATABASE TABLES
# =========================================================

def init_db():

    conn = get_db()
    cursor = conn.cursor()

    # -----------------------------------------------------
    # ROLES TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            role_id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name VARCHAR(50) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -----------------------------------------------------
    # USERS TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name VARCHAR(50) NOT NULL,
            user_email VARCHAR(100) NOT NULL UNIQUE,
            user_pass VARCHAR(255) NOT NULL,
            phone VARCHAR(20) NOT NULL,
            role_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (role_id)
            REFERENCES roles(role_id)
        )
    """)

    # -----------------------------------------------------
    # CUSTOMERS TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            address TEXT,
            preferences TEXT,

            FOREIGN KEY (user_id)
            REFERENCES users(user_id)
        )
    """)

    # -----------------------------------------------------
    # ORDERS TABLE
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_details TEXT NOT NULL,
            total_amount DECIMAL(10, 2),
            status VARCHAR(50) DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    """)

    # -----------------------------------------------------
    # DELIVERY PARTNERS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_partners (
            partner_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            vehicle_type VARCHAR(100) DEFAULT 'Bicycle',
            license_number VARCHAR(100),
            availability_status VARCHAR(30) NOT NULL DEFAULT 'Offline',
            current_lat DECIMAL(10, 7),
            current_lng DECIMAL(10, 7),
            rating DECIMAL(3, 2) NOT NULL DEFAULT 5.0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # -----------------------------------------------------
    # DELIVERY ASSIGNMENTS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            partner_id INTEGER NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'Assigned',
            payout DECIMAL(10, 2) NOT NULL DEFAULT 0,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accepted_at TIMESTAMP,
            picked_up_at TIMESTAMP,
            delivered_at TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (partner_id) REFERENCES delivery_partners(partner_id)
        )
    """)

    # -----------------------------------------------------
    # GPS LOCATION LOGS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS location_logs (
            location_id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            latitude DECIMAL(10, 7) NOT NULL,
            longitude DECIMAL(10, 7) NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assignment_id) REFERENCES delivery_assignments(assignment_id)
        )
    """)

    # -----------------------------------------------------
    # NOTIFICATIONS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            notification_type VARCHAR(50) NOT NULL DEFAULT 'system',
            title VARCHAR(150) NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # -----------------------------------------------------
    # FEEDBACK AND RATINGS
    # -----------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL UNIQUE,
            customer_id INTEGER NOT NULL,
            delivery_partner_id INTEGER,
            restaurant_rating INTEGER NOT NULL CHECK (restaurant_rating BETWEEN 1 AND 5),
            delivery_rating INTEGER NOT NULL CHECK (delivery_rating BETWEEN 1 AND 5),
            comments TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (delivery_partner_id) REFERENCES delivery_partners(partner_id)
        )
    """)

    # These columns keep delivery information attached to the order while
    # remaining compatible with the original database shipped with the app.
    add_column_if_missing(conn, "orders", "restaurant_name", "VARCHAR(150) DEFAULT 'ispice majesty'")
    add_column_if_missing(conn, "orders", "pickup_address", "TEXT DEFAULT '845 Grand Avenue, Culinary District'")
    add_column_if_missing(conn, "orders", "delivery_address", "TEXT")
    add_column_if_missing(conn, "orders", "delivery_notes", "TEXT")

    # -----------------------------------------------------
    # ADD ROLES
    # -----------------------------------------------------

    cursor.execute("""
        INSERT OR IGNORE INTO roles (role_name)
        VALUES (?)
    """, (ROLE_ADMIN,))

    cursor.execute("""
        INSERT OR IGNORE INTO roles (role_name)
        VALUES (?)
    """, (ROLE_CUSTOMER,))

    cursor.execute("""
        INSERT OR IGNORE INTO roles (role_name)
        VALUES (?)
    """, (ROLE_DELIVERY,))

    conn.commit()
    conn.close()


# Create database automatically
init_db()


# =========================================================
# HOME
# =========================================================

@app.route("/")
@public_access
def home():
    return render_template("index.html")


# =========================================================
# PUBLIC PAGES
# =========================================================

@app.route("/rest")
@public_access
def rest():
    return render_template("customer/restaurants.html")


@app.route("/menu")
@public_access
def menu():
    return render_template("public/menu.html")


@app.route("/about")
@public_access
def about():
    return render_template("public/about.html")


@app.route("/faq")
@public_access
def faq():
    return render_template("public/faq.html")


@app.route("/contact")
@public_access
def contact():
    return render_template("public/contact.html")


@app.route("/public/index")
@public_access
def public_index():
    return render_template("public/index.html")


@app.route("/public/menu")
@public_access
def public_menu():
    return render_template("public/menu.html")


@app.route("/public/reserve")
@public_access
def public_reserve():
    return render_template("public/reserve.html")


@app.route("/public/track")
@public_access
def public_track():
    return render_template("public/track.html")


@app.route("/public/privacy")
@public_access
def public_privacy():
    return render_template("public/privacy.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "GET" and session.get("user_id") and session.get("role") != ROLE_CUSTOMER:
        return portal_redirect()

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")

        conn = get_db()

        user = conn.execute("""
            SELECT
                users.*,
                roles.role_name
            FROM users
            JOIN roles
                ON users.role_id = roles.role_id
            WHERE users.user_email = ?
        """, (email,)).fetchone()

        conn.close()

        # Check user and password
        if user and password and check_password_hash(
            user["user_pass"],
            password
        ):

            if user["role_name"] == ROLE_DELIVERY:
                partner = ensure_delivery_partner(conn, user["user_id"])
                if not partner["is_active"]:
                    conn.close()
                    return render_template(
                        "auth/login.html",
                        error="This delivery partner account is currently inactive.",
                    )
                if partner["availability_status"] == "Offline":
                    conn.execute(
                        "UPDATE delivery_partners SET availability_status = 'Available', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
                        (partner["partner_id"],),
                    )
                    conn.commit()

            # Save user information in session
            session.clear()
            session.permanent = True
            session["user_id"] = user["user_id"]
            session["user_name"] = user["user_name"]
            session["role"] = user["role_name"]

            # Go to correct dashboard

            if user["role_name"] == ROLE_ADMIN:
                return redirect(url_for("admin_dashboard"))

            elif user["role_name"] == ROLE_DELIVERY:
                return redirect(url_for("delivery_dashboard"))

            else:
                return redirect(url_for("customer_dashboard"))

        return render_template(
            "auth/login.html",
            error="Invalid email or password"
        )

    return render_template("auth/login.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if session.get("role") in (ROLE_ADMIN, ROLE_DELIVERY):
        return portal_redirect()

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")
        phone = request.form.get("phone", "").strip()

        # Check fields
        if not name or not email or not password or not phone:

            return render_template(
                "auth/register.html",
                error="Please fill all fields"
            )

        conn = get_db()

        # Check if email already exists
        existing_user = conn.execute("""
            SELECT user_id
            FROM users
            WHERE user_email = ?
        """, (email,)).fetchone()

        if existing_user:

            conn.close()

            return render_template(
                "auth/register.html",
                error="Email already registered"
            )

        # Get Customer role
        role = conn.execute("""
            SELECT role_id
            FROM roles
            WHERE role_name = ?
        """, (ROLE_CUSTOMER,)).fetchone()

        # Hash password
        hashed_password = generate_password_hash(password)

        # Create user
        cursor = conn.execute("""
            INSERT INTO users (
                user_name,
                user_email,
                user_pass,
                phone,
                role_id
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            name,
            email,
            hashed_password,
            phone,
            role["role_id"]
        ))

        # Get the new user's ID
        user_id = cursor.lastrowid

        # Create customer record
        conn.execute("""
            INSERT INTO customers (
                user_id,
                address
            )
            VALUES (?, ?)
        """, (
            user_id,
            None
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("auth/register.html")


# =========================================================
# DELIVERY PARTNER AUTHENTICATION
# =========================================================

@app.route("/delivery/login", methods=["GET", "POST"])
def delivery_login():
    if session.get("user_id") and session.get("role") != ROLE_DELIVERY:
        return portal_redirect()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")

        conn = get_db()
        user = conn.execute(
            """
            SELECT users.*, roles.role_name
            FROM users
            JOIN roles ON users.role_id = roles.role_id
            WHERE users.user_email = ? AND roles.role_name = ?
            """,
            (email, ROLE_DELIVERY),
        ).fetchone()

        if user and password and check_password_hash(user["user_pass"], password):
            partner = ensure_delivery_partner(conn, user["user_id"])
            if not partner["is_active"]:
                conn.close()
                return render_template(
                    "auth/delivery-login.html",
                    error="This delivery partner account is currently inactive.",
                )

            if partner["availability_status"] == "Offline":
                conn.execute(
                    "UPDATE delivery_partners SET availability_status = 'Available', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
                    (partner["partner_id"],),
                )
                conn.commit()

            session.clear()
            session.permanent = True
            session["user_id"] = user["user_id"]
            session["user_name"] = user["user_name"]
            session["role"] = ROLE_DELIVERY
            conn.close()
            return redirect(url_for("delivery_dashboard"))

        conn.close()
        return render_template(
            "auth/delivery-login.html",
            error="Invalid delivery partner email or password",
        )

    return render_template("auth/delivery-login.html")


@app.route("/delivery/register", methods=["GET", "POST"])
def delivery_register():
    if session.get("user_id"):
        return portal_redirect()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()
        vehicle_type = request.form.get("vehicle_type", "Bicycle").strip()
        license_number = request.form.get("license_number", "").strip()

        if not all((name, email, password, phone, vehicle_type)):
            return render_template(
                "auth/delivery-register.html",
                error="Please fill all required fields.",
            )
        if len(password) < 6:
            return render_template(
                "auth/delivery-register.html",
                error="Password must be at least 6 characters.",
            )

        conn = get_db()
        existing_user = conn.execute(
            "SELECT user_id FROM users WHERE user_email = ?", (email,)
        ).fetchone()
        if existing_user:
            conn.close()
            return render_template(
                "auth/delivery-register.html",
                error="Email already registered.",
            )

        role_id = get_role_id(conn, ROLE_DELIVERY)
        cursor = conn.execute(
            """
            INSERT INTO users (user_name, user_email, user_pass, phone, role_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, email, generate_password_hash(password), phone, role_id),
        )
        conn.execute(
            """
            INSERT INTO delivery_partners
                (user_id, vehicle_type, license_number, availability_status)
            VALUES (?, ?, ?, 'Offline')
            """,
            (cursor.lastrowid, vehicle_type, license_number or None),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("delivery_login", registered="1"))

    return render_template("auth/delivery-register.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================================================
# FORGOT PASSWORD
# =========================================================

@app.route("/forgot-password")
def forgot_password():
    return render_template("auth/forgot-password.html")


# =========================================================
# RESET PASSWORD
# =========================================================

@app.route("/reset-password")
def reset_password():
    return render_template("auth/reset-password.html")


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if request.method == "GET" and session.get("user_id") and session.get("role") != ROLE_ADMIN:
        return portal_redirect()

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")

        conn = get_db()

        user = conn.execute("""
            SELECT
                users.*,
                roles.role_name
            FROM users
            JOIN roles
                ON users.role_id = roles.role_id
            WHERE users.user_email = ?
        """, (email,)).fetchone()

        conn.close()

        # Must be an Admin
        if (
            user
            and user["role_name"] == ROLE_ADMIN
            and password
            and check_password_hash(
                user["user_pass"],
                password
            )
        ):

            session.permanent = True
            session["user_id"] = user["user_id"]
            session["user_name"] = user["user_name"]
            session["role"] = user["role_name"]

            return redirect(url_for("admin_dashboard"))

        return render_template(
            "auth/admin-login.html",
            error="Invalid admin email or password"
        )

    return render_template("auth/admin-login.html")


# =========================================================
# CUSTOMER PAGES AND ORDER MANAGEMENT
# =========================================================

@app.route("/customer/dashboard")
@role_required(ROLE_CUSTOMER)
def customer_dashboard():
    conn = get_db()
    customer = get_current_customer(conn)
    active_order = None
    if customer:
        active_order = conn.execute(
            """
            SELECT o.*, da.assignment_id, da.status AS delivery_status,
                   dp.partner_id, pu.user_name AS partner_name
            FROM orders o
            LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
            LEFT JOIN delivery_partners dp ON dp.partner_id = da.partner_id
            LEFT JOIN users pu ON pu.user_id = dp.user_id
            WHERE o.customer_id = ? AND o.status NOT IN ('Delivered', 'Cancelled')
            ORDER BY o.created_at DESC LIMIT 1
            """,
            (customer["customer_id"],),
        ).fetchone()
    conn.close()
    return render_template("customer/dashboard.html", active_order=active_order)


@app.route("/customer/restaurants")
@role_required(ROLE_CUSTOMER)
def customer_restaurants():
    return render_template("customer/restaurants.html")


@app.route("/customer/restaurant-details")
@role_required(ROLE_CUSTOMER)
def customer_restaurant_details():
    return render_template("customer/restaurant_details.html")


@app.route("/customer/orders")
@role_required(ROLE_CUSTOMER)
def customer_orders():
    conn = get_db()
    customer = get_current_customer(conn)
    orders = []
    if customer:
        orders = conn.execute(
            """
            SELECT o.*, da.assignment_id, da.status AS delivery_status,
                   pu.user_name AS partner_name
            FROM orders o
            LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
            LEFT JOIN delivery_partners dp ON dp.partner_id = da.partner_id
            LEFT JOIN users pu ON pu.user_id = dp.user_id
            WHERE o.customer_id = ? ORDER BY o.created_at DESC
            """,
            (customer["customer_id"],),
        ).fetchall()
    conn.close()
    return render_template("customer/orders.html", orders=orders)


@app.route("/customer/orders/create", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def create_order():
    if session.get("role") != ROLE_CUSTOMER:
        return portal_redirect()
    details = request.form.get("order_details", "").strip()
    delivery_address = request.form.get("delivery_address", "").strip()
    delivery_notes = request.form.get("delivery_notes", "").strip()

    try:
        total_amount = round(float(request.form.get("total_amount", "0")), 2)
    except (TypeError, ValueError):
        total_amount = 0

    conn = get_db()
    customer = get_current_customer(conn)
    if customer and not delivery_address:
        delivery_address = customer["address"] or ""

    if not customer or not details or total_amount <= 0 or not delivery_address:
        conn.close()
        return jsonify({
            "ok": False,
            "error": "Order items, a valid total, and delivery address are required.",
        }), 400

    cursor = conn.execute(
        """
        INSERT INTO orders (
            customer_id, order_details, total_amount, status,
            restaurant_name, pickup_address, delivery_address, delivery_notes
        )
        VALUES (?, ?, ?, 'Placed', ?, ?, ?, ?)
        """,
        (
            customer["customer_id"],
            details,
            total_amount,
            "ispice majesty",
            "845 Grand Avenue, Culinary District",
            delivery_address,
            delivery_notes or None,
        ),
    )
    order_id = cursor.lastrowid
    add_notification(
        conn,
        session["user_id"],
        "Order placed",
        f"Order #{order_id} has been placed and is waiting for dispatch.",
        "order",
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "order_id": order_id})


@app.route("/customer/tracking")
@role_required(ROLE_CUSTOMER)
def customer_tracking():
    conn = get_db()
    customer = get_current_customer(conn)
    tracking_order = None
    if customer:
        tracking_order = conn.execute(
            """
            SELECT o.*, da.assignment_id, da.status AS delivery_status,
                   da.payout, dp.current_lat, dp.current_lng,
                   pu.user_name AS partner_name, pu.phone AS partner_phone,
                   dp.vehicle_type, dp.rating AS partner_rating
            FROM orders o
            LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
            LEFT JOIN delivery_partners dp ON dp.partner_id = da.partner_id
            LEFT JOIN users pu ON pu.user_id = dp.user_id
            WHERE o.customer_id = ? ORDER BY o.created_at DESC LIMIT 1
            """,
            (customer["customer_id"],),
        ).fetchone()
    conn.close()
    return render_template("customer/tracking.html", tracking_order=tracking_order)


@app.route("/customer/profile", methods=["GET", "POST"])
@role_required(ROLE_CUSTOMER)
def customer_profile():
    conn = get_db()
    if request.method == "POST":
        if session.get("role") != ROLE_CUSTOMER:
            conn.close()
            return portal_redirect()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        preferences = request.form.get("preferences", "").strip()
        if name and email and phone and address:
            conn.execute(
                "UPDATE users SET user_name = ?, user_email = ?, phone = ? WHERE user_id = ?",
                (name, email, phone, session["user_id"]),
            )
            conn.execute(
                "UPDATE customers SET address = ?, preferences = ? WHERE user_id = ?",
                (address, preferences or None, session["user_id"]),
            )
            conn.commit()
            session["user_name"] = name

    user = conn.execute(
        """
        SELECT u.*, c.address, c.preferences
        FROM users u JOIN customers c ON u.user_id = c.user_id
        WHERE u.user_id = ?
        """,
        (session["user_id"],),
    ).fetchone()
    conn.close()
    return render_template("customer/profile.html", user=user)


@app.route("/customer/feedback", methods=["GET", "POST"])
@role_required(ROLE_CUSTOMER)
def customer_feedback():
    conn = get_db()
    customer = get_current_customer(conn)
    if request.method == "POST":
        if session.get("role") != ROLE_CUSTOMER:
            conn.close()
            return portal_redirect()
        try:
            order_id = int(request.form.get("order_id", "0"))
            restaurant_rating = int(request.form.get("restaurant_rating", "0"))
            delivery_rating = int(request.form.get("delivery_rating", "0"))
        except ValueError:
            order_id = restaurant_rating = delivery_rating = 0
        comments = request.form.get("comments", "").strip()
        order = conn.execute(
            """
            SELECT o.order_id, da.partner_id
            FROM orders o
            LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
            WHERE o.order_id = ? AND o.customer_id = ? AND o.status = 'Delivered'
            """,
            (order_id, customer["customer_id"] if customer else 0),
        ).fetchone()
        if order and 1 <= restaurant_rating <= 5 and 1 <= delivery_rating <= 5:
            already_reviewed = conn.execute(
                "SELECT feedback_id FROM feedback WHERE order_id = ?", (order_id,)
            ).fetchone()
            if not already_reviewed:
                conn.execute(
                    """
                    INSERT INTO feedback (
                        order_id, customer_id, delivery_partner_id,
                        restaurant_rating, delivery_rating, comments
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        customer["customer_id"],
                        order["partner_id"],
                        restaurant_rating,
                        delivery_rating,
                        comments or None,
                    ),
                )
                if order["partner_id"]:
                    conn.execute(
                        """
                        UPDATE delivery_partners
                        SET rating = (
                            SELECT ROUND(AVG(delivery_rating), 2)
                            FROM feedback WHERE delivery_partner_id = ?
                        )
                        WHERE partner_id = ?
                        """,
                        (order["partner_id"], order["partner_id"]),
                    )
                conn.commit()
                conn.close()
                return redirect(url_for("customer_feedback"))

    reviewable_orders = conn.execute(
        """
        SELECT o.order_id, o.order_details, o.total_amount,
               f.feedback_id
        FROM orders o
        LEFT JOIN feedback f ON f.order_id = o.order_id
        WHERE o.customer_id = ? AND o.status = 'Delivered'
        ORDER BY o.created_at DESC
        """,
        (customer["customer_id"] if customer else 0,),
    ).fetchall()
    conn.close()
    return render_template("customer/feedback.html", reviewable_orders=reviewable_orders)


@app.route("/customer/cart")
@role_required(ROLE_CUSTOMER)
def customer_cart():
    conn = get_db()
    customer = get_current_customer(conn)
    conn.close()
    return render_template("customer/cart.html", customer=customer)


# =========================================================
# DELIVERY PARTNER PAGES AND OPERATIONS
# =========================================================

def active_assignment_for_partner(conn, partner_id):
    return conn.execute(
        """
        SELECT da.*, o.order_details, o.total_amount, o.status AS order_status,
               o.restaurant_name, o.pickup_address, o.delivery_address,
               o.delivery_notes, c.customer_id, u.user_name AS customer_name,
               u.phone AS customer_phone
        FROM delivery_assignments da
        JOIN orders o ON o.order_id = da.order_id
        JOIN customers c ON c.customer_id = o.customer_id
        JOIN users u ON u.user_id = c.user_id
        WHERE da.partner_id = ? AND da.status NOT IN ('Delivered', 'Cancelled')
        ORDER BY da.assigned_at DESC LIMIT 1
        """,
        (partner_id,),
    ).fetchone()


@app.route("/delivery/dashboard")
@role_required(ROLE_DELIVERY)
def delivery_dashboard():
    conn = get_db()
    partner = get_current_partner(conn)
    if not partner and session.get("role") == ROLE_DELIVERY:
        partner = ensure_delivery_partner(conn, session["user_id"])
    stats = {"today_earnings": 0, "today_deliveries": 0, "average_payout": 0}
    active_assignment = None
    if partner:
        stats = conn.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN date(da.delivered_at) = date('now') THEN da.payout ELSE 0 END), 0) AS today_earnings,
                COUNT(CASE WHEN da.status = 'Delivered' AND date(da.delivered_at) = date('now') THEN 1 END) AS today_deliveries,
                COALESCE(AVG(CASE WHEN da.status = 'Delivered' THEN da.payout END), 0) AS average_payout
            FROM delivery_assignments da WHERE da.partner_id = ?
            """,
            (partner["partner_id"],),
        ).fetchone()
        active_assignment = active_assignment_for_partner(conn, partner["partner_id"])
    conn.close()
    return render_template(
        "delivery/dashboard.html",
        partner=partner,
        stats=stats,
        active_assignment=active_assignment,
    )


@app.route("/delivery/navigation")
@role_required(ROLE_DELIVERY)
def delivery_navigation():
    conn = get_db()
    partner = get_current_partner(conn)
    assignment = active_assignment_for_partner(conn, partner["partner_id"]) if partner else None
    conn.close()
    return render_template("delivery/navigation.html", assignment=assignment)


@app.route("/delivery/history")
@role_required(ROLE_DELIVERY)
def delivery_history():
    conn = get_db()
    partner = get_current_partner(conn)
    history = []
    totals = {"payout": 0, "deliveries": 0}
    if partner:
        history = conn.execute(
            """
            SELECT da.*, o.order_id, o.restaurant_name, u.user_name AS customer_name
            FROM delivery_assignments da
            JOIN orders o ON o.order_id = da.order_id
            JOIN customers c ON c.customer_id = o.customer_id
            JOIN users u ON u.user_id = c.user_id
            WHERE da.partner_id = ? ORDER BY da.delivered_at DESC, da.assigned_at DESC
            """,
            (partner["partner_id"],),
        ).fetchall()
        totals = conn.execute(
            """
            SELECT COALESCE(SUM(payout), 0) AS payout,
                   COUNT(CASE WHEN status = 'Delivered' THEN 1 END) AS deliveries
            FROM delivery_assignments WHERE partner_id = ?
            """,
            (partner["partner_id"],),
        ).fetchone()
    conn.close()
    return render_template("delivery/history.html", history=history, totals=totals)


@app.route("/delivery/details")
@role_required(ROLE_DELIVERY)
def delivery_details():
    conn = get_db()
    partner = get_current_partner(conn)
    assignment_id = request.args.get("assignment_id", type=int)
    assignment = None
    if partner:
        if assignment_id:
            assignment = conn.execute(
                """
                SELECT da.*, o.order_details, o.total_amount, o.status AS order_status,
                       o.restaurant_name, o.pickup_address, o.delivery_address,
                       o.delivery_notes, u.user_name AS customer_name,
                       u.phone AS customer_phone
                FROM delivery_assignments da
                JOIN orders o ON o.order_id = da.order_id
                JOIN customers c ON c.customer_id = o.customer_id
                JOIN users u ON u.user_id = c.user_id
                WHERE da.assignment_id = ? AND da.partner_id = ?
                """,
                (assignment_id, partner["partner_id"]),
            ).fetchone()
        if not assignment:
            assignment = active_assignment_for_partner(conn, partner["partner_id"])
    conn.close()
    return render_template("delivery/details.html", assignment=assignment)


@app.route("/delivery/requests")
@role_required(ROLE_DELIVERY)
def delivery_requests():
    conn = get_db()
    requests = conn.execute(
        """
        SELECT o.*, c.address AS customer_address, u.user_name AS customer_name,
               u.phone AS customer_phone
        FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        JOIN users u ON u.user_id = c.user_id
        LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
        WHERE da.assignment_id IS NULL
          AND o.status IN ('Pending', 'Placed', 'Preparing', 'Dispatched')
        ORDER BY o.created_at ASC
        """
    ).fetchall()
    conn.close()
    return render_template("delivery/requests.html", requests=requests)


@app.route("/delivery/requests/<int:order_id>/accept", methods=["POST"])
@actual_role_required(ROLE_DELIVERY)
def accept_delivery_request(order_id):
    conn = get_db()
    partner = get_current_partner(conn)
    order = conn.execute(
        """
        SELECT o.*, da.assignment_id
        FROM orders o LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
        WHERE o.order_id = ?
        """,
        (order_id,),
    ).fetchone()
    active_assignment = active_assignment_for_partner(conn, partner["partner_id"]) if partner else None
    if (
        not partner
        or not partner["is_active"]
        or active_assignment
        or not order
        or order["assignment_id"]
        or order["status"] not in ("Pending", "Placed", "Preparing", "Dispatched")
    ):
        conn.close()
        return redirect(url_for("delivery_requests"))

    payout = max(3.50, round(float(order["total_amount"] or 0) * 0.15, 2))
    try:
        cursor = conn.execute(
            """
            INSERT INTO delivery_assignments (order_id, partner_id, status, payout, accepted_at)
            VALUES (?, ?, 'Accepted', ?, CURRENT_TIMESTAMP)
            """,
            (order_id, partner["partner_id"], payout),
        )
    except sqlite3.IntegrityError:
        conn.close()
        return redirect(url_for("delivery_requests"))
    conn.execute(
        "UPDATE orders SET status = 'Dispatched' WHERE order_id = ?", (order_id,)
    )
    conn.execute(
        """
        UPDATE delivery_partners
        SET availability_status = 'Busy', updated_at = CURRENT_TIMESTAMP
        WHERE partner_id = ?
        """,
        (partner["partner_id"],),
    )
    customer_user = conn.execute(
        "SELECT user_id FROM customers WHERE customer_id = ?", (order["customer_id"],)
    ).fetchone()
    if customer_user:
        add_notification(
            conn,
            customer_user["user_id"],
            "Delivery partner assigned",
            f"{partner['user_name']} accepted order #{order_id}.",
            "delivery",
        )
    conn.commit()
    conn.close()
    return redirect(url_for("delivery_details", assignment_id=cursor.lastrowid))


@app.route("/delivery/assignments/<int:assignment_id>/status", methods=["POST"])
@actual_role_required(ROLE_DELIVERY)
def update_delivery_status(assignment_id):
    requested_status = request.form.get("status", "").strip()
    transitions = {
        "Assigned": {"Accepted"},
        "Accepted": {"Picked Up"},
        "Picked Up": {"Out for Delivery"},
        "Out for Delivery": {"Delivered"},
    }
    if requested_status not in ORDER_STATUSES:
        return redirect(url_for("delivery_details", assignment_id=assignment_id))

    conn = get_db()
    partner = get_current_partner(conn)
    assignment = conn.execute(
        """
        SELECT da.*, o.customer_id, o.order_id
        FROM delivery_assignments da JOIN orders o ON o.order_id = da.order_id
        WHERE da.assignment_id = ? AND da.partner_id = ?
        """,
        (assignment_id, partner["partner_id"] if partner else 0),
    ).fetchone()
    if not assignment or requested_status not in transitions.get(assignment["status"], set()):
        conn.close()
        return redirect(url_for("delivery_details", assignment_id=assignment_id))

    timestamp_column = {
        "Accepted": "accepted_at",
        "Picked Up": "picked_up_at",
        "Delivered": "delivered_at",
    }.get(requested_status)
    if timestamp_column:
        conn.execute(
            f"UPDATE delivery_assignments SET status = ?, {timestamp_column} = CURRENT_TIMESTAMP WHERE assignment_id = ?",
            (requested_status, assignment_id),
        )
    else:
        conn.execute(
            "UPDATE delivery_assignments SET status = ? WHERE assignment_id = ?",
            (requested_status, assignment_id),
        )
    conn.execute(
        "UPDATE orders SET status = ? WHERE order_id = ?",
        (requested_status, assignment["order_id"]),
    )
    if requested_status == "Delivered":
        conn.execute(
            """
            UPDATE delivery_partners
            SET availability_status = 'Available', updated_at = CURRENT_TIMESTAMP
            WHERE partner_id = ?
            """,
            (partner["partner_id"],),
        )

    customer_user = conn.execute(
        "SELECT user_id FROM customers WHERE customer_id = ?", (assignment["customer_id"],)
    ).fetchone()
    if customer_user:
        add_notification(
            conn,
            customer_user["user_id"],
            "Order status updated",
            f"Order #{assignment['order_id']} is now {requested_status}.",
            "delivery",
        )
    conn.commit()
    conn.close()
    return redirect(url_for("delivery_details", assignment_id=assignment_id))


@app.route("/delivery/assignments/<int:assignment_id>/location", methods=["POST"])
@actual_role_required(ROLE_DELIVERY)
def update_delivery_location(assignment_id):
    try:
        latitude = float(request.form.get("latitude", ""))
        longitude = float(request.form.get("longitude", ""))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid coordinates."}), 400
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"ok": False, "error": "Coordinates are out of range."}), 400

    conn = get_db()
    partner = get_current_partner(conn)
    assignment = conn.execute(
        "SELECT assignment_id FROM delivery_assignments WHERE assignment_id = ? AND partner_id = ?",
        (assignment_id, partner["partner_id"] if partner else 0),
    ).fetchone()
    if not assignment:
        conn.close()
        return jsonify({"ok": False, "error": "Assignment not found."}), 404

    conn.execute(
        "UPDATE delivery_partners SET current_lat = ?, current_lng = ?, updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
        (latitude, longitude, partner["partner_id"]),
    )
    conn.execute(
        "INSERT INTO location_logs (assignment_id, latitude, longitude) VALUES (?, ?, ?)",
        (assignment_id, latitude, longitude),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/delivery/profile", methods=["GET", "POST"])
@role_required(ROLE_DELIVERY)
def delivery_profile():
    conn = get_db()
    partner = get_current_partner(conn)
    if not partner and session.get("role") == ROLE_DELIVERY:
        partner = ensure_delivery_partner(conn, session["user_id"])
        partner = get_current_partner(conn)

    if request.method == "POST":
        if session.get("role") != ROLE_DELIVERY:
            conn.close()
            return portal_redirect()
        if not partner:
            conn.close()
            return portal_redirect()
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        vehicle_type = request.form.get("vehicle_type", "").strip()
        license_number = request.form.get("license_number", "").strip()
        availability = request.form.get("availability_status", "Offline")
        active = active_assignment_for_partner(conn, partner["partner_id"])
        if availability not in DELIVERY_STATUSES:
            availability = "Offline"
        if active:
            availability = "Busy"
        if name and email and phone and vehicle_type:
            conn.execute(
                "UPDATE users SET user_name = ?, user_email = ?, phone = ? WHERE user_id = ?",
                (name, email, phone, session["user_id"]),
            )
            conn.execute(
                """
                UPDATE delivery_partners
                SET vehicle_type = ?, license_number = ?, availability_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE partner_id = ?
                """,
                (vehicle_type, license_number or None, availability, partner["partner_id"]),
            )
            conn.commit()
            session["user_name"] = name
            partner = get_current_partner(conn)
    conn.close()
    return render_template("delivery/profile.html", partner=partner)


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route("/notifications")
@login_required
def notifications():
    conn = get_db()
    items = conn.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
        (session["user_id"],),
    ).fetchall()
    conn.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],)
    )
    conn.commit()
    conn.close()
    return render_template("shared/notifications.html", notifications=items)


# =========================================================
# ADMIN
# =========================================================

@app.route("/admin/dashboard")
@role_required(ROLE_ADMIN)
def admin_dashboard():
    session.pop("portal_preview", None)
    return render_template("admin/dashboard.html")


@app.route("/admin/preview/customer")
@actual_role_required(ROLE_ADMIN)
def admin_customer_preview():
    session["portal_preview"] = ROLE_CUSTOMER
    return redirect(url_for("home"))


@app.route("/admin/preview/delivery")
@actual_role_required(ROLE_ADMIN)
def admin_delivery_preview():
    session["portal_preview"] = ROLE_DELIVERY
    return redirect(url_for("delivery_dashboard"))


@app.route("/admin/preview/exit")
@actual_role_required(ROLE_ADMIN)
def admin_exit_preview():
    session.pop("portal_preview", None)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delivery-partners")
@role_required(ROLE_ADMIN)
def admin_delivery_partners():
    conn = get_db()
    partners = conn.execute(
        """
        SELECT dp.*, u.user_name, u.user_email, u.phone,
               COUNT(CASE WHEN da.status = 'Delivered' THEN 1 END) AS completed_deliveries
        FROM delivery_partners dp
        JOIN users u ON u.user_id = dp.user_id
        LEFT JOIN delivery_assignments da ON da.partner_id = dp.partner_id
        GROUP BY dp.partner_id ORDER BY dp.created_at DESC
        """
    ).fetchall()
    unassigned_orders = conn.execute(
        """
        SELECT o.order_id, o.order_details, o.total_amount, o.status,
               u.user_name AS customer_name
        FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        JOIN users u ON u.user_id = c.user_id
        LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
        WHERE da.assignment_id IS NULL AND o.status NOT IN ('Delivered', 'Cancelled')
        ORDER BY o.created_at ASC
        """
    ).fetchall()
    available_partners = conn.execute(
        """
        SELECT dp.partner_id, u.user_name
        FROM delivery_partners dp JOIN users u ON u.user_id = dp.user_id
        WHERE dp.is_active = 1 AND dp.availability_status = 'Available'
        ORDER BY u.user_name
        """
    ).fetchall()
    conn.close()
    return render_template(
        "admin/delivery-partners.html",
        partners=partners,
        unassigned_orders=unassigned_orders,
        available_partners=available_partners,
    )


@app.route("/admin/delivery-partners/create", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_create_delivery_partner():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    phone = request.form.get("phone", "").strip()
    vehicle_type = request.form.get("vehicle_type", "Bicycle").strip()
    license_number = request.form.get("license_number", "").strip()
    conn = get_db()
    if not all((name, email, password, phone, vehicle_type)) or len(password) < 6:
        conn.close()
        return redirect(url_for("admin_delivery_partners"))
    if conn.execute("SELECT user_id FROM users WHERE user_email = ?", (email,)).fetchone():
        conn.close()
        return redirect(url_for("admin_delivery_partners"))
    role_id = get_role_id(conn, ROLE_DELIVERY)
    user_cursor = conn.execute(
        """
        INSERT INTO users (user_name, user_email, user_pass, phone, role_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, email, generate_password_hash(password), phone, role_id),
    )
    conn.execute(
        """
        INSERT INTO delivery_partners (user_id, vehicle_type, license_number, availability_status)
        VALUES (?, ?, ?, 'Offline')
        """,
        (user_cursor.lastrowid, vehicle_type, license_number or None),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_delivery_partners"))


@app.route("/admin/delivery-partners/assign", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_assign_delivery_order():
    order_id = request.form.get("order_id", type=int)
    partner_id = request.form.get("partner_id", type=int)
    try:
        payout = max(3.50, round(float(request.form.get("payout", "3.5")), 2))
    except (TypeError, ValueError):
        payout = 3.50
    conn = get_db()
    order = conn.execute(
        "SELECT * FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    partner = conn.execute(
        "SELECT * FROM delivery_partners WHERE partner_id = ? AND is_active = 1",
        (partner_id,),
    ).fetchone()
    already_assigned = conn.execute(
        "SELECT assignment_id FROM delivery_assignments WHERE order_id = ?", (order_id,)
    ).fetchone()
    if (
        order
        and partner
        and not already_assigned
        and order["status"] not in ("Delivered", "Cancelled")
    ):
        conn.execute(
            """
            INSERT INTO delivery_assignments (order_id, partner_id, status, payout)
            VALUES (?, ?, 'Assigned', ?)
            """,
            (order_id, partner_id, payout),
        )
        conn.execute("UPDATE orders SET status = 'Dispatched' WHERE order_id = ?", (order_id,))
        conn.execute(
            "UPDATE delivery_partners SET availability_status = 'Busy', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
            (partner_id,),
        )
        partner_user = conn.execute(
            "SELECT user_id, user_name FROM users u JOIN delivery_partners dp ON dp.user_id = u.user_id WHERE dp.partner_id = ?",
            (partner_id,),
        ).fetchone()
        if partner_user:
            add_notification(
                conn,
                partner_user["user_id"],
                "New delivery assignment",
                f"Order #{order_id} has been assigned to you.",
                "delivery",
            )
        conn.commit()
    conn.close()
    return redirect(url_for("admin_delivery_partners"))


@app.route("/admin/delivery-partners/<int:partner_id>/toggle", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_toggle_delivery_partner(partner_id):
    conn = get_db()
    conn.execute(
        "UPDATE delivery_partners SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE partner_id = ?",
        (partner_id,),
    )
    conn.commit()
    conn.close()
    return redirect(url_for("admin_delivery_partners"))


# =========================================================
# PROJECT ASSETS
# =========================================================

@app.route("/project-assets/<path:filename>")
def root_asset(filename):

    return send_from_directory(
        app.root_path,
        filename
    )


# =========================================================
# OLD LINKS
# =========================================================

@app.route("/index.html")
def legacy_home():
    return redirect(url_for("home"))


@app.route("/style.css")
def legacy_stylesheet():
    return redirect(url_for("static", filename="style.css"))


@app.route("/assets/logo.png")
def legacy_logo():
    return redirect(url_for("static", filename="assets/logo.png"))


@app.route("/page_3d.js")
@app.route("/main.js")
@app.route("/scene3d.js")
def legacy_script():

    filename = request.path.rsplit("/", 1)[-1]

    return redirect(
        url_for("root_asset", filename=filename)
    )


# =========================================================
# OLD HTML LINKS
# =========================================================

LEGACY_PAGE_ENDPOINTS = {

    "menu.html": "public_menu",
    "about.html": "about",
    "faq.html": "faq",
    "contact.html": "contact",

    "reserve.html": "public_reserve",
    "track.html": "public_track",
    "privacy.html": "public_privacy",

    "customer/dashboard.html": "customer_dashboard",
    "customer/restaurants.html": "customer_restaurants",
    "customer/restaurant_details.html": "customer_restaurant_details",
    "customer/orders.html": "customer_orders",
    "customer/tracking.html": "customer_tracking",
    "customer/profile.html": "customer_profile",
    "customer/feedback.html": "customer_feedback",
    "customer/cart.html": "customer_cart",

    "public/menu.html": "public_menu",
    "public/about.html": "about",
    "public/faq.html": "faq",
    "public/contact.html": "contact",
    "public/reserve.html": "public_reserve",
    "public/track.html": "public_track",
    "public/privacy.html": "public_privacy",

    "auth/login.html": "login",
    "auth/register.html": "register",
    "auth/forgot-password.html": "forgot_password",
    "auth/reset-password.html": "reset_password",
    "auth/admin-login.html": "admin_login",

    "delivery/dashboard.html": "delivery_dashboard",
    "delivery/navigation.html": "delivery_navigation",
    "delivery/history.html": "delivery_history",
    "delivery/details.html": "delivery_details",
    "delivery/requests.html": "delivery_requests",
    "delivery/profile.html": "delivery_profile",

    "admin/dashboard.html": "admin_dashboard",
}


@app.route("/<path:legacy_path>")
def legacy_page(legacy_path):

    endpoint = LEGACY_PAGE_ENDPOINTS.get(legacy_path)

    if endpoint:
        return redirect(url_for(endpoint))

    return page_not_found(None)


# =========================================================
# 404
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return render_template(
        "public/404.html"
    ), 404


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)
