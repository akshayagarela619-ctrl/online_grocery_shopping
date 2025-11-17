from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
import hashlib
import logging
import traceback

# --------- App setup ----------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# Configure logging (Render shows these logs)
logging.basicConfig(level=logging.INFO)

def get_db():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(BASE_DIR, "grocery.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

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
    if q:
        like = f"%{q}%"
        items = conn.execute(
            "SELECT * FROM products WHERE name LIKE ? OR category LIKE ? ORDER BY name",
            (like, like)
        ).fetchall()
    else:
        items = conn.execute("SELECT * FROM products ORDER BY name").fetchall()
    conn.close()
    return render_template("products.html", items=items, q=q)

@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    p = conn.execute("SELECT * FROM products WHERE product_id = ?", (pid,)).fetchone()
    conn.close()
    if not p:
        return "Product not found", 404
    return render_template("product_detail.html", p=p)

# ---------- CART ----------
def get_product(product_id):
    conn = get_db()
    p = conn.execute("SELECT product_id, name, price FROM products WHERE product_id = ?", (product_id,)).fetchone()
    conn.close()
    return p

@app.route("/add_to_cart/<int:pid>", methods=["POST","GET"])
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
        for pid_str, qty in cart.items():
            try:
                pid = int(pid_str)
            except:
                continue

            p = conn.execute("SELECT * FROM products WHERE product_id = ?", (pid,)).fetchone()
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
@app.route("/checkout", methods=["GET","POST"])
def checkout():
    if "user_id" not in session:
        return redirect("/login")

    cart = session.get("cart", {}) or {}
    if not cart:
        flash("Your cart is empty.")
        return redirect("/products")

    conn = get_db()
    cur = conn.cursor()

    total = 0.0
    order_items = []

    for pid_str, qty in cart.items():
        try:
            pid = int(pid_str)
        except:
            continue
        row = conn.execute("SELECT product_id, price FROM products WHERE product_id = ?", (pid,)).fetchone()
        if not row:
            continue
        price = float(row["price"])
        total += price * int(qty)
        order_items.append((pid, int(qty), price))

    # Insert order
    cur.execute("INSERT INTO orders (user_id, total) VALUES (?, ?)", (session["user_id"], total))
    order_id = cur.lastrowid

    # Insert items
    for pid, qty, price in order_items:
        cur.execute(
            "INSERT INTO order_items (order_id, product_id, qty, price) VALUES (?, ?, ?, ?)",
            (order_id, pid, qty, price)
        )

    conn.commit()
    conn.close()

    session.pop("cart", None)

    return redirect(url_for("order_confirmation", oid=order_id))

# ---------- ORDER CONFIRMATION ----------
@app.route("/order-confirmation/<int:oid>")
def order_confirmation(oid):
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    order_row = conn.execute(
        "SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
        (oid, session["user_id"])
    ).fetchone()

    if not order_row:
        conn.close()
        return "Order not found", 404

    items_rows = conn.execute("""
        SELECT oi.qty, oi.price, p.name, p.product_id
        FROM order_items oi
        JOIN products p ON oi.product_id = p.product_id
        WHERE oi.order_id = ?
    """, (oid,)).fetchall()

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
    order = conn.execute(
        "SELECT * FROM orders WHERE order_id = ? AND user_id = ?",
        (oid, session["user_id"])
    ).fetchone()

    if not order:
        conn.close()
        return "Order not found", 404

    items = conn.execute(
        "SELECT oi.qty, oi.price, p.name FROM order_items oi "
        "JOIN products p ON oi.product_id = p.product_id WHERE oi.order_id = ?",
        (oid,)
    ).fetchall()

    conn.close()
    return render_template("order_detail.html", order=order, items=items)

# ---------- FIXED /orders (NO created_at NEEDED) ----------
@app.route("/orders")
def my_orders():
    if "user_id" not in session:
        return redirect("/login")

    conn = get_db()
    try:
        orders = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY COALESCE(created_at, order_id) DESC",
            (session["user_id"],)
        ).fetchall()

        orders_list = []
        for o in orders:
            items = conn.execute(
                "SELECT oi.qty, oi.price, p.name FROM order_items oi "
                "JOIN products p ON oi.product_id = p.product_id WHERE oi.order_id = ?",
                (o["order_id"],)
            ).fetchall()

            orders_list.append({"order": o, "items": items})

        conn.close()
        return render_template("orders.html", orders=orders_list)

    except Exception as e:
        logging.error("ERROR in /orders: %s", e)
        logging.error(traceback.format_exc())
        conn.close()
        return "An error occurred. Check logs.", 500

# ---------- AUTH ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")

        if not (name and email and password):
            return "All fields required.", 400

        hashed = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db()
        try:
            conn.execute(
                "INSERT INTO users (name,email,password) VALUES (?,?,?)",
                (name,email,hashed)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Email already registered."
        conn.close()

        return redirect("/login")

    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")

        hashed = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email,hashed)
        ).fetchone()
        conn.close()

        if user:
            session["user_id"]   = user["user_id"]
            session["user"]      = user["name"]
            session["user_name"] = user["name"]
            session["email"]     = user["email"]
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

    if request.method == "POST":
        new_name = request.form.get("name","").strip()
        new_email = request.form.get("email","").strip().lower()

        conn.execute(
            "UPDATE users SET name=?, email=? WHERE user_id=?",
            (new_name,new_email,session["user_id"])
        )
        conn.commit()

        session["user_name"] = new_name
        session["email"] = new_email

        conn.close()
        return redirect("/dashboard")

    user = conn.execute(
        "SELECT * FROM users WHERE user_id=?",
        (session["user_id"],)
    ).fetchone()
    conn.close()

    return render_template("profile.html", user=user)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------- REPORT PAGE ----------
@app.route("/report")
def report():
    conn = get_db()
    tables = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()

    tables = [t["name"] for t in tables]
    data = []

    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        columns = [c["name"] for c in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        rows_list = [dict(r) for r in rows]
        data.append({"table": table, "columns": columns, "rows": rows_list})

    conn.close()
    return render_template("report.html", data=data)

# ---------- RUN ----------
if __name__ == "__main__":
    print("Starting Flask server...")
    app.run(debug=True)
