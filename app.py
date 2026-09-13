"""
=============================================================================
ispice majesty - Food Delivery Web Application
=============================================================================
Welcome to the backend of our Food Delivery website!

Think of this file like the master brain of a restaurant and delivery fleet:
1. It connects to the SQLite database (the digital filing cabinet).
2. It handles customer accounts, menus, shopping carts, and orders.
3. It assigns orders to delivery drivers and updates their live status.
4. It lets the administrator see how the whole restaurant is performing!

Everything here is written in simple, friendly, step-by-step Python so that
anyone—even a beginner or a young student—can read and understand how it works!
=============================================================================
"""

import os
import sqlite3
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
    jsonify,
    flash
)
from jinja2 import ChoiceLoader, FileSystemLoader
from werkzeug.security import generate_password_hash, check_password_hash


# =============================================================================
# SECTION 1: FLASK APP CONFIGURATION
# =============================================================================
# Here we set up Flask, which is our web server. It listens for visitors who
# open our website in their browser.

app = Flask(__name__)

# Secret key used to encrypt cookies (like your digital login badge)
app.secret_key = "mysecretkey-super-secure-and-friendly"

# Keep the user logged in for 60 minutes of inactivity
app.permanent_session_lifetime = timedelta(minutes=60)

# Security cookie settings
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# Tell Jinja (the HTML engine) to look for HTML files in both:
# 1. The default 'templates' folder
# 2. The main project folder (where admin/, auth/, delivery/ live)
app.jinja_loader = ChoiceLoader([
    app.jinja_loader,
    FileSystemLoader(app.root_path)
])


# =============================================================================
# SECTION 2: SECURITY HEADERS AND CSRF PROTECTION
# =============================================================================
# Security guards to protect our website from bad requests.

@app.after_request
def add_security_headers(response):
    """
    Every time our server sends a response to the browser,
    we attach standard safety badges so browsers stay safe.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


def generate_csrf_token():
    """
    Creates a secret random code for the user's session.
    Forms include this secret code to prove the submit came from our website.
    """
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]

# Make the csrf_token() helper function available inside all HTML templates!
app.jinja_env.globals["csrf_token"] = generate_csrf_token


@app.before_request
def csrf_protect():
    """
    Before accepting any POST request (submitting a form), check that the
    secret CSRF token matches the one in the user's session.
    """
    if request.method == "POST":
        expected_token = session.get("csrf_token")
        
        # Check form data, HTTP headers, or JSON body
        submitted_token = (
            request.form.get("csrf_token")
            or request.headers.get("X-CSRF-Token")
            or (request.get_json(silent=True) or {}).get("csrf_token")
        )
        
        # If the secret token does not match, reject the request
        if not expected_token or submitted_token != expected_token:
            abort(403)
    else:
        # Ensure session always has a CSRF token on GET requests
        generate_csrf_token()


# =============================================================================
# SECTION 3: CONSTANTS AND USER ROLES
# =============================================================================
# We have 3 types of users:
# 1. Admin: Runs the restaurant and manages the drivers.
# 2. Customer: Orders delicious food.
# 3. Delivery Partner: Picks up food and brings it to the customer.

ROLE_ADMIN = "Admin"
ROLE_CUSTOMER = "Customer"
ROLE_DELIVERY = "Delivery Partner"

# Valid order statuses from start to finish
ORDER_STATUSES = (
    "Pending",          # Just submitted
    "Placed",           # Confirmed by restaurant
    "Preparing",        # Chef is cooking
    "Dispatched",       # Ready for driver
    "Accepted",         # Driver accepted the job
    "Picked Up",        # Driver has the food
    "Out for Delivery", # Driver is on the road
    "Delivered",        # Food arrived!
    "Cancelled",        # Order cancelled
)

# Valid driver availability statuses
DELIVERY_STATUSES = ("Available", "Busy", "Offline")


# =============================================================================
# SECTION 4: DATABASE CONNECTION AND HELPERS
# =============================================================================
# The database is stored in a simple file named 'food.db'.

DATABASE = os.path.join(app.root_path, "food.db")


def get_db():
    """
    Connect to the SQLite database file and return the connection.
    We set row_factory so we can access database columns by name,
    for example: row['user_name'] instead of row[1].
    """
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def add_column_if_missing(conn, table_name, column_name, definition):
    """
    Helper function that safely adds a new column to a table if it doesn't
    already exist, without deleting any existing data.
    """
    existing_columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def get_role_id(conn, role_name):
    """Finds the numeric ID of a role name (like 'Customer' -> 2)."""
    row = conn.execute("SELECT role_id FROM roles WHERE role_name = ?", (role_name,)).fetchone()
    return row["role_id"] if row else None


def ensure_delivery_partner(conn, user_id):
    """
    Makes sure a delivery partner profile row exists for the given user.
    If it doesn't exist yet, it creates one.
    """
    partner = conn.execute("SELECT * FROM delivery_partners WHERE user_id = ?", (user_id,)).fetchone()
    if partner:
        return partner

    conn.execute(
        """
        INSERT INTO delivery_partners (user_id, availability_status)
        VALUES (?, 'Offline')
        """,
        (user_id,)
    )
    conn.commit()
    return conn.execute("SELECT * FROM delivery_partners WHERE user_id = ?", (user_id,)).fetchone()


def get_current_customer(conn):
    """Finds the customer profile of whoever is currently logged in."""
    if "user_id" not in session:
        return None
    return conn.execute("SELECT * FROM customers WHERE user_id = ?", (session["user_id"],)).fetchone()


def get_current_partner(conn):
    """Finds the delivery partner profile and user details of whoever is logged in."""
    if "user_id" not in session:
        return None
    return conn.execute(
        """
        SELECT dp.*, u.user_name, u.user_email, u.phone
        FROM delivery_partners dp
        JOIN users u ON u.user_id = dp.user_id
        WHERE dp.user_id = ?
        """,
        (session["user_id"],)
    ).fetchone()


def add_notification(conn, user_id, title, message, notification_type="system"):
    """
    Puts a friendly alert into the user's notification box!
    """
    conn.execute(
        """
        INSERT INTO notifications (user_id, notification_type, title, message)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, notification_type, title, message)
    )


# =============================================================================
# SECTION 5: INITIALIZE DATABASE TABLES
# =============================================================================
# This function automatically creates all the tables if this is a fresh setup.

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Roles table (Admin, Customer, Delivery Partner)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            role_id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_name VARCHAR(50) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Users table (stores name, email, password hash, phone, and role)
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
            FOREIGN KEY (role_id) REFERENCES roles(role_id)
        )
    """)

    # 3. Customers table (extra details like address and food preferences)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            address TEXT,
            preferences TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    # 4. Orders table (items, total price, status, delivery address)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_details TEXT NOT NULL,
            total_amount DECIMAL(10, 2),
            status VARCHAR(50) DEFAULT 'Pending',
            restaurant_name VARCHAR(150) DEFAULT 'ispice majesty',
            pickup_address TEXT DEFAULT '845 Grand Avenue, Culinary District',
            delivery_address TEXT,
            delivery_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    """)

    # 5. Delivery Partners table (vehicle, status, rating, coordinates)
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

    # 6. Delivery Assignments table (connects an order with a delivery driver)
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

    # 7. Location Logs table (tracks driver GPS points)
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

    # 8. Notifications table
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

    # 9. Feedback table (stars and reviews from customers)
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

    # Make sure optional columns exist in legacy databases
    add_column_if_missing(conn, "orders", "restaurant_name", "VARCHAR(150) DEFAULT 'ispice majesty'")
    add_column_if_missing(conn, "orders", "pickup_address", "TEXT DEFAULT '845 Grand Avenue, Culinary District'")
    add_column_if_missing(conn, "orders", "delivery_address", "TEXT")
    add_column_if_missing(conn, "orders", "delivery_notes", "TEXT")

    # Insert initial roles if they are not already there
    cursor.execute("INSERT OR IGNORE INTO roles (role_name) VALUES (?)", (ROLE_ADMIN,))
    cursor.execute("INSERT OR IGNORE INTO roles (role_name) VALUES (?)", (ROLE_CUSTOMER,))
    cursor.execute("INSERT OR IGNORE INTO roles (role_name) VALUES (?)", (ROLE_DELIVERY,))

    conn.commit()
    conn.close()


# Run database initialization once on startup
init_db()


# =============================================================================
# SECTION 6: ACCESS CONTROL HELPERS (LOGIN & ROLE GUARDS)
# =============================================================================

def portal_redirect():
    """
    Sends each user directly to their correct personal dashboard:
    - Admin -> Admin Dashboard
    - Delivery Partner -> Delivery Dashboard
    - Customer -> Customer Dashboard
    - Not logged in -> Login page
    """
    role = session.get("role")
    if role == ROLE_ADMIN:
        return redirect(url_for("admin_dashboard"))
    if role == ROLE_DELIVERY:
        return redirect(url_for("delivery_dashboard"))
    if role == ROLE_CUSTOMER:
        return redirect(url_for("customer_dashboard"))
    return redirect(url_for("login"))


def admin_previewing(role_name):
    """Checks if an Admin is temporarily testing how another role's dashboard looks."""
    return (
        session.get("role") == ROLE_ADMIN
        and session.get("portal_preview") == role_name
    )


def login_required(f):
    """
    Gatekeeper: makes sure the visitor is logged in.
    If not, sends them to the login screen!
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def role_required(*roles):
    """
    Gatekeeper: makes sure the user has one of the allowed roles
    (or is an admin previewing that role).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            user_role = session.get("role")
            if user_role not in roles and not any(admin_previewing(r) for r in roles):
                return portal_redirect()
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def actual_role_required(*roles):
    """
    Strict gatekeeper: requires the user's REAL role (preview mode cannot submit changes).
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get("role") not in roles:
                return portal_redirect()
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def public_access(f):
    """
    Allows customers and public visitors to browse freely,
    while keeping staff (drivers and admins) inside their staff portals.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        role = session.get("role")
        if role == ROLE_DELIVERY:
            return portal_redirect()
        if role == ROLE_ADMIN and not admin_previewing(ROLE_CUSTOMER):
            return portal_redirect()
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# SECTION 7: PUBLIC WEBSITE PAGES
# =============================================================================
# These pages can be visited by anyone on the internet!

@app.route("/")
@public_access
def home():
    """Main landing page of ispice majesty."""
    return render_template("index.html")


@app.route("/rest")
@public_access
def rest():
    """Restaurant showcase page."""
    return render_template("customer/restaurants.html")


@app.route("/menu")
@public_access
def menu():
    """Gourmet menu page."""
    return render_template("public/menu.html")


@app.route("/about")
@public_access
def about():
    """About us page."""
    return render_template("public/about.html")


@app.route("/faq")
@public_access
def faq():
    """Frequently asked questions page."""
    return render_template("public/faq.html")


@app.route("/contact")
@public_access
def contact():
    """Contact our restaurant page."""
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


# =============================================================================
# SECTION 8: AUTHENTICATION (SIGN IN, SIGN UP, PASSWORD RESET)
# =============================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Universal login page for customers, drivers, and admins.
    Step 1: If already logged in, go straight to your dashboard.
    Step 2: When the form is submitted, check the email and password.
    Step 3: If correct, save the user info in the session and redirect.
    """
    if request.method == "GET" and session.get("user_id") and session.get("role") != ROLE_CUSTOMER:
        return portal_redirect()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        try:
            user = conn.execute(
                """
                SELECT users.*, roles.role_name
                FROM users
                JOIN roles ON users.role_id = roles.role_id
                WHERE users.user_email = ?
                """,
                (email,)
            ).fetchone()

            # Check if user exists and password is correct
            if user and password and check_password_hash(user["user_pass"], password):
                
                # If this is a delivery partner, check active status and set to Available
                if user["role_name"] == ROLE_DELIVERY:
                    partner = ensure_delivery_partner(conn, user["user_id"])
                    if not partner["is_active"]:
                        return render_template(
                            "auth/login.html",
                            error="This delivery partner account is currently inactive."
                        )
                    if partner["availability_status"] == "Offline":
                        conn.execute(
                            "UPDATE delivery_partners SET availability_status = 'Available', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
                            (partner["partner_id"],)
                        )
                        conn.commit()

                # Log the user in!
                session.clear()
                session.permanent = True
                session["csrf_token"] = generate_csrf_token()
                session["user_id"] = user["user_id"]
                session["user_name"] = user["user_name"]
                session["user_email"] = user["user_email"]
                session["role"] = user["role_name"]

                # Send them to their portal
                if user["role_name"] == ROLE_ADMIN:
                    return redirect(url_for("admin_dashboard"))
                elif user["role_name"] == ROLE_DELIVERY:
                    return redirect(url_for("delivery_dashboard"))
                else:
                    return redirect(url_for("customer_dashboard"))

            # If password or email was wrong:
            return render_template(
                "auth/login.html",
                error="Invalid email or password. Please try again!"
            )
        finally:
            conn.close()

    return render_template("auth/login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Customer registration page.
    Step 1: Get name, email, password, and phone number.
    Step 2: Make sure the email isn't already used.
    Step 3: Hash the password for security.
    Step 4: Save the user and create their customer profile.
    """
    if session.get("role") in (ROLE_ADMIN, ROLE_DELIVERY):
        return portal_redirect()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "").strip()

        # Simple validation
        if not name or not email or not password or not phone:
            return render_template("auth/register.html", error="Please fill in all fields!")

        if len(password) < 6:
            return render_template("auth/register.html", error="Password must be at least 6 characters long.")

        conn = get_db()
        try:
            # Check if this email is already registered
            existing_user = conn.execute("SELECT user_id FROM users WHERE user_email = ?", (email,)).fetchone()
            if existing_user:
                return render_template("auth/register.html", error="An account with this email already exists.")

            role_id = get_role_id(conn, ROLE_CUSTOMER)
            hashed_password = generate_password_hash(password)

            # Insert into users table
            cursor = conn.execute(
                """
                INSERT INTO users (user_name, user_email, user_pass, phone, role_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, email, hashed_password, phone, role_id)
            )
            new_user_id = cursor.lastrowid

            # Create customer profile record
            conn.execute(
                "INSERT INTO customers (user_id, address) VALUES (?, ?)",
                (new_user_id, "")
            )

            # Add a welcome notification!
            add_notification(
                conn,
                new_user_id,
                "Welcome to ispice majesty!",
                f"Hello {name}! Your customer account is ready. Explore our gourmet menu!",
                "welcome"
            )

            conn.commit()
            return redirect(url_for("login"))
        finally:
            conn.close()

    return render_template("auth/register.html")


@app.route("/delivery/login", methods=["GET", "POST"])
def delivery_login():
    """Special login page specifically for Delivery Partners."""
    if session.get("user_id") and session.get("role") != ROLE_DELIVERY:
        return portal_redirect()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        try:
            user = conn.execute(
                """
                SELECT users.*, roles.role_name
                FROM users
                JOIN roles ON users.role_id = roles.role_id
                WHERE users.user_email = ? AND roles.role_name = ?
                """,
                (email, ROLE_DELIVERY)
            ).fetchone()

            if user and password and check_password_hash(user["user_pass"], password):
                partner = ensure_delivery_partner(conn, user["user_id"])
                if not partner["is_active"]:
                    return render_template(
                        "auth/delivery-login.html",
                        error="This delivery partner account is currently inactive."
                    )

                if partner["availability_status"] == "Offline":
                    conn.execute(
                        "UPDATE delivery_partners SET availability_status = 'Available', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
                        (partner["partner_id"],)
                    )
                    conn.commit()

                session.clear()
                session.permanent = True
                session["csrf_token"] = generate_csrf_token()
                session["user_id"] = user["user_id"]
                session["user_name"] = user["user_name"]
                session["user_email"] = user["user_email"]
                session["role"] = ROLE_DELIVERY
                return redirect(url_for("delivery_dashboard"))

            return render_template(
                "auth/delivery-login.html",
                error="Invalid delivery partner email or password."
            )
        finally:
            conn.close()

    return render_template("auth/delivery-login.html")


@app.route("/delivery/register", methods=["GET", "POST"])
def delivery_register():
    """Allows new delivery drivers to sign up."""
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
            return render_template("auth/delivery-register.html", error="Please fill in all required fields.")

        if len(password) < 6:
            return render_template("auth/delivery-register.html", error="Password must be at least 6 characters.")

        conn = get_db()
        try:
            existing_user = conn.execute("SELECT user_id FROM users WHERE user_email = ?", (email,)).fetchone()
            if existing_user:
                return render_template("auth/delivery-register.html", error="Email already registered.")

            role_id = get_role_id(conn, ROLE_DELIVERY)
            cursor = conn.execute(
                """
                INSERT INTO users (user_name, user_email, user_pass, phone, role_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, email, generate_password_hash(password), phone, role_id)
            )
            conn.execute(
                """
                INSERT INTO delivery_partners (user_id, vehicle_type, license_number, availability_status)
                VALUES (?, ?, ?, 'Offline')
                """,
                (cursor.lastrowid, vehicle_type, license_number or None)
            )
            conn.commit()
            return redirect(url_for("delivery_login", registered="1"))
        finally:
            conn.close()

    return render_template("auth/delivery-register.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    """Special login page specifically for Administrators."""
    if request.method == "GET" and session.get("user_id") and session.get("role") != ROLE_ADMIN:
        return portal_redirect()

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        try:
            user = conn.execute(
                """
                SELECT users.*, roles.role_name
                FROM users
                JOIN roles ON users.role_id = roles.role_id
                WHERE users.user_email = ?
                """,
                (email,)
            ).fetchone()

            if user and user["role_name"] == ROLE_ADMIN and password and check_password_hash(user["user_pass"], password):
                session.clear()
                session.permanent = True
                session["csrf_token"] = generate_csrf_token()
                session["user_id"] = user["user_id"]
                session["user_name"] = user["user_name"]
                session["user_email"] = user["user_email"]
                session["role"] = user["role_name"]
                return redirect(url_for("admin_dashboard"))

            return render_template(
                "auth/admin-login.html",
                error="Invalid admin email or password."
            )
        finally:
            conn.close()

    return render_template("auth/admin-login.html")


@app.route("/logout")
def logout():
    """Logs the current user out and clears the session."""
    session.clear()
    generate_csrf_token()
    return redirect(url_for("login"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    Helps a user reset their password if they forgot it.
    Step 1: Enter email address.
    Step 2: Check if email exists in our database.
    Step 3: Redirect to the password reset form with the email!
    """
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            return render_template("auth/forgot-password.html", error="Please enter your email address.")

        conn = get_db()
        try:
            user = conn.execute("SELECT user_id, user_email FROM users WHERE user_email = ?", (email,)).fetchone()
            if not user:
                return render_template("auth/forgot-password.html", error="No account found with this email address.")
            return redirect(url_for("reset_password", email=email))
        finally:
            conn.close()

    return render_template("auth/forgot-password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """
    Allows the user to set a new password.
    Step 1: User types their email and new password.
    Step 2: Update the password hash in the database.
    Step 3: Send them to the login page with a success message!
    """
    email = request.args.get("email", "").strip().lower()

    if request.method == "POST":
        post_email = request.form.get("email", email).strip().lower()
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not post_email or not new_password:
            return render_template("auth/reset-password.html", email=post_email, error="Please enter all fields.")

        if len(new_password) < 6:
            return render_template("auth/reset-password.html", email=post_email, error="Password must be at least 6 characters.")

        if new_password != confirm_password:
            return render_template("auth/reset-password.html", email=post_email, error="Passwords do not match.")

        conn = get_db()
        try:
            user = conn.execute("SELECT user_id FROM users WHERE user_email = ?", (post_email,)).fetchone()
            if not user:
                return render_template("auth/reset-password.html", email=post_email, error="Account not found.")

            hashed = generate_password_hash(new_password)
            conn.execute("UPDATE users SET user_pass = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (hashed, user["user_id"]))
            conn.commit()
            return render_template("auth/login.html", success="Password successfully updated! Please sign in.")
        finally:
            conn.close()

    return render_template("auth/reset-password.html", email=email)


# =============================================================================
# SECTION 9: CUSTOMER PORTAL & ORDERS
# =============================================================================

@app.route("/customer/dashboard")
@role_required(ROLE_CUSTOMER)
def customer_dashboard():
    """Customer's main home base: shows current active order status."""
    conn = get_db()
    try:
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
                (customer["customer_id"],)
            ).fetchone()
        return render_template("customer/dashboard.html", active_order=active_order)
    finally:
        conn.close()


@app.route("/customer/restaurants")
@role_required(ROLE_CUSTOMER)
def customer_restaurants():
    """Shows partner restaurants and exhibition culinary destinations."""
    return render_template("customer/restaurants.html")


@app.route("/customer/restaurant-details")
@role_required(ROLE_CUSTOMER)
def customer_restaurant_details():
    """Shows menu details of the selected restaurant."""
    return render_template("customer/restaurant_details.html")


@app.route("/customer/orders")
@role_required(ROLE_CUSTOMER)
def customer_orders():
    """Lists all past and present orders placed by this customer."""
    conn = get_db()
    try:
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
                WHERE o.customer_id = ?
                ORDER BY o.created_at DESC
                """,
                (customer["customer_id"],)
            ).fetchall()
        return render_template("customer/orders.html", orders=orders)
    finally:
        conn.close()


@app.route("/customer/orders/create", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def create_order():
    """
    Submits a new order from the customer's cart into the database!
    Step 1: Read order items, total price, and delivery address.
    Step 2: Save the order with status 'Placed'.
    Step 3: Send a friendly notification to the customer.
    Step 4: Return JSON confirming the order ID.
    """
    if session.get("role") != ROLE_CUSTOMER:
        return portal_redirect()

    details = request.form.get("order_details", "").strip()
    delivery_address = request.form.get("delivery_address", "").strip()
    delivery_notes = request.form.get("delivery_notes", "").strip()

    try:
        total_amount = round(float(request.form.get("total_amount", "0")), 2)
    except (TypeError, ValueError):
        total_amount = 0.0

    conn = get_db()
    try:
        customer = get_current_customer(conn)
        if customer and not delivery_address:
            delivery_address = customer["address"] or ""

        if not customer or not details or total_amount <= 0 or not delivery_address:
            return jsonify({
                "ok": False,
                "error": "Order items, valid total, and delivery address are required."
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
            )
        )
        new_order_id = cursor.lastrowid

        # Send a notification to the customer
        add_notification(
            conn,
            session["user_id"],
            "Order Placed Successfully!",
            f"Your order #{new_order_id} has been received and our chefs are getting it ready!",
            "order"
        )

        conn.commit()
        return jsonify({"ok": True, "order_id": new_order_id})
    finally:
        conn.close()


@app.route("/customer/orders/<int:order_id>/cancel", methods=["POST"])
@role_required(ROLE_CUSTOMER)
def cancel_order(order_id):
    """
    Allows a customer to cancel an order if it hasn't been picked up yet.
    """
    conn = get_db()
    try:
        customer = get_current_customer(conn)
        if not customer:
            return redirect(url_for("customer_orders"))

        order = conn.execute(
            "SELECT * FROM orders WHERE order_id = ? AND customer_id = ?",
            (order_id, customer["customer_id"])
        ).fetchone()

        # Only allow cancellation if order has not been dispatched/picked up
        if order and order["status"] in ("Placed", "Pending", "Preparing"):
            conn.execute("UPDATE orders SET status = 'Cancelled' WHERE order_id = ?", (order_id,))
            
            # Cancel any assignment if present
            conn.execute("UPDATE delivery_assignments SET status = 'Cancelled' WHERE order_id = ?", (order_id,))

            add_notification(
                conn,
                session["user_id"],
                "Order Cancelled",
                f"Order #{order_id} was cancelled.",
                "order"
            )
            conn.commit()

        return redirect(url_for("customer_orders"))
    finally:
        conn.close()


@app.route("/customer/tracking")
@role_required(ROLE_CUSTOMER)
def customer_tracking():
    """Live GPS order tracking page for the customer."""
    conn = get_db()
    try:
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
                WHERE o.customer_id = ?
                ORDER BY o.created_at DESC LIMIT 1
                """,
                (customer["customer_id"],)
            ).fetchone()
        return render_template("customer/tracking.html", tracking_order=tracking_order)
    finally:
        conn.close()


@app.route("/customer/profile", methods=["GET", "POST"])
@role_required(ROLE_CUSTOMER)
def customer_profile():
    """Customer profile page: update name, phone, and delivery address."""
    conn = get_db()
    try:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            address = request.form.get("address", "").strip()
            preferences = request.form.get("preferences", "").strip()

            if name and email and phone:
                conn.execute(
                    "UPDATE users SET user_name = ?, user_email = ?, phone = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (name, email, phone, session["user_id"])
                )
                conn.execute(
                    "UPDATE customers SET address = ?, preferences = ? WHERE user_id = ?",
                    (address, preferences or None, session["user_id"])
                )
                conn.commit()
                session["user_name"] = name
                session["user_email"] = email

        user = conn.execute(
            """
            SELECT u.*, c.address, c.preferences
            FROM users u
            JOIN customers c ON u.user_id = c.user_id
            WHERE u.user_id = ?
            """,
            (session["user_id"],)
        ).fetchone()
        return render_template("customer/profile.html", user=user)
    finally:
        conn.close()


@app.route("/customer/feedback", methods=["GET", "POST"])
@role_required(ROLE_CUSTOMER)
def customer_feedback():
    """Lets customers give star ratings and write reviews for delivered orders."""
    conn = get_db()
    try:
        customer = get_current_customer(conn)

        if request.method == "POST":
            try:
                order_id = int(request.form.get("order_id", "0"))
                restaurant_rating = int(request.form.get("restaurant_rating", "5"))
                delivery_rating = int(request.form.get("delivery_rating", "5"))
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
                (order_id, customer["customer_id"] if customer else 0)
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
                        (order_id, customer["customer_id"], order["partner_id"], restaurant_rating, delivery_rating, comments or None)
                    )

                    # Update driver's average rating!
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
                            (order["partner_id"], order["partner_id"])
                        )

                    conn.commit()
                    return redirect(url_for("customer_feedback"))

        reviewable_orders = conn.execute(
            """
            SELECT o.order_id, o.order_details, o.total_amount, f.feedback_id
            FROM orders o
            LEFT JOIN feedback f ON f.order_id = o.order_id
            WHERE o.customer_id = ? AND o.status = 'Delivered'
            ORDER BY o.created_at DESC
            """,
            (customer["customer_id"] if customer else 0,)
        ).fetchall()

        return render_template("customer/feedback.html", reviewable_orders=reviewable_orders)
    finally:
        conn.close()


@app.route("/customer/cart")
@role_required(ROLE_CUSTOMER)
def customer_cart():
    """Customer's shopping cart and checkout page."""
    conn = get_db()
    try:
        customer = get_current_customer(conn)
        return render_template("customer/cart.html", customer=customer)
    finally:
        conn.close()


# =============================================================================
# SECTION 10: DELIVERY PARTNER OPERATIONS & DISPATCH
# =============================================================================

def active_assignment_for_partner(conn, partner_id):
    """Finds the current active delivery job for a specific driver."""
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
        (partner_id,)
    ).fetchone()


@app.route("/delivery/dashboard")
@role_required(ROLE_DELIVERY)
def delivery_dashboard():
    """Delivery Fleet Dashboard: earnings, rating, and active delivery."""
    conn = get_db()
    try:
        partner = get_current_partner(conn)
        if not partner and session.get("role") == ROLE_DELIVERY:
            partner = ensure_delivery_partner(conn, session["user_id"])

        stats = {"today_earnings": 0.0, "today_deliveries": 0, "average_payout": 0.0}
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
                (partner["partner_id"],)
            ).fetchone()
            active_assignment = active_assignment_for_partner(conn, partner["partner_id"])

        return render_template(
            "delivery/dashboard.html",
            partner=partner,
            stats=stats,
            active_assignment=active_assignment
        )
    finally:
        conn.close()


@app.route("/delivery/navigation")
@role_required(ROLE_DELIVERY)
def delivery_navigation():
    """Turn-by-turn simulated GPS map for the delivery driver."""
    conn = get_db()
    try:
        partner = get_current_partner(conn)
        assignment = active_assignment_for_partner(conn, partner["partner_id"]) if partner else None
        return render_template("delivery/navigation.html", assignment=assignment)
    finally:
        conn.close()


@app.route("/delivery/history")
@role_required(ROLE_DELIVERY)
def delivery_history():
    """History of all completed deliveries and total earnings."""
    conn = get_db()
    try:
        partner = get_current_partner(conn)
        history = []
        totals = {"payout": 0.0, "deliveries": 0}

        if partner:
            history = conn.execute(
                """
                SELECT da.*, o.order_id, o.restaurant_name, u.user_name AS customer_name
                FROM delivery_assignments da
                JOIN orders o ON o.order_id = da.order_id
                JOIN customers c ON c.customer_id = o.customer_id
                JOIN users u ON u.user_id = c.user_id
                WHERE da.partner_id = ?
                ORDER BY da.delivered_at DESC, da.assigned_at DESC
                """,
                (partner["partner_id"],)
            ).fetchall()

            totals = conn.execute(
                """
                SELECT COALESCE(SUM(payout), 0) AS payout,
                       COUNT(CASE WHEN status = 'Delivered' THEN 1 END) AS deliveries
                FROM delivery_assignments WHERE partner_id = ?
                """,
                (partner["partner_id"],)
            ).fetchone()

        return render_template("delivery/history.html", history=history, totals=totals)
    finally:
        conn.close()


@app.route("/delivery/details")
@role_required(ROLE_DELIVERY)
def delivery_details():
    """Detailed view of an assigned delivery order with progress buttons."""
    conn = get_db()
    try:
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
                    (assignment_id, partner["partner_id"])
                ).fetchone()

            if not assignment:
                assignment = active_assignment_for_partner(conn, partner["partner_id"])

        return render_template("delivery/details.html", assignment=assignment)
    finally:
        conn.close()


@app.route("/delivery/requests")
@role_required(ROLE_DELIVERY)
def delivery_requests():
    """Shows all available orders waiting for a driver to accept."""
    conn = get_db()
    try:
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
        return render_template("delivery/requests.html", requests=requests)
    finally:
        conn.close()


@app.route("/delivery/requests/<int:order_id>/accept", methods=["POST"])
@actual_role_required(ROLE_DELIVERY)
def accept_delivery_request(order_id):
    """
    Called when a driver clicks 'Accept' on an available order.
    Step 1: Check driver is active and doesn't already have an active job.
    Step 2: Assign the order to this driver with a payout calculation.
    Step 3: Update driver status to 'Busy'.
    Step 4: Notify the customer!
    """
    conn = get_db()
    try:
        partner = get_current_partner(conn)
        order = conn.execute(
            """
            SELECT o.*, da.assignment_id
            FROM orders o
            LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
            WHERE o.order_id = ?
            """,
            (order_id,)
        ).fetchone()

        active_job = active_assignment_for_partner(conn, partner["partner_id"]) if partner else None

        if (
            not partner
            or not partner["is_active"]
            or active_job
            or not order
            or order["assignment_id"]
            or order["status"] not in ("Pending", "Placed", "Preparing", "Dispatched")
        ):
            return redirect(url_for("delivery_requests"))

        payout = max(3.50, round(float(order["total_amount"] or 0) * 0.15, 2))

        try:
            cursor = conn.execute(
                """
                INSERT INTO delivery_assignments (order_id, partner_id, status, payout, accepted_at)
                VALUES (?, ?, 'Accepted', ?, CURRENT_TIMESTAMP)
                """,
                (order_id, partner["partner_id"], payout)
            )
            assignment_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            return redirect(url_for("delivery_requests"))

        conn.execute("UPDATE orders SET status = 'Dispatched' WHERE order_id = ?", (order_id,))
        conn.execute(
            "UPDATE delivery_partners SET availability_status = 'Busy', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
            (partner["partner_id"],)
        )

        customer_user = conn.execute(
            "SELECT user_id FROM customers WHERE customer_id = ?", (order["customer_id"],)
        ).fetchone()
        if customer_user:
            add_notification(
                conn,
                customer_user["user_id"],
                "Driver Assigned!",
                f"{partner['user_name']} is heading to pick up order #{order_id}.",
                "delivery"
            )

        conn.commit()
        return redirect(url_for("delivery_details", assignment_id=assignment_id))
    finally:
        conn.close()


@app.route("/delivery/assignments/<int:assignment_id>/status", methods=["POST"])
@actual_role_required(ROLE_DELIVERY)
def update_delivery_status(assignment_id):
    """
    Moves the delivery along its journey:
    Assigned -> Accepted -> Picked Up -> Out for Delivery -> Delivered!
    """
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
    try:
        partner = get_current_partner(conn)
        assignment = conn.execute(
            """
            SELECT da.*, o.customer_id, o.order_id
            FROM delivery_assignments da
            JOIN orders o ON o.order_id = da.order_id
            WHERE da.assignment_id = ? AND da.partner_id = ?
            """,
            (assignment_id, partner["partner_id"] if partner else 0)
        ).fetchone()

        if not assignment or requested_status not in transitions.get(assignment["status"], set()):
            return redirect(url_for("delivery_details", assignment_id=assignment_id))

        # Update assignment timestamps
        timestamp_col = {
            "Accepted": "accepted_at",
            "Picked Up": "picked_up_at",
            "Delivered": "delivered_at",
        }.get(requested_status)

        if timestamp_col:
            conn.execute(
                f"UPDATE delivery_assignments SET status = ?, {timestamp_col} = CURRENT_TIMESTAMP WHERE assignment_id = ?",
                (requested_status, assignment_id)
            )
        else:
            conn.execute(
                "UPDATE delivery_assignments SET status = ? WHERE assignment_id = ?",
                (requested_status, assignment_id)
            )

        # Update order status
        conn.execute("UPDATE orders SET status = ? WHERE order_id = ?", (requested_status, assignment["order_id"]))

        # When delivered, make driver available again!
        if requested_status == "Delivered":
            conn.execute(
                "UPDATE delivery_partners SET availability_status = 'Available', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
                (partner["partner_id"],)
            )

        # Notify the customer!
        customer_user = conn.execute(
            "SELECT user_id FROM customers WHERE customer_id = ?", (assignment["customer_id"],)
        ).fetchone()
        if customer_user:
            add_notification(
                conn,
                customer_user["user_id"],
                "Order Status Updated",
                f"Order #{assignment['order_id']} is now: {requested_status}!",
                "delivery"
            )

        conn.commit()
        return redirect(url_for("delivery_details", assignment_id=assignment_id))
    finally:
        conn.close()


@app.route("/delivery/assignments/<int:assignment_id>/location", methods=["POST"])
@actual_role_required(ROLE_DELIVERY)
def update_delivery_location(assignment_id):
    """Records the driver's GPS location in the database."""
    try:
        latitude = float(request.form.get("latitude", ""))
        longitude = float(request.form.get("longitude", ""))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "Invalid coordinates."}), 400

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return jsonify({"ok": False, "error": "Coordinates out of range."}), 400

    conn = get_db()
    try:
        partner = get_current_partner(conn)
        assignment = conn.execute(
            "SELECT assignment_id FROM delivery_assignments WHERE assignment_id = ? AND partner_id = ?",
            (assignment_id, partner["partner_id"] if partner else 0)
        ).fetchone()

        if not assignment:
            return jsonify({"ok": False, "error": "Assignment not found."}), 404

        conn.execute(
            "UPDATE delivery_partners SET current_lat = ?, current_lng = ?, updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
            (latitude, longitude, partner["partner_id"])
        )
        conn.execute(
            "INSERT INTO location_logs (assignment_id, latitude, longitude) VALUES (?, ?, ?)",
            (assignment_id, latitude, longitude)
        )
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()


@app.route("/delivery/profile", methods=["GET", "POST"])
@role_required(ROLE_DELIVERY)
def delivery_profile():
    """Driver profile page: change vehicle, phone, and online availability."""
    conn = get_db()
    try:
        partner = get_current_partner(conn)
        if not partner and session.get("role") == ROLE_DELIVERY:
            partner = ensure_delivery_partner(conn, session["user_id"])
            partner = get_current_partner(conn)

        if request.method == "POST":
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
                    "UPDATE users SET user_name = ?, user_email = ?, phone = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                    (name, email, phone, session["user_id"])
                )
                conn.execute(
                    """
                    UPDATE delivery_partners
                    SET vehicle_type = ?, license_number = ?, availability_status = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE partner_id = ?
                    """,
                    (vehicle_type, license_number or None, availability, partner["partner_id"])
                )
                conn.commit()
                session["user_name"] = name
                session["user_email"] = email
                partner = get_current_partner(conn)

        return render_template("delivery/profile.html", partner=partner)
    finally:
        conn.close()


# =============================================================================
# SECTION 11: NOTIFICATIONS
# =============================================================================

@app.route("/notifications")
@login_required
def notifications():
    """Lists all notifications for the logged in user and marks them as read."""
    conn = get_db()
    try:
        items = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
            (session["user_id"],)
        ).fetchall()
        conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
        conn.commit()
        return render_template("shared/notifications.html", notifications=items)
    finally:
        conn.close()


# =============================================================================
# SECTION 12: ADMIN COMMAND CENTER
# =============================================================================

@app.route("/admin/dashboard")
@role_required(ROLE_ADMIN)
def admin_dashboard():
    """Admin dashboard overview."""
    session.pop("portal_preview", None)
    return render_template("admin/dashboard.html")


@app.route("/admin/preview/customer")
@actual_role_required(ROLE_ADMIN)
def admin_customer_preview():
    """Lets an admin preview how the customer sees the site."""
    session["portal_preview"] = ROLE_CUSTOMER
    return redirect(url_for("home"))


@app.route("/admin/preview/delivery")
@actual_role_required(ROLE_ADMIN)
def admin_delivery_preview():
    """Lets an admin preview how a delivery driver sees the fleet portal."""
    session["portal_preview"] = ROLE_DELIVERY
    return redirect(url_for("delivery_dashboard"))


@app.route("/admin/preview/exit")
@actual_role_required(ROLE_ADMIN)
def admin_exit_preview():
    """Exits preview mode and returns to Admin dashboard."""
    session.pop("portal_preview", None)
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delivery-partners")
@role_required(ROLE_ADMIN)
def admin_delivery_partners():
    """Admin page to view and manage all delivery partners and unassigned orders."""
    conn = get_db()
    try:
        partners = conn.execute(
            """
            SELECT dp.*, u.user_name, u.user_email, u.phone,
                   COUNT(CASE WHEN da.status = 'Delivered' THEN 1 END) AS completed_deliveries
            FROM delivery_partners dp
            JOIN users u ON u.user_id = dp.user_id
            LEFT JOIN delivery_assignments da ON da.partner_id = dp.partner_id
            GROUP BY dp.partner_id
            ORDER BY dp.created_at DESC
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
            FROM delivery_partners dp
            JOIN users u ON u.user_id = dp.user_id
            WHERE dp.is_active = 1 AND dp.availability_status = 'Available'
            ORDER BY u.user_name
            """
        ).fetchall()

        return render_template(
            "admin/delivery-partners.html",
            partners=partners,
            unassigned_orders=unassigned_orders,
            available_partners=available_partners
        )
    finally:
        conn.close()


@app.route("/admin/delivery-partners/create", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_create_delivery_partner():
    """Admin creates a new driver directly."""
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    phone = request.form.get("phone", "").strip()
    vehicle_type = request.form.get("vehicle_type", "Bicycle").strip()
    license_number = request.form.get("license_number", "").strip()

    conn = get_db()
    try:
        if not all((name, email, password, phone, vehicle_type)) or len(password) < 6:
            return redirect(url_for("admin_delivery_partners"))

        if conn.execute("SELECT user_id FROM users WHERE user_email = ?", (email,)).fetchone():
            return redirect(url_for("admin_delivery_partners"))

        role_id = get_role_id(conn, ROLE_DELIVERY)
        cursor = conn.execute(
            """
            INSERT INTO users (user_name, user_email, user_pass, phone, role_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, email, generate_password_hash(password), phone, role_id)
        )
        conn.execute(
            """
            INSERT INTO delivery_partners (user_id, vehicle_type, license_number, availability_status)
            VALUES (?, ?, ?, 'Offline')
            """,
            (cursor.lastrowid, vehicle_type, license_number or None)
        )
        conn.commit()
        return redirect(url_for("admin_delivery_partners"))
    finally:
        conn.close()


@app.route("/admin/delivery-partners/assign", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_assign_delivery_order():
    """Admin manually assigns an order to a delivery partner."""
    order_id = request.form.get("order_id", type=int)
    partner_id = request.form.get("partner_id", type=int)

    try:
        payout = max(3.50, round(float(request.form.get("payout", "3.5")), 2))
    except (TypeError, ValueError):
        payout = 3.50

    conn = get_db()
    try:
        order = conn.execute(
            """
            SELECT o.*, da.assignment_id
            FROM orders o
            LEFT JOIN delivery_assignments da ON da.order_id = o.order_id
            WHERE o.order_id = ?
            """,
            (order_id,)
        ).fetchone()

        partner = conn.execute(
            "SELECT * FROM delivery_partners WHERE partner_id = ? AND is_active = 1",
            (partner_id,)
        ).fetchone()

        if not order or order["assignment_id"] or not partner:
            return redirect(url_for("admin_delivery_partners"))

        conn.execute(
            """
            INSERT INTO delivery_assignments (order_id, partner_id, status, payout, assigned_at)
            VALUES (?, ?, 'Assigned', ?, CURRENT_TIMESTAMP)
            """,
            (order_id, partner_id, payout)
        )
        conn.execute("UPDATE orders SET status = 'Dispatched' WHERE order_id = ?", (order_id,))
        conn.execute(
            "UPDATE delivery_partners SET availability_status = 'Busy', updated_at = CURRENT_TIMESTAMP WHERE partner_id = ?",
            (partner_id,)
        )
        conn.commit()
        return redirect(url_for("admin_delivery_partners"))
    finally:
        conn.close()


@app.route("/admin/delivery-partners/<int:partner_id>/toggle", methods=["POST"])
@role_required(ROLE_ADMIN)
def admin_toggle_delivery_partner(partner_id):
    """Toggles a delivery driver between active and inactive."""
    conn = get_db()
    try:
        conn.execute(
            "UPDATE delivery_partners SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE partner_id = ?",
            (partner_id,)
        )
        conn.commit()
        return redirect(url_for("admin_delivery_partners"))
    finally:
        conn.close()


# =============================================================================
# SECTION 13: STATIC & LEGACY REDIRECT HANDLERS
# =============================================================================
# Ensures that any old link or direct static asset URL works flawlessly!

@app.route("/project-assets/<path:filename>")
def root_asset(filename):
    """Serves root assets like main.js, scene3d.js, page_3d.js."""
    return send_from_directory(app.root_path, filename)


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
    return redirect(url_for("root_asset", filename=filename))


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


# =============================================================================
# SECTION 14: ERROR HANDLERS
# =============================================================================

@app.errorhandler(404)
def page_not_found(error):
    """Custom 404 page for missing links."""
    return render_template("public/404.html"), 404


@app.errorhandler(403)
def forbidden(error):
    """Custom 403 response for forbidden / CSRF failures."""
    return jsonify({"ok": False, "error": "Forbidden: Invalid or missing CSRF token."}), 403


# =============================================================================
# SECTION 15: RUN THE FLASK SERVER
# =============================================================================

if __name__ == "__main__":
    print("✨ Starting ispice majesty Food Delivery App on http://127.0.0.1:5000 ✨")
    app.run(debug=True)
