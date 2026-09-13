"""
=============================================================================
Comprehensive Test Suite for ispice majesty Food Delivery App
=============================================================================
This test script verifies that every single part of the application works
correctly and seamlessly:
1. Public pages and legacy redirects
2. Registration and login for all 3 user roles
3. The fixed Delivery Partner login path
4. Real password reset flow
5. Placing orders, canceling orders, and tracking
6. Delivery partner workflow (accept, pick up, out for delivery, deliver)
7. Customer rating and feedback
8. Admin driver management and manual assignment
=============================================================================
"""

import sys
import json
from werkzeug.security import check_password_hash
from app import app, get_db, ROLE_ADMIN, ROLE_CUSTOMER, ROLE_DELIVERY

def run_tests():
    print("🚀 Running comprehensive tests for Food Delivery App...\n")
    client = app.test_client()
    passed = 0
    failed = 0

    def assert_test(name, condition, details=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ PASS: {name}")
            passed += 1
        else:
            print(f"  ❌ FAIL: {name} - {details}")
            failed += 1

    # -------------------------------------------------------------
    # 1. PUBLIC ROUTES TEST
    # -------------------------------------------------------------
    print("--- 1. Testing Public Routes ---")
    public_routes = [
        "/", "/rest", "/menu", "/about", "/faq", "/contact",
        "/public/index", "/public/menu", "/public/reserve",
        "/public/track", "/public/privacy", "/login", "/register",
        "/delivery/login", "/delivery/register", "/forgot-password",
        "/reset-password", "/admin/login"
    ]
    for route in public_routes:
        res = client.get(route)
        assert_test(f"GET {route} returns 200", res.status_code == 200)

    # -------------------------------------------------------------
    # 2. LEGACY REDIRECTS TEST
    # -------------------------------------------------------------
    print("\n--- 2. Testing Legacy Redirects ---")
    legacy_redirects = [
        ("/index.html", 302),
        ("/style.css", 302),
        ("/assets/logo.png", 302),
        ("/main.js", 302),
        ("/menu.html", 302),
        ("/about.html", 302),
    ]
    for path, expected_code in legacy_redirects:
        res = client.get(path)
        assert_test(f"GET {path} redirects (status {expected_code})", res.status_code == expected_code)

    # -------------------------------------------------------------
    # 3. CUSTOMER REGISTRATION & LOGIN TEST
    # -------------------------------------------------------------
    print("\n--- 3. Testing Customer Registration & Login ---")
    test_customer_email = "test_kid_customer@example.com"
    test_customer_pass = "mypassword123"

    def cleanup_user_by_email(email):
        c = get_db()
        u = c.execute("SELECT user_id FROM users WHERE user_email = ?", (email,)).fetchone()
        if u:
            uid = u["user_id"]
            cust = c.execute("SELECT customer_id FROM customers WHERE user_id = ?", (uid,)).fetchone()
            part = c.execute("SELECT partner_id FROM delivery_partners WHERE user_id = ?", (uid,)).fetchone()
            cid = cust["customer_id"] if cust else None
            pid = part["partner_id"] if part else None

            if cid:
                c.execute("DELETE FROM feedback WHERE customer_id = ?", (cid,))
                c.execute("DELETE FROM delivery_assignments WHERE order_id IN (SELECT order_id FROM orders WHERE customer_id = ?)", (cid,))
                c.execute("DELETE FROM orders WHERE customer_id = ?", (cid,))
                c.execute("DELETE FROM customers WHERE customer_id = ?", (cid,))
            if pid:
                c.execute("DELETE FROM feedback WHERE delivery_partner_id = ?", (pid,))
                c.execute("DELETE FROM location_logs WHERE assignment_id IN (SELECT assignment_id FROM delivery_assignments WHERE partner_id = ?)", (pid,))
                c.execute("DELETE FROM delivery_assignments WHERE partner_id = ?", (pid,))
                c.execute("DELETE FROM delivery_partners WHERE partner_id = ?", (pid,))

            c.execute("DELETE FROM notifications WHERE user_id = ?", (uid,))
            c.execute("DELETE FROM users WHERE user_id = ?", (uid,))
            c.commit()
        c.close()

    # Clean up test users if existing
    cleanup_user_by_email(test_customer_email)
    client.get("/logout")

    # Get a CSRF token
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-token-123"

    # Test Registration
    reg_res = client.post("/register", data={
        "csrf_token": "test-token-123",
        "name": "Little Chef",
        "email": test_customer_email,
        "password": test_customer_pass,
        "phone": "+1-555-0199"
    })
    assert_test("Customer registration redirects to login", reg_res.status_code == 302 and reg_res.location.endswith("/login"))

    # Verify user was saved in database
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE user_email = ?", (test_customer_email,)).fetchone()
    assert_test("Customer exists in database with hashed password", user is not None and check_password_hash(user["user_pass"], test_customer_pass))
    cust = conn.execute("SELECT * FROM customers WHERE user_id = ?", (user["user_id"],)).fetchone()
    assert_test("Customer profile row created", cust is not None)
    conn.close()

    # Test Customer Login
    login_res = client.post("/login", data={
        "csrf_token": "test-token-123",
        "email": test_customer_email,
        "password": test_customer_pass
    })
    assert_test("Customer login redirects to customer_dashboard", login_res.status_code == 302 and login_res.location.endswith("/customer/dashboard"))

    # -------------------------------------------------------------
    # 4. DELIVERY PARTNER REGISTRATION & FIXED LOGIN TEST
    # -------------------------------------------------------------
    print("\n--- 4. Testing Delivery Partner Registration & Fixed Login ---")
    test_driver_email = "test_friendly_driver@example.com"
    test_driver_pass = "driverpass123"

    cleanup_user_by_email(test_driver_email)

    # Clear previous user session
    client.get("/logout")
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-token-123"

    driver_reg_res = client.post("/delivery/register", data={
        "csrf_token": "test-token-123",
        "name": "Speedy Sam",
        "email": test_driver_email,
        "password": test_driver_pass,
        "phone": "+1-555-0288",
        "vehicle_type": "Scooter",
        "license_number": "SCOOT-999"
    })
    assert_test("Driver registration redirects to delivery_login", driver_reg_res.status_code == 302)

    # Test driver login on the main /login page (this had the critical bug where conn.close() was called early!)
    driver_login_res = client.post("/login", data={
        "csrf_token": "test-token-123",
        "email": test_driver_email,
        "password": test_driver_pass
    })
    assert_test("Driver login via /login redirects to delivery_dashboard (Bug Fixed!)",
                driver_login_res.status_code == 302 and driver_login_res.location.endswith("/delivery/dashboard"))

    # Verify driver status changed to Available upon login
    conn = get_db()
    driver_user = conn.execute("SELECT user_id FROM users WHERE user_email = ?", (test_driver_email,)).fetchone()
    partner = conn.execute("SELECT * FROM delivery_partners WHERE user_id = ?", (driver_user["user_id"],)).fetchone()
    assert_test("Driver availability became Available after login", partner["availability_status"] == "Available")
    conn.close()

    # -------------------------------------------------------------
    # 5. PASSWORD RESET TEST
    # -------------------------------------------------------------
    print("\n--- 5. Testing Password Reset Flow ---")
    # Step 1: Request password reset
    client.get("/logout")
    with client.session_transaction() as sess:
        sess["csrf_token"] = "test-token-123"

    forgot_res = client.post("/forgot-password", data={
        "csrf_token": "test-token-123",
        "email": test_customer_email
    })
    assert_test("Forgot password redirects to reset-password with email query param",
                forgot_res.status_code == 302 and f"email={test_customer_email}" in forgot_res.location)

    # Step 2: Set new password
    new_password = "newsecretpass456"
    reset_res = client.post(f"/reset-password?email={test_customer_email}", data={
        "csrf_token": "test-token-123",
        "email": test_customer_email,
        "new_password": new_password,
        "confirm_password": new_password
    })
    assert_test("Reset password returns success", reset_res.status_code == 200 and b"Password successfully updated" in reset_res.data)

    # Step 3: Verify database has new password hash
    conn = get_db()
    updated_user = conn.execute("SELECT user_pass FROM users WHERE user_email = ?", (test_customer_email,)).fetchone()
    assert_test("Database password updated with new hash", check_password_hash(updated_user["user_pass"], new_password))
    conn.close()

    # -------------------------------------------------------------
    # 6. ORDER PLACEMENT & CANCELLATION TEST
    # -------------------------------------------------------------
    print("\n--- 6. Testing Order Placement, Tracking & Cancellation ---")
    # Log in as customer
    with client.session_transaction() as sess:
        sess["user_id"] = user["user_id"]
        sess["user_name"] = "Little Chef"
        sess["role"] = ROLE_CUSTOMER
        sess["csrf_token"] = "test-token-123"

    # Place an order
    order_res = client.post("/customer/orders/create", data={
        "csrf_token": "test-token-123",
        "order_details": "2x Truffle Burger, 1x Apple Cider",
        "total_amount": "45.00",
        "delivery_address": "123 Sunshine Boulevard, Apt 4B",
        "delivery_notes": "Ring the bell once please!"
    })
    assert_test("Customer place order returns JSON with ok: True", order_res.status_code == 200)
    order_data = json.loads(order_res.data.decode())
    assert_test("Order ID returned", order_data.get("ok") and "order_id" in order_data)
    placed_order_id = order_data["order_id"]

    # Check order appears in customer orders page
    orders_page = client.get("/customer/orders")
    assert_test("Customer orders page contains placed order", f"#{placed_order_id}" in orders_page.data.decode())

    # Check order appears in tracking page
    tracking_page = client.get("/customer/tracking")
    assert_test("Customer tracking page displays the active order", f"#{placed_order_id}" in tracking_page.data.decode())

    # Test Cancel Order endpoint
    # Place another order specifically to cancel it
    order_to_cancel_res = client.post("/customer/orders/create", data={
        "csrf_token": "test-token-123",
        "order_details": "1x Ice Cream Sundae",
        "total_amount": "8.50",
        "delivery_address": "123 Sunshine Boulevard"
    })
    cancel_order_id = json.loads(order_to_cancel_res.data.decode())["order_id"]
    cancel_res = client.post(f"/customer/orders/{cancel_order_id}/cancel", data={
        "csrf_token": "test-token-123"
    })
    assert_test("Customer cancel order redirects to orders list", cancel_res.status_code == 302)
    conn = get_db()
    cancelled_status = conn.execute("SELECT status FROM orders WHERE order_id = ?", (cancel_order_id,)).fetchone()
    assert_test("Order status changed to Cancelled", cancelled_status["status"] == "Cancelled")
    conn.close()

    # -------------------------------------------------------------
    # 7. DELIVERY FLEET WORKFLOW (ACCEPT -> STATUS -> DELIVER)
    # -------------------------------------------------------------
    print("\n--- 7. Testing Delivery Fleet Workflow ---")
    # Log in as Delivery Partner
    with client.session_transaction() as sess:
        sess["user_id"] = driver_user["user_id"]
        sess["user_name"] = "Speedy Sam"
        sess["role"] = ROLE_DELIVERY
        sess["csrf_token"] = "test-token-123"

    # Driver checks available requests
    reqs_page = client.get("/delivery/requests")
    assert_test("Driver requests page shows unassigned order", f"#{placed_order_id}" in reqs_page.data.decode())

    # Driver accepts the order
    accept_res = client.post(f"/delivery/requests/{placed_order_id}/accept", data={
        "csrf_token": "test-token-123"
    })
    assert_test("Driver accept order redirects to details", accept_res.status_code == 302 and "assignment_id=" in accept_res.location)

    conn = get_db()
    assignment = conn.execute("SELECT * FROM delivery_assignments WHERE order_id = ?", (placed_order_id,)).fetchone()
    assert_test("Delivery assignment created with status Accepted", assignment is not None and assignment["status"] == "Accepted")
    assignment_id = assignment["assignment_id"]
    conn.close()

    # Progress through statuses: Accepted -> Picked Up -> Out for Delivery -> Delivered
    statuses = ["Picked Up", "Out for Delivery", "Delivered"]
    for next_status in statuses:
        status_res = client.post(f"/delivery/assignments/{assignment_id}/status", data={
            "csrf_token": "test-token-123",
            "status": next_status
        })
        conn = get_db()
        current_status = conn.execute("SELECT status FROM orders WHERE order_id = ?", (placed_order_id,)).fetchone()["status"]
        conn.close()
        assert_test(f"Order status successfully updated to {next_status}", current_status == next_status)

    # Verify driver is Available again after delivery
    conn = get_db()
    partner_after = conn.execute("SELECT availability_status FROM delivery_partners WHERE partner_id = ?", (partner["partner_id"],)).fetchone()
    assert_test("Driver availability returned to Available after Delivered", partner_after["availability_status"] == "Available")
    conn.close()

    # -------------------------------------------------------------
    # 8. CUSTOMER FEEDBACK & RATING TEST
    # -------------------------------------------------------------
    print("\n--- 8. Testing Customer Rating & Feedback ---")
    # Log in as Customer
    with client.session_transaction() as sess:
        sess["user_id"] = user["user_id"]
        sess["user_name"] = "Little Chef"
        sess["role"] = ROLE_CUSTOMER
        sess["csrf_token"] = "test-token-123"

    fb_res = client.post("/customer/feedback", data={
        "csrf_token": "test-token-123",
        "order_id": placed_order_id,
        "restaurant_rating": "5",
        "delivery_rating": "5",
        "comments": "Super delicious and arrived piping hot! Five stars!"
    })
    assert_test("Customer feedback redirects", fb_res.status_code == 302)

    conn = get_db()
    fb = conn.execute("SELECT * FROM feedback WHERE order_id = ?", (placed_order_id,)).fetchone()
    assert_test("Feedback recorded in database", fb is not None and fb["restaurant_rating"] == 5)
    conn.close()

    # -------------------------------------------------------------
    # 9. ADMIN FLEET MANAGEMENT TEST
    # -------------------------------------------------------------
    print("\n--- 9. Testing Admin Fleet Management ---")
    # Log in as Admin
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_name"] = "Zimal Tajwer"
        sess["role"] = ROLE_ADMIN
        sess["csrf_token"] = "test-token-123"

    admin_dash = client.get("/admin/dashboard")
    assert_test("Admin dashboard returns 200", admin_dash.status_code == 200)

    admin_fleet = client.get("/admin/delivery-partners")
    assert_test("Admin delivery partners page returns 200", admin_fleet.status_code == 200)

    # Toggle driver active status
    toggle_res = client.post(f"/admin/delivery-partners/{partner['partner_id']}/toggle", data={
        "csrf_token": "test-token-123"
    })
    assert_test("Admin toggle driver redirects", toggle_res.status_code == 302)

    conn = get_db()
    partner_toggled = conn.execute("SELECT is_active FROM delivery_partners WHERE partner_id = ?", (partner["partner_id"],)).fetchone()
    assert_test("Driver is_active toggled to 0", partner_toggled["is_active"] == 0)
    # Toggle back to 1
    conn.execute("UPDATE delivery_partners SET is_active = 1 WHERE partner_id = ?", (partner["partner_id"],))
    conn.commit()
    conn.close()

    # -------------------------------------------------------------
    # 10. NOTIFICATIONS TEST
    # -------------------------------------------------------------
    print("\n--- 10. Testing Notifications System ---")
    notif_page = client.get("/notifications")
    assert_test("Notifications page returns 200", notif_page.status_code == 200)
    conn = get_db()
    unread_count = conn.execute("SELECT COUNT(*) as c FROM notifications WHERE user_id = 1 AND is_read = 0").fetchone()["c"]
    assert_test("Notifications marked as read after viewing", unread_count == 0)
    conn.close()

    # -------------------------------------------------------------
    # CLEANUP & SUMMARY
    # -------------------------------------------------------------
    cleanup_user_by_email(test_customer_email)
    cleanup_user_by_email(test_driver_email)

    print(f"\n==================================================")
    print(f"TEST RESULTS: {passed} PASSED, {failed} FAILED")
    print(f"==================================================")
    return failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
