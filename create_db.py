import sqlite3, os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "grocery.db")

# Create the database file
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price REAL,
    category TEXT,
    stock INTEGER
)
""")

# sample data
c.execute("INSERT INTO products (name, price, category, stock) VALUES ('Rice', 40, 'Grains', 50)")
c.execute("INSERT INTO products (name, price, category, stock) VALUES ('Milk', 25, 'Dairy', 20)")
c.execute("INSERT INTO products (name, price, category, stock) VALUES ('Sugar', 45, 'Essentials', 30)")

conn.commit()
conn.close()

print("Database created at", db_path)
