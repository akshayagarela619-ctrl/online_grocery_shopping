import sqlite3

DB = "grocery.db"

def insert_sample_data():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # Insert categories
    cur.executescript("""
    INSERT OR IGNORE INTO categories (name, description) VALUES 
        ('Fruits & Vegetables', 'Fresh daily produce'),
        ('Dairy Products', 'Milk, cheese, paneer, butter'),
        ('Bakery', 'Bread and baked items'),
        ('Snacks', 'Chips, biscuits, packaged snacks'),
        ('Beverages', 'Juice, tea, coffee, soft drinks');
    """)

    # Insert suppliers
    cur.executescript("""
    INSERT OR IGNORE INTO suppliers (name, contact_email, phone) VALUES
        ('Fresh Farm Ltd', 'freshfarm@gmail.com', '9876543210'),
        ('Daily Dairy Co', 'dairyco@gmail.com', '9123456789'),
        ('BakeHouse Foods', 'bakehouse@gmail.com', '9988776655');
    """)

    # Insert inventory rows (match product_id from your products table)
    cur.executescript("""
    INSERT OR IGNORE INTO inventory (product_id, stock, reorder_level) VALUES
        (1, 50, 5),
        (2, 30, 10),
        (3, 80, 15);
    """)

    conn.commit()
    conn.close()
    print("Sample data added successfully!")

if __name__ == "__main__":
    insert_sample_data()
