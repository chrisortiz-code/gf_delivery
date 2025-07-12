import sqlite3 as sql

con = sql.connect("Databases/good_food.db")
c = con.cursor()



# # Add new trigger for AFTER INSERT
# c.execute('''
# CREATE TRIGGER IF NOT EXISTS update_site_total_owing_after_insert
# AFTER INSERT ON employees
# BEGIN
#     UPDATE sites
#     SET total_owing = (
#         SELECT COALESCE(SUM(current_owing), 0)
#         FROM employees
#         WHERE site_id = NEW.site_id
#     )
#     WHERE id = NEW.site_id;
# END;
# ''')

# Manual update to fix existing data
# c.execute('''
# UPDATE sites
# SET total_owing = (
#     SELECT COALESCE(SUM(current_owing), 0)
#     FROM employees
#     WHERE site_id = sites.id
# )
# ''')

# Create new orders table for signatures


# Create profit table for cleared orders
c.execute('''
CREATE TABLE IF NOT EXISTS profit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    original_order_id INTEGER NOT NULL,
    items TEXT NOT NULL,
    total_paid INTEGER NOT NULL,
    date_cleared DATE NOT NULL
)
''')

# Migration: Update sites table to add maestro and remove total_owing

# # First, drop the triggers that reference the sites table
# c.execute("DROP TRIGGER IF EXISTS update_site_total_owing")
# c.execute("DROP TRIGGER IF EXISTS update_site_total_owing_after_insert")

# # Create new table structure
# c.execute('''
# CREATE TABLE IF NOT EXISTS sites_new (
#     id TEXT PRIMARY KEY,
#     location TEXT NOT NULL,
#     maestro TEXT DEFAULT 'Boss'
# )
# ''')

# # Copy existing data, setting default maestro value
# c.execute('''
# INSERT INTO sites_new (id, location, maestro)
# SELECT id, location, 'Boss' FROM sites
# ''')

# # Drop old table and rename new one
# c.execute('DROP TABLE sites')
# c.execute('ALTER TABLE sites_new RENAME TO sites')


con.commit()
con.close()
