# app.py  -- MySQL-adapted version of your original file
from types import SimpleNamespace
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import os
import hashlib
import logging
import traceback
import mysql.connector
from mysql.connector import Error

# --------- App setup ----------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# Configure logging (Render shows these logs)
logging.basicConfig(level=logging.INFO)


# ---------- DB helpers ----------
def get_db():
    """
    Returns a mysql.connector connection. Use environment variables to configure.
    MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DB (defaults provided)
    """
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        user=os.environ.get("MYSQL_USER", "root"),
        password=os.environ.get("MYSQL_PASSWORD", ""),
        database=os.environ.get("MYSQL_DB", "grocery_db"),
        autocommit=False
    )

def dict_cursor(conn):
    """Return a dictionary cursor from a given connection"""
    return conn.cursor(dictionary=True)


# ---------- Context processor ----------
@app.context_processor
def inject_cart_count():
    cart = session.get("cart") or {}
    try:
        cart_count = sum(int(q) for q in cart.values())
    except:
        cart_count = 0
    return {"cart_count": cart_count}


# ---------- Home ----------
@app.route("/")
def home():
    return render_template("index.html")


# ---------- Products ----------
@app.route("/products")
def products():
    q = request.args.get("q", "").strip()
    conn = get_db()
    cur = dict_cursor(conn)
    try:
        if q:
            like = f"%{q}%"
            cur.execute(
                "SELECT * FROM products WHERE name LIKE %s OR category LIKE %s ORDER BY name",
                (like, like)
            )
        else:
            cur.execute("SELECT * FROM products ORDER BY name")
        items = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template("products.html", items=items, q=q)


@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT * FROM products WHERE product_id = %s", (pid,))
        p = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not p:
        return "Product not found", 404
    return render_template("product_detail.html", p=p)


# ---------- CART ----------
def get_product(product_id):
    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute("SELECT product_id, name, price FROM products WHERE product_id = %s", (product_id,))
        p = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    return p


@app.route("/add_to_cart/<int:pid>", methods=["POST", "GET"])
def add_to_cart(pid):
    qty = 1
    if request.method == "POST":
        try:
            qty = int(request.form.get("qty", 1))
        except:
            qty = 1

    p = get_product(pid)
    if not p:
        return "Product not found", 404

    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + qty
    session["cart"] = cart
    return redirect("/cart")


@app.route("/cart")
def cart():
    cart = session.get("cart", {}) or {}
    items = []
    total = 0.0

    if cart:
        conn = get_db()
        cur = dict_cursor(conn)
        try:
            for pid_str, qty in cart.items():
                try:
                    pid = int(pid_str)
                except:
                    continue

                cur.execute("SELECT * FROM products WHERE product_id = %s", (pid,))
                p = cur.fetchone()
                if p:
                    subtotal = float(p["price"]) * int(qty)
                    items.append({
                        "product_id": p["product_id"],
                        "name": p["name"],
                        "price": p["price"],
                        "qty": int(qty),
                        "subtotal": subtotal
                    })
                    total += subtotal
        finally:
            cur.close()
            conn.close()

    return render_template("cart.html", items=items, total=total)


@app.route("/update_cart", methods=["POST"])
def update_cart():
    new_cart = {}
    for key, value in request.form.items():
        if key.startswith("qty_"):
            pid = key.split("_")[1]
            try:
                q = int(value)
            except:
                q = 0
            if q > 0:
                new_cart[pid] = q
    session["cart"] = new_cart
    return redirect("/cart")


@app.route("/remove_from_cart/<int:pid>")
def remove_from_cart(pid):
    cart = session.get("cart", {}) or {}
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect("/cart")


# ---------- CHECKOUT ----------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if "user_id" not in session:
        return redirect("/login")

    cart = session.get("cart", {}) or {}
    if not cart:
        flash("Your cart is empty.")
        return redirect("/products")

    conn = get_db()
    cur = dict_cursor(conn)
    # We'll also use a non-dict cursor for inserts to access lastrowid reliably
    write_cur = conn.cursor()
    total = 0.0
    order_items = []

    try:
        for pid_str, qty in cart.items():
            try:
                pid = int(pid_str)
            except:
                continue
            cur.execute("SELECT product_id, price, stock FROM products WHERE product_id = %s", (pid,))
            row = cur.fetchone()
            if not row:
                continue
            price = float(row["price"])
            total += price * int(qty)
            order_items.append((pid, int(qty), price, row.get("stock")))

        # Insert order
        write_cur.execute("INSERT INTO orders (user_id, total) VALUES (%s, %s)", (session["user_id"], total))
        order_id = write_cur.lastrowid

        # Insert items and decrement stock safely
        for pid, qty, price, stock in order_items:
            write_cur.execute(
                "INSERT INTO order_items (order_id, product_id, qty, price) VALUES (%s, %s, %s, %s)",
                (order_id, pid, qty, price)
            )
            # Decrement stock if the column exists and stock is not NULL
            try:
                write_cur.execute(
                    "UPDATE products SET stock = stock - %s WHERE product_id = %s AND (stock IS NULL OR stock >= %s)",
                    (qty, pid, qty)
                )
            except Exception:
                # ignore if product has no stock column or update fails; primary demo is orders/order_items
                pass

        conn.commit()
    except Error as e:
        conn.rollback()
        logging.error("Checkout DB error: %s", e)
        return "An error occurred while placing your order.", 500
    finally:
        try:
            cur.close()
        except:
            pass
        try:
            write_cur.close()
        except:
            pass
        conn.close()

    session.pop("cart", None)
    return redirect(url_for("order_confirmation", oid=order_id))


# ---------- ORDER CONFIRMATION ----------
@app.route("/order-confirmation/<int:oid>")
def order_confirmation(oid):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT * FROM orders WHERE order_id = %s AND user_id = %s",
            (oid, session["user_id"])
        )
        order_row = cur.fetchone()

        if not order_row:
            return "Order not found", 404

        cur.execute("""
            SELECT oi.qty, oi.price, p.name, p.product_id
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            WHERE oi.order_id = %s
        """, (oid,))
        items_rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    return render_template(
        "order_confirmation.html",
        order=dict(order_row),
        items=[dict(r) for r in items_rows]
    )


# ---------- VIEW SINGLE ORDER ----------
@app.route("/orders/<int:oid>")
def order_detail(oid):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT * FROM orders WHERE order_id = %s AND user_id = %s",
            (oid, session["user_id"])
        )
        order = cur.fetchone()

        if not order:
            return "Order not found", 404

        cur.execute(
            "SELECT oi.qty, oi.price, p.name FROM order_items oi "
            "JOIN products p ON oi.product_id = p.product_id WHERE oi.order_id = %s",
            (oid,)
        )
        items = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    return render_template("order_detail.html", order=order, items=items)


# ---------- /orders (list) ----------
@app.route("/orders")
def my_orders():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = dict_cursor(conn)
    try:
        cur.execute(
            "SELECT * FROM orders WHERE user_id = %s ORDER BY COALESCE(created_at, order_id) DESC",
            (session["user_id"],)
        )
        orders = cur.fetchall()

        orders_list = []
        for o in orders:
            cur.execute(
                "SELECT oi.qty, oi.price, p.name FROM order_items oi "
                "JOIN products p ON oi.product_id = p.product_id WHERE oi.order_id = %s",
                (o["order_id"],)
            )
            items = cur.fetchall()
            orders_list.append(SimpleNamespace(order=o, items=items))
    except Exception as e:
        logging.error("ERROR in /orders: %s", e)
        logging.error(traceback.format_exc())
        cur.close()
        conn.close()
        return "An error occurred. Check logs.", 500
    finally:
        cur.close()
        conn.close()
    return render_template("orders.html", orders=orders_list)


# ---------- AUTH ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not (name and email and password):
            return "All fields required.", 400

        hashed = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, hashed)
            )
            conn.commit()
        except Error as e:
            conn.rollback()
            logging.error("Signup error: %s", e)
            cur.close()
            conn.close()
            return "Email already registered or other DB error."
        cur.close()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        hashed = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db()
        cur = dict_cursor(conn)
        try:
            cur.execute(
                "SELECT * FROM users WHERE email = %s AND password = %s",
                (email, hashed)
            )
            user = cur.fetchone()
        finally:
            cur.close()
            conn.close()

        if user:
            session["user_id"] = user["user_id"]
            session["user"] = user["name"]
            session["user_name"] = user["name"]
            session["email"] = user["email"]
            return redirect("/dashboard")

        return "Invalid login."

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/login")

    user = {
        "user_id": session["user_id"],
        "name": session["user_name"],
        "email": session["email"]
    }

    return render_template("dashboard.html", user=user)


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()
    try:
        if request.method == "POST":
            new_name = request.form.get("name", "").strip()
            new_email = request.form.get("email", "").strip().lower()

            cur.execute(
                "UPDATE users SET name=%s, email=%s WHERE user_id=%s",
                (new_name, new_email, session["user_id"])
            )
            conn.commit()

            session["user_name"] = new_name
            session["email"] = new_email

            cur.close()
            conn.close()
            return redirect("/dashboard")

        cur2 = dict_cursor(conn)
        cur2.execute("SELECT * FROM users WHERE user_id = %s", (session["user_id"],))
        user = cur2.fetchone()
    finally:
        try:
            cur2.close()
        except:
            pass
        try:
            cur.close()
        except:
            pass
        conn.close()

    return render_template("profile.html", user=user)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------- REPORT PAGE (MySQL-friendly) ----------
@app.route("/report")
def report():
    """
    Enumerate all user tables in the current DB and return their columns + rows.
    """
    conn = get_db()
    cur = dict_cursor(conn)
    data = []
    try:
        # list user tables in the current database
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'")
        tables = [r["table_name"] for r in cur.fetchall()]

        for table in tables:
            # columns
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s ORDER BY ordinal_position",
                (table,)
            )
            columns = [c["column_name"] for c in cur.fetchall()]

            # rows
            # build safe SQL - using format for table name is safe because table came from information_schema
            cur.execute(f"SELECT * FROM `{table}`")
            rows = cur.fetchall()
            rows_list = [dict(r) for r in rows]

            data.append({"table": table, "columns": columns, "rows": rows_list})
    finally:
        cur.close()
        conn.close()

    return render_template("report.html", data=data)


# ---------- RUN ----------
if __name__ == "__main__":
    print("Starting Flask server...")
    # ensure FLASK_DEBUG environment variable set separately if needed
    app.run(debug=True)
