import sqlite3

DB = "grocery.db"

def create_tables():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.executescript("""
    PRAGMA foreign_keys = ON;

    -- Categories Table
    CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT
    );

    -- Suppliers Table
    CREATE TABLE IF NOT EXISTS suppliers (
        supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        contact_email TEXT,
        phone TEXT
    );

    -- Inventory Table
    CREATE TABLE IF NOT EXISTS inventory (
        inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0,
        reorder_level INTEGER DEFAULT 5,
        FOREIGN KEY (product_id) REFERENCES products(product_id)
    );
    """)

    conn.commit()
    conn.close()
    print("Extra 3 tables created successfully!")

if __name__ == "__main__":
    create_tables()
