from flask import Flask, render_template, session, render_template_string, request, redirect
import sqlite3
from datetime import date, timedelta, datetime
import re
import random
import string

import os
from werkzeug.utils import secure_filename


app = Flask(__name__)
DB_PATH = "Databases/good_food.db"

UPLOAD_FOLDER = "static/images"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_products():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, image FROM products")
    products = cursor.fetchall()
    conn.close()
    return products

@app.route("/")
def index():
    clear_paid_orders_for_all()
    products = get_products()
    # Fetch all sites and employees for the checkout form
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, location, maestro FROM sites")
    sites = cursor.fetchall()
    cursor.execute("SELECT id, name, site_id FROM employees")
    employees = cursor.fetchall()
    conn.close()
    return render_template("index.html", products=products, sites=sites, employees=employees)

@app.route("/checkout", methods=["POST"])
def checkout():
    products = get_products()
    quantities = {
        item: int(request.form.get("product_" + item, 0))
        for item, _, _ in products
    }

    filtered = {k: v for k, v in quantities.items() if v > 0}

    if not filtered:
        return redirect("/")

    order_items = []
    receipt = []

    for name, price, _ in products:
        qty = filtered.get(name)
        if qty:
            order_items.append(f"{name}:{price};{qty}")
            line_total = qty * price
            receipt.append((name, qty, line_total))

    products_string = ", ".join(order_items)
    timestamp = datetime.today().strftime("%Y-%m-%d %H:%M")

    employee_id = request.form.get("employee_id")

    # Get employee name for display
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM employees WHERE id = ?", (employee_id,))
    employee_name = cursor.fetchone()
    employee_name = employee_name[0] if employee_name else "Unknown"
    conn.close()

    # Store order data in session for later insertion
    session['pending_order'] = {
        'timestamp': timestamp,
        'products_string': products_string,
        'employee_id': employee_id
    }

    return render_template("gracias.html", receipt=receipt, employee_id=employee_id, employee_name=employee_name)

@app.route("/submit_order", methods=["POST"])
def submit_order():
    if 'pending_order' not in session:
        return redirect("/")
    
    # Get the signature data
    signature_data = request.form.get("signature_data", "")
    
    # Create signatures directory if it doesn't exist
    signatures_dir = "static/signatures"
    if not os.path.exists(signatures_dir):
        os.makedirs(signatures_dir)
    
    # Generate filename: date_site_id.png
    timestamp = session['pending_order']['timestamp']
    date_str = timestamp.split()[0]  # Get just the date part
    employee_id = session['pending_order']['employee_id']
    
    # Get site_id for the employee
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT site_id FROM employees WHERE id = ?", (employee_id,))
    site_result = cursor.fetchone()
    site_id = site_result[0] if site_result else "unknown"
    conn.close()
    
    # Create filename
    filename = f"{date_str}_{site_id}_{employee_id}.png"
    filepath = os.path.join(signatures_dir, filename)
    
    # Save signature as image file
    if signature_data.startswith('data:image'):
        # Remove the data URL prefix
        import base64
        signature_data = signature_data.split(',')[1]
        signature_bytes = base64.b64decode(signature_data)
        
        with open(filepath, 'wb') as f:
            f.write(signature_bytes)
    
    # Insert the order into database with file path
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (employee_id, items, signature, date) VALUES (?, ?, ?, ?)",
        (session['pending_order']['employee_id'],
         session['pending_order']['products_string'], 
         filepath,
         session['pending_order']['timestamp'])
    )
    conn.commit()
    conn.close()
    
    # Clear the pending order from session
    session.pop('pending_order', None)
    
    return redirect("/")

@app.route("/products")
def product_manager():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, image FROM products")
    products = cursor.fetchall()
    conn.close()
    return render_template("products.html", products=products)
from pathlib import Path
@app.route("/update", methods=["POST"])
def update_prods():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    i = request.form.get('id')
    name = request.form.get(f'name')
    price = request.form.get(f'price')
    image = request.files.get(f'image')

    if image and image.filename:
        filename = secure_filename(image.filename)
        save_path = Path(UPLOAD_FOLDER) / filename
        image.save(str(save_path))
        image_path = str(save_path)
    else:
        # Get the current image path from DB
        c.execute("SELECT image FROM products WHERE id = ?", (i,))
        current_image = c.fetchone()
        if current_image:
            image_path = current_image[0]
        else:
            image_path = ''

    c.execute("UPDATE products SET name = ?, price = ?, image = ? WHERE id  = ?", (name, price, str(save_path), i))
    conn.commit()
    conn.close()
    return redirect("/products")

@app.route("/products/delete", methods=["POST"])
def delete_product():
    name = request.form["name"]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE name = ?", (name,))
    conn.commit()
    conn.close()
    return redirect("/products")

@app.route("/products/add", methods=["POST"])
def add_product():
    name = request.form["name"]
    price = request.form["price"]
    image = request.files.get("image")
    if image and image.filename:
        filename = secure_filename(image.filename)
        image_path = os.path.join(UPLOAD_FOLDER,filename)
        image.save(image_path)
    else:
        image_path = ""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO products (name, price, image) VALUES (?, ?, ?)", (name, price, image_path))
    conn.commit()
    conn.close()
    return redirect("/products")



app.secret_key = "f92e4b9c638a82e82d1e4e9b4753d1a9fabc1cd2e279c6e7f291f083e82c9b91"

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") == "chrisjamesortiz":
            session["is_admin"] = True
            return redirect("/")
        else:
            return render_template("admin.html", error="Wrong password")
    return render_template("admin.html")
@app.route("/logout", methods = ["POST"])
def logout():
    session.clear()
    return redirect("/")

@app.route("/logout", methods = ["GET"])
def logout_get():
    print(f"Logout GET called - this should not happen")
    return "Please use the logout button in the footer", 405


def parse_order_total(items_str):
    total = 0
    for item in items_str.split(","):
        item = item.strip()
        if ":" in item and ";" in item:
            try:
                name_price, qty = item.split(";", 1)
                _, price = name_price.split(":", 1)
                price = int(price.strip())
                qty = int(qty.strip())
                total += price * qty
            except Exception:
                continue
    return total

def clear_paid_orders_for_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM employees")
    employees = [row[0] for row in c.fetchall()]
    for emp_id in employees:
        # Get all orders (oldest first)
        c.execute("SELECT id, items, date FROM orders WHERE employee_id = ? ORDER BY date", (emp_id,))
        orders = c.fetchall()
        # Get all payments (oldest first)
        c.execute("SELECT id, amount, date FROM payments WHERE employee_id = ? ORDER BY date", (emp_id,))
        payments = c.fetchall()
        
        remaining_payments = payments.copy()
        cleared_orders = []
        
        # Calculate how much we can pay off
        total_payments = sum(payment[1] for payment in payments)
        remaining = total_payments
        
        for order_id, items, date in orders:
            order_total = parse_order_total(items)
            if remaining >= order_total:
                # Move to profit
                c.execute("""INSERT INTO profit (employee_id, original_order_id, items, total_paid, date_cleared)
                             VALUES (?, ?, ?, ?, DATE('now'))""", (emp_id, order_id, items, order_total))
                # Delete from orders
                c.execute("DELETE FROM orders WHERE id = ?", (order_id,))
                remaining -= order_total
                cleared_orders.append((order_id, order_total))
            else:
                break
        
        # Now delete the payments that were used to pay for cleared orders
        if cleared_orders:
            total_cleared = sum(order_total for _, order_total in cleared_orders)
            remaining_to_delete = total_cleared
            
            for payment_id, payment_amount, payment_date in payments:
                if remaining_to_delete <= 0:
                    break
                    
                if payment_amount <= remaining_to_delete:
                    # Delete this entire payment
                    c.execute("DELETE FROM payments WHERE id = ?", (payment_id,))
                    remaining_to_delete -= payment_amount
                else:
                    # This payment was partially used, update it
                    new_amount = payment_amount - remaining_to_delete
                    c.execute("UPDATE payments SET amount = ? WHERE id = ?", (new_amount, payment_id))
                    remaining_to_delete = 0
                    break
    
    conn.commit()
    conn.close()

@app.route("/chart", methods=["GET", "POST"])
def chart():
    clear_paid_orders_for_all()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Handle payment submission if admin and POST
    if request.method == "POST" and session.get("is_admin"):
        site_id = request.form.get("site_id")
        employee_id = request.form.get("employee_id")
        amount = request.form.get("amount")
        note = request.form.get("note")
        payment_key = request.form.get("payment_key")
        
        # Check if this payment key has already been processed
        if payment_key and payment_key not in session.get('processed_payment_keys', []):
            # Store the payment key to prevent duplicate processing
            if 'processed_payment_keys' not in session:
                session['processed_payment_keys'] = []
            session['processed_payment_keys'].append(payment_key)
            
            # Allow payment for all employees at a site
            if employee_id and amount:
                if employee_id == "all" and site_id:
                    # Create a single payment entry for "All" employees
                    # Use the first employee's ID as a placeholder, but mark it as "all" in the note
                    c.execute("SELECT id FROM employees WHERE site_id = ? LIMIT 1", (site_id,))
                    first_emp = c.fetchone()
                    if first_emp:
                        timestamp = datetime.today().strftime("%Y-%m-%d %H:%M")
                        all_note = f"ALL EMPLOYEES: {note}" if note else "ALL EMPLOYEES"
                        c.execute("INSERT INTO payments (employee_id, amount, date, note) VALUES (?, ?, ?, ?)", (first_emp[0], amount, timestamp, all_note))
                        conn.commit()
                elif employee_id != "all":
                    timestamp = datetime.today().strftime("%Y-%m-%d %H:%M")
                    c.execute("INSERT INTO payments (employee_id, amount, date, note) VALUES (?, ?, ?, ?)", (employee_id, amount, timestamp, note))
                    conn.commit()
    # Fetch all sites and employees for the filter form
    c.execute("SELECT id, location, maestro FROM sites")
    sites = c.fetchall()
    c.execute("SELECT id, site_id, name FROM employees")
    employees = c.fetchall()

    # Get selected site and employee from form/query params
    selected_site = request.values.get("site_id")
    selected_employee = request.values.get("employee_id")
    # If a site is selected but employee is blank, treat as 'all'
    if selected_site and not selected_employee:
        selected_employee = 'all'

    # Filter employees for the selected site
    filtered_employees = [e for e in employees if not selected_site or e[1] == selected_site]

    # If 'All' is selected, show all employees for the site
    show_all = (selected_employee == "all")
    orders = []
    grand_total = 0
    if selected_site and (selected_employee and not show_all):
        # Show orders/payments for one employee
        c.execute("SELECT id, items, date, signature FROM orders WHERE employee_id = ? ORDER BY date DESC", (selected_employee,))
        raw_orders = c.fetchall()
        for order in raw_orders:
            order_total = parse_order_total(order[1])
            grand_total += order_total
            orders.append((order[0], order[1], order[2], selected_employee, order_total, order[3]))
        c.execute("SELECT amount, date, note FROM payments WHERE employee_id = ? ORDER BY date DESC", (selected_employee,))
        payments = c.fetchall()
    elif selected_site and show_all:
        emp_ids = [e[0] for e in filtered_employees]
        if emp_ids:
            qmarks = ','.join(['?']*len(emp_ids))
            c.execute(f"SELECT id, items, date, employee_id, signature FROM orders WHERE employee_id IN ({qmarks}) ORDER BY date DESC", emp_ids)
            raw_orders = c.fetchall()
            for order in raw_orders:
                order_total = parse_order_total(order[1])
                grand_total += order_total
                orders.append((order[0], order[1], order[2], order[3], order_total, order[4]))
            c.execute(f"SELECT employee_id, amount, date, note FROM payments WHERE employee_id IN ({qmarks}) ORDER BY date DESC", emp_ids)
            payments = c.fetchall()
        else:
            payments = []
            orders = []
    else:
        payments = []
        orders = []
    conn.close()

    # Build all_entries in Python, with parsed_items for orders
    all_entries = []
    order_total = 0
    payment_total = 0
    
    # Create employee name lookup - convert IDs to strings for consistent matching
    emp_names = {str(emp[0]): emp[2] for emp in employees}
    
    for order in orders:
        parsed_items = []
        for item in order[1].split(","):
            item = item.strip()
            if ":" in item and ";" in item:
                try:
                    name_price, qty = item.split(";", 1)
                    name, price = name_price.split(":", 1)
                    parsed_items.append({
                        'name': name.strip(),
                        'price': int(price.strip()),
                        'qty': int(qty.strip())
                    })
                except Exception:
                    continue
        all_entries.append({
            'type': 'order',
            'employee_id': order[3],
            'employee_name': emp_names.get(str(order[3]), f'Employee #{order[3]}'),
            'date': order[2] if len(order) > 2 else order[1],
            'items': order[1],
            'parsed_items': parsed_items,
            'total': order[4],
            'signature': order[5] if len(order) > 5 else None
        })
        order_total += order[4]
    for payment in payments:
        if show_all:
            emp_id, amount, date, note = payment
        else:
            emp_id, amount, date, note = selected_employee, *payment
        
        # Check if this is an "all employees" payment
        is_all_employees = note and note.startswith("ALL EMPLOYEES")
        
        all_entries.append({
            'type': 'payment',
            'employee_id': emp_id,
            'employee_name': "All" if is_all_employees else emp_names.get(str(emp_id), f'Employee #{emp_id}'),
            'date': date,
            'amount': amount,
            'note': note,
            'items': None,
            'parsed_items': []
        })
        payment_total += amount
    all_entries.sort(key=lambda x: x['date'], reverse=False)  # Oldest first
    net_total = order_total - payment_total

    import uuid
    payment_key = str(uuid.uuid4())
    
    # Get maestro for selected site
    selected_maestro = None
    if selected_site:
        for site_id, location, maestro in sites:
            if site_id == selected_site:
                selected_maestro = maestro
                break
    
    return render_template("chart.html", 
        sites=sites, 
        employees=employees, 
        filtered_employees=filtered_employees,
        selected_site=selected_site,
        selected_employee=selected_employee,
        selected_maestro=selected_maestro,
        show_all=show_all,
        orders=orders,
        payments=payments,
        grand_total=grand_total,
        all_entries=all_entries,
        order_total=order_total,
        payment_total=payment_total,
        net_total=net_total,
        payment_key=payment_key)

@app.route("/del_order", methods = ["POST"])
def del_order():
    order_id = request.form.get('o_id')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("select * from orders")
    row= c.fetchall()
    c.execute("delete from orders where id = ?", (order_id,))

    conn.commit()
    conn.close()
    return redirect("/chart")

@app.route("/test")
def test():
    return render_template("test.html")

@app.route("/sites")
def view_sites():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Get all sites
    cursor.execute("SELECT id, location, total_owing FROM sites")
    sites = cursor.fetchall()
    site_data = []
    for site_id, location, total_owing in sites:
        cursor.execute("SELECT id, current_owing, items, name FROM employees WHERE site_id = ?", (site_id,))
        employees = cursor.fetchall()
        # For each employee, get their orders
        employees_with_orders = []
        for emp in employees:
            emp_id, current_owing, items, name = emp
            # Parse items
            parsed_items = []
            for item in (items or '').split(","):
                item = item.strip()
                if ":" in item and ";" in item:
                    try:
                        name_price, qty = item.split(";", 1)
                        iname, price = name_price.split(":", 1)
                        parsed_items.append({
                            'name': iname.strip(),
                            'price': int(price.strip()),
                            'qty': int(qty.strip())
                        })
                    except Exception:
                        continue
            # Get signature from orders
            cursor.execute("SELECT signature FROM orders WHERE employee_id = ? ORDER BY date DESC LIMIT 1", (emp_id,))
            signature_result = cursor.fetchone()
            signature = signature_result[0] if signature_result else None
            employees_with_orders.append({
                'id': emp_id,
                'name': name or f'Employee #{emp_id}',
                'current_owing': current_owing,
                'items': items,
                'parsed_items': parsed_items,
                'signature': signature
            })
        site_data.append({
            'id': site_id,
            'location': location,
            'total_owing': total_owing,
            'employees': employees_with_orders
        })
    conn.close()
    return render_template("sites.html", sites=site_data)

@app.route("/manage")
def manage():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, location, maestro FROM sites")
    sites = cursor.fetchall()
    site_data = []
    for site_id, location, maestro in sites:
        cursor.execute("SELECT id, current_owing, items, name FROM employees WHERE site_id = ?", (site_id,))
        employees = cursor.fetchall()
        employees_parsed = []
        for emp in employees:
            emp_id, current_owing, items, name = emp
            # Parse items
            parsed_items = []
            for item in (items or '').split(","):
                item = item.strip()
                if ":" in item and ";" in item:
                    try:
                        name_price, qty = item.split(";", 1)
                        iname, price = name_price.split(":", 1)
                        parsed_items.append({
                            'name': iname.strip(),
                            'price': int(price.strip()),
                            'qty': int(qty.strip())
                        })
                    except Exception:
                        continue
            employees_parsed.append({
                'id': emp_id,
                'name': name or f'Employee #{emp_id}',
                'current_owing': current_owing,
                'items': items,
                'parsed_items': parsed_items
            })
        site_data.append({
            'id': site_id,
            'location': location,
            'maestro': maestro,
            'employees': employees_parsed
        })
    conn.close()
    return render_template("manage.html", sites=site_data)

@app.route("/update_site", methods=["POST"])
def update_site():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    site_id = request.form.get("site_id")
    location = request.form.get("location")
    maestro = request.form.get("maestro")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE sites SET location = ?, maestro = ? WHERE id = ?", (location, maestro, site_id))
    conn.commit()
    conn.close()
    
    return redirect("/manage")

@app.route("/delete_site", methods=["POST"])
def delete_site():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    site_id = request.form.get("site_id")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if site exists
        cursor.execute("SELECT id, location FROM sites WHERE id = ?", (site_id,))
        site = cursor.fetchone()
        if not site:
            return f"Site {site_id} not found", 404
        
        
        # Get all employees for this site
        cursor.execute("SELECT id FROM employees WHERE site_id = ?", (site_id,))
        employees = cursor.fetchall()
        
        # Delete all orders for employees at this site
        for emp in employees:
            emp_id = emp[0]
            cursor.execute("DELETE FROM orders WHERE employee_id = ?", (emp_id,))
        
        # Delete all employees for this site
        cursor.execute("DELETE FROM employees WHERE site_id = ?", (site_id,))
        
        # Then delete the site
        cursor.execute("DELETE FROM sites WHERE id = ?", (site_id,))
        
        conn.commit()
        conn.close()
        
        return redirect("/manage")
    except Exception as e:
        return f"Error deleting site: {e}", 500

@app.route("/update_employee", methods=["POST"])
def update_employee():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    employee_id = request.form.get("employee_id")
    employee_name = request.form.get("employee_name")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE employees SET name = ? WHERE id = ?", (employee_name, employee_id))
    conn.commit()
    conn.close()
    
    return redirect("/manage")

@app.route("/delete_employee", methods=["POST"])
def delete_employee():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    employee_id = request.form.get("employee_id")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    conn.commit()
    conn.close()
    
    return redirect("/manage")

@app.route("/add_employee", methods=["POST"])
def add_employee():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    site_id = request.form.get("site_id")
    employee_name = request.form.get("employee_name")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO employees (name, site_id, current_owing, items) VALUES (?, ?, 0, '')", (employee_name, site_id))
    conn.commit()
    conn.close()
    
    return redirect("/manage")

def rand_str(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route("/add_site", methods=["POST"])
def add_site():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    location = request.form.get("location")
    maestro = request.form.get("maestro")
    
    # Generate a random site ID
    site_id = rand_str(8)
    
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sites (id, location, maestro) VALUES (?, ?, ?)", (site_id, location, maestro))
    conn.commit()
    conn.close()
    
    return redirect("/manage")

@app.route("/profit")
def profit():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT employee_id, original_order_id, items, total_paid, date_cleared FROM profit ORDER BY date_cleared DESC")
    profits = c.fetchall()
    # Get employee names for display
    c.execute("SELECT id, name FROM employees")
    emp_names = {row[0]: row[1] for row in c.fetchall()}
    conn.close()
    return render_template("profit.html", profits=profits, emp_names=emp_names)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port = 5000)

