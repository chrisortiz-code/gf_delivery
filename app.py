from flask import Flask, render_template, session, render_template_string, request, redirect, flash, get_flashed_messages
import sqlite3
from datetime import date, timedelta, datetime
import re
import random
import string
from pathlib import Path
import os
from werkzeug.utils import secure_filename
from werkzeug.utils import secure_filename
import re
from flask import url_for
import uuid


app = Flask(__name__)
DB_PATH = "Databases/good_food.db"

UPLOAD_FOLDER = "static/images"
@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html', error=error), 500
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def get_products():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, image FROM products ORDER BY position ASC, id ASC")
    products = cursor.fetchall()
    conn.close()
    return products

def smart_capitalize(name):
    # Remove special characters except spaces and slashes
    name = re.sub(r'[^\w\s/]', ' ', name)
    def cap_word(word, is_first):
        if is_first or len(word) > 3:
            return word.capitalize()
        return word.lower()
    words = re.split(r'(\s+)', name)  # Keep spaces
    result = []
    first = True
    for w in words:
        if w.strip() == '':
            result.append(w)
        else:
            result.append(cap_word(w, first))
            if w.strip():
                first = False
    return ''.join(result).strip()


@app.route("/")
def index():
    clear_paid_orders_for_all()
    products = get_products()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Load all sites
    cursor.execute("SELECT id, location FROM sites")
    sites = cursor.fetchall()
    # Load all bosses
    cursor.execute("SELECT id, name, site_id FROM bosses")
    bosses = cursor.fetchall()
    # Load all employees
    cursor.execute("SELECT id, name, boss_id FROM employees")
    employees = cursor.fetchall()
    conn.close()
    # Build a structure: {site_id: {boss_id: {boss_name, employees: [...]}}}
    site_bosses = {}
    for site_id, location in sites:
        site_bosses[site_id] = {}
    for boss_id, boss_name, site_id in bosses:
        if site_id in site_bosses:
            site_bosses[site_id][str(boss_id)] = {'name': boss_name, 'employees': []}
    for emp_id, emp_name, boss_id in employees:
        for site_id, bosses_dict in site_bosses.items():
            if str(boss_id) in bosses_dict:
                bosses_dict[str(boss_id)]['employees'].append({'id': emp_id, 'name': emp_name})
    return render_template("index.html", products=products, sites=sites, site_bosses=site_bosses)

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
    timestamp = session['pending_order']['timestamp'].replace(" ", "_").replace(":", "-")
    employee_id = session['pending_order']['employee_id']
    # Get boss_id for the employee, then site_id for the boss
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT boss_id FROM employees WHERE id = ?", (employee_id,))
    boss_result = cursor.fetchone()
    boss_id = boss_result[0] if boss_result else None
    site_id = "unknown"
    if boss_id:
        cursor.execute("SELECT site_id FROM bosses WHERE id = ?", (boss_id,))
        site_result = cursor.fetchone()
        site_id = site_result[0] if site_result else "unknown"
    conn.close()
    # Create unique filename
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{timestamp}_{site_id}_{employee_id}_{unique_id}.png"
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
    # Get boss_id and site_id for redirect
    employee_id = session['pending_order']['employee_id']
    cursor.execute("SELECT boss_id FROM employees WHERE id = ?", (employee_id,))
    boss_result = cursor.fetchone()
    boss_id = boss_result[0] if boss_result else None
    site_id = "unknown"
    if boss_id:
        cursor.execute("SELECT site_id FROM bosses WHERE id = ?", (boss_id,))
        site_result = cursor.fetchone()
        site_id = site_result[0] if site_result else "unknown"
    conn.close()
    # Clear the pending order from session
    session.pop('pending_order', None)
    # Redirect with site_id and boss_id as query params
    return redirect(f"/?site_id={site_id}&boss_id={boss_id}")

@app.route("/products")
def product_manager():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, image FROM products ORDER BY position ASC, id ASC")
    products = cursor.fetchall()
    conn.close()
    return render_template("products.html", products=products)

@app.route("/products/bulk_update", methods=["POST"])
def bulk_update_products():
 
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Get all product ids from the form
    ids = request.form.getlist('id')
    names = request.form.getlist('name')
    prices = request.form.getlist('price')
    positions = request.form.getlist('position')
    # For file uploads, use request.files.getlist for all images
    images = request.files.getlist('image')
    for idx, prod_id in enumerate(ids):
        name = names[idx]
        name = smart_capitalize(name)
        raw_price = prices[idx].strip()
        clean_price = re.sub(r'[^\d]', '', raw_price)
        try:
            price = int(clean_price)
        except ValueError:
            price = 0
        position = int(positions[idx]) if positions[idx].isdigit() else idx + 1
        image = images[idx] if idx < len(images) else None
        # Handle image upload or keep existing
        if image and image.filename:
            filename = secure_filename(image.filename)
            save_path = os.path.join(UPLOAD_FOLDER, filename)
            image.save(save_path)
            image_path = save_path
        else:
            c.execute("SELECT image FROM products WHERE id = ?", (prod_id,))
            current_image = c.fetchone()
            image_path = current_image[0] if current_image else ''
        c.execute("UPDATE products SET name = ?, price = ?, image = ?, position = ? WHERE id = ?", (name, price, image_path, position, prod_id))
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
    name = smart_capitalize(name)
    import re
    raw_price = request.form.get('price', '').strip()
    clean_price = re.sub(r'[^\d]', '', raw_price)
    try:
        price = int(clean_price)
    except ValueError:
        price = 0
    image = request.files.get("image")
    if image and image.filename:
        filename = secure_filename(image.filename)
        image_path = os.path.join(UPLOAD_FOLDER,filename)
        image.save(image_path)
    else:
        image_path = ""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Get the current max position
    cursor.execute("SELECT MAX(position) FROM products")
    max_position = cursor.fetchone()[0]
    if max_position is None:
        new_position = 1
    else:
        new_position = max_position + 1
    cursor.execute("INSERT INTO products (name, price, image, position) VALUES (?, ?, ?, ?)", (name, price, image_path, new_position))
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

def get_sites_bosses_employees():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, location FROM sites")
    sites = c.fetchall()
    c.execute("SELECT id, name, site_id FROM bosses")
    bosses = c.fetchall()
    c.execute("SELECT id, name, boss_id FROM employees")
    employees = c.fetchall()
    conn.close()
    return sites, bosses, employees

def build_site_bosses(sites, bosses, employees):
    site_bosses = {str(site_id): {} for site_id, _ in sites}
    for boss_id, boss_name, site_id in bosses:
        site_bosses[str(site_id)][str(boss_id)] = {'name': boss_name, 'employees': []}
    for emp_id, emp_name, boss_id in employees:
        for site_id, bosses_dict in site_bosses.items():
            if str(boss_id) in bosses_dict:
                bosses_dict[str(boss_id)]['employees'].append({'id': emp_id, 'name': emp_name})
    return site_bosses

def parse_orders_payments(c, selected_employee, emp_ids=None):
    orders, payments, grand_total = [], [], 0
    # Always return: (id, items, date, employee_id, order_total, signature)
    if selected_employee and selected_employee != 'all':
        c.execute("SELECT id, items, date, signature FROM orders WHERE employee_id = ? ORDER BY date DESC", (selected_employee,))
        raw_orders = c.fetchall()
        for order in raw_orders:
            order_total = parse_order_total(order[1])
            grand_total += order_total
            # order = (id, items, date, signature)
            orders.append((order[0], order[1], order[2], selected_employee, order_total, order[3]))
        c.execute("SELECT amount, date, note FROM payments WHERE employee_id = ? ORDER BY date DESC", (selected_employee,))
        payments = c.fetchall()
    elif emp_ids:
        qmarks = ','.join(['?']*len(emp_ids))
        c.execute(f"SELECT id, items, date, employee_id, signature FROM orders WHERE employee_id IN ({qmarks}) ORDER BY date DESC", emp_ids)
        raw_orders = c.fetchall()
        for order in raw_orders:
            order_total = parse_order_total(order[1])
            grand_total += order_total
            # order = (id, items, date, employee_id, signature)
            orders.append((order[0], order[1], order[2], order[3], order_total, order[4]))
        c.execute(f"SELECT employee_id, amount, date, note FROM payments WHERE employee_id IN ({qmarks}) ORDER BY date DESC", emp_ids)
        payments = c.fetchall()
    return orders, payments, grand_total

@app.route("/chart", methods=["GET", "POST"])
def chart():
    clear_paid_orders_for_all()
    error = None

    # Handle payment submission if admin and POST
    if request.method == "POST" and session.get("is_admin"):
        # ... (keep your payment logic here, or move to a helper)
        # Existing payment logic remains unchanged
        site_id = request.form.get("site_id")
        boss_id = request.form.get("boss_id") or request.values.get("boss_id")
        employee_id = request.form.get("employee_id")
        amount = request.form.get("amount")
        note = request.form.get("note")
        payment_key = request.form.get("payment_key")
        if payment_key and payment_key not in session.get('processed_payment_keys', []):
            if 'processed_payment_keys' not in session:
                session['processed_payment_keys'] = []
            session['processed_payment_keys'].append(payment_key)
            if employee_id == "all" and boss_id:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT id FROM employees WHERE boss_id = ?", (boss_id,))
                emp_ids = [row[0] for row in c.fetchall()]
                total_orders = 0
                for emp_id in emp_ids:
                    c.execute("SELECT items FROM orders WHERE employee_id = ?", (emp_id,))
                    orders = c.fetchall()
                    for order in orders:
                        total_orders += parse_order_total(order[0])
                # Subtract all payments for these employees
                total_payments = 0
                for emp_id in emp_ids:
                    c.execute("SELECT amount FROM payments WHERE employee_id = ?", (emp_id,))
                    payments = c.fetchall()
                    for payment in payments:
                        total_payments += payment[0]
                total_debt = total_orders - total_payments
                try:
                    amount_int = int(amount)
                except Exception:
                    amount_int = -1
                if amount_int != total_debt or total_debt == 0:
                    error = f"All Employees payment must match the total debt for this boss (currently {total_debt})."
                    flash(error, 'error')
                    conn.close()
                    return redirect(request.url)
                c.execute("SELECT id FROM employees WHERE boss_id = ? LIMIT 1", (boss_id,))
                first_emp = c.fetchone()
                if first_emp:
                    timestamp = datetime.today().strftime("%Y-%m-%d %H:%M")
                    all_note = f"ALL EMPLOYEES: {note}" if note else "ALL EMPLOYEES"
                    c.execute("INSERT INTO payments (employee_id, amount, date, note) VALUES (?, ?, ?, ?)", (first_emp[0], amount_int, timestamp, all_note))
                    for emp_id in emp_ids:
                        c.execute("SELECT id, items, date FROM orders WHERE employee_id = ?", (emp_id,))
                        orders = c.fetchall()
                        for order_id, items, date in orders:
                            order_total = parse_order_total(items)
                            c.execute("""INSERT INTO profit (employee_id, original_order_id, items, total_paid, date_cleared)
                                         VALUES (?, ?, ?, ?, DATE('now'))""", (emp_id, order_id, items, order_total))
                            c.execute("DELETE FROM orders WHERE id = ?", (order_id,))
                    for emp_id in emp_ids:
                        c.execute("DELETE FROM payments WHERE employee_id = ?", (emp_id,))
                    conn.commit()
                    conn.close()
            elif employee_id != "all":
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                timestamp = datetime.today().strftime("%Y-%m-%d %H:%M")
                c.execute("INSERT INTO payments (employee_id, amount, date, note) VALUES (?, ?, ?, ?)", (employee_id, amount, timestamp, note))
                conn.commit()
                conn.close()
            return redirect(request.url)

    # Fetch data
    sites, bosses, employees = get_sites_bosses_employees()
    site_bosses = build_site_bosses(sites, bosses, employees)

    # Filtering logic
    selected_site = request.values.get("site_id")
    boss_id_list = request.values.getlist("boss_id")
    selected_boss = boss_id_list[0] if boss_id_list else None
    selected_employee = request.values.get("employee_id") or "all"
    filtered_employees = []
    if selected_site and selected_boss and selected_boss in site_bosses[selected_site]:
        filtered_employees = site_bosses[selected_site][selected_boss]['employees']

    # Orders/payments filtering
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    emp_ids = None
    if selected_employee == 'all' and selected_boss and selected_site and selected_boss in site_bosses[selected_site]:
        emp_ids = [e['id'] for e in site_bosses[selected_site][selected_boss]['employees']]
    orders, payments, grand_total = parse_orders_payments(c, selected_employee, emp_ids)
    conn.close()

    # Build all_entries
    emp_names = {str(emp[0]): emp[1] for emp in employees}
    all_entries, order_total, payment_total = [], 0, 0
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
            'id': order[0],  # <-- Add this line for order id
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
        if len(payment) == 4:
            emp_id, amount, date, note = payment
            payment_id = None  # Default if not available
        elif len(payment) == 3:
            amount, date, note = payment
            emp_id = selected_employee
            payment_id = None
        else:
            continue
        is_all_employees = note and note.startswith("ALL EMPLOYEES")
        entry = {
            'type': 'payment',
            'employee_id': emp_id,
            'employee_name': "All" if is_all_employees else emp_names.get(str(emp_id), f'Employee #{emp_id}'),
            'date': date,
            'amount': amount,
            'note': note,
            'items': None,
            'parsed_items': []
        }
        # If payment id is available, add it
        if len(payment) == 4:
            entry['id'] = emp_id  # If you have a payment id, set it here. Otherwise, leave as is.
        all_entries.append(entry)
        payment_total += amount
    all_entries.sort(key=lambda x: x['date'], reverse=False)
    net_total = order_total - payment_total

    # Always generate a new payment_key for the form
    payment_key = str(uuid.uuid4())

    return render_template("chart.html", 
        sites=sites, 
        site_bosses=site_bosses,
        selected_site=selected_site,
        selected_boss=selected_boss,
        selected_employee=selected_employee,
        filtered_employees=filtered_employees,
        orders=orders,
        payments=payments,
        grand_total=grand_total,
        all_entries=all_entries,
        order_total=order_total,
        payment_total=payment_total,
        net_total=net_total,
        error=error,
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


@app.route("/manage")
def manage():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, location FROM sites")
    sites = cursor.fetchall()
    cursor.execute("SELECT id, name, site_id FROM bosses")
    bosses = cursor.fetchall()
    cursor.execute("SELECT id, name, boss_id, items FROM employees")
    employees = cursor.fetchall()
    # Build a structure: {site_id: {boss_id: {boss_name, employees: [...]}}}
    site_bosses = {}
    for site_id, location in sites:
        site_bosses[site_id] = {}
    for boss_id, boss_name, site_id in bosses:
        if site_id in site_bosses:
            site_bosses[site_id][str(boss_id)] = {'name': boss_name, 'employees': []}
    for emp_id, emp_name, boss_id, items in employees:
        # Calculate current owing
        cursor.execute("SELECT items FROM orders WHERE employee_id = ?", (emp_id,))
        orders = cursor.fetchall()
        order_total = sum(parse_order_total(order[0]) for order in orders)
        cursor.execute("SELECT amount FROM payments WHERE employee_id = ?", (emp_id,))
        payments = cursor.fetchall()
        payment_total = sum(payment[0] for payment in payments)
        current_owing = order_total - payment_total
        for site_id, bosses_dict in site_bosses.items():
            if str(boss_id) in bosses_dict:
                bosses_dict[str(boss_id)]['employees'].append({'id': emp_id, 'name': emp_name, 'current_owing': current_owing, 'items': items})
    conn.close()
    return render_template("manage.html", sites=sites, site_bosses=site_bosses)

@app.route("/update_site", methods=["POST"])
def update_site():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    site_id = request.form.get("site_id")
    location = request.form.get("location")
    
    # Collect all maestro inputs (all with name 'maestro')
    maestro_inputs = request.form.getlist("maestro")
    maestro_inputs = [m.strip() for m in maestro_inputs if m.strip()]
    maestro = ";".join(maestro_inputs)
    
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
        # Check for outstanding orders for any employee
        for emp in employees:
            emp_id = emp[0]
            cursor.execute("SELECT COUNT(*) FROM orders WHERE employee_id = ?", (emp_id,))
            if cursor.fetchone()[0] > 0:
                conn.close()
                flash("Cannot delete site: there are still outstanding orders (debts) for this site.", "error")
                return redirect("/manage")
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
    site_id = request.form.get("site_id")
    if not employee_id:
        return redirect("/manage")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Prevent delete if employee has current_owing > 0
    cursor.execute("SELECT current_owing FROM employees WHERE id = ?", (employee_id,))
    row = cursor.fetchone()
    if row and row[0] and int(row[0]) > 0:
        conn.close()
        flash("Cannot delete employee: employee still has outstanding owings.", "error")
        if site_id:
            return redirect(f"/manage?site_id={site_id}")
        return redirect("/manage")
    cursor.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
    conn.commit()
    conn.close()
    if site_id:
        return redirect(f"/manage?site_id={site_id}")
    return redirect("/manage")

@app.route("/add_boss", methods=["POST"])
def add_boss():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    site_id = request.form.get("site_id")
    boss_name = request.form.get("boss_name")
    if not site_id or not boss_name:
        return redirect("/manage")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO bosses (name, site_id) VALUES (?, ?)", (boss_name, site_id))
    conn.commit()
    conn.close()
    return redirect(f"/manage?site_id={site_id}")

@app.route("/update_boss", methods=["POST"])
def update_boss():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    boss_id = request.form.get("boss_id")
    boss_name = request.form.get("boss_name")
    site_id = request.form.get("site_id")
    if not boss_id or not boss_name:
        return redirect("/manage")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE bosses SET name = ? WHERE id = ?", (boss_name, boss_id))
    conn.commit()
    conn.close()
    if site_id:
        return redirect(f"/manage?site_id={site_id}")
    return redirect("/manage")

@app.route("/delete_boss", methods=["POST"])
def delete_boss():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    boss_id = request.form.get("boss_id")
    site_id = request.form.get("site_id")
    if not boss_id:
        return redirect("/manage")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Only allow delete if no employees for this boss
    cursor.execute("SELECT COUNT(*) FROM employees WHERE boss_id = ?", (boss_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        flash("Cannot delete boss: there are still employees assigned. Move or delete all employees first.", "error")
        if site_id:
            return redirect(f"/manage?site_id={site_id}")
        return redirect("/manage")
    cursor.execute("DELETE FROM bosses WHERE id = ?", (boss_id,))
    conn.commit()
    conn.close()
    if site_id:
        return redirect(f"/manage?site_id={site_id}")
    return redirect("/manage")

@app.route("/move_employee", methods=["POST"])
def move_employee():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    employee_id = request.form.get("employee_id")
    new_boss_id = request.form.get("new_boss_id")
    site_id = request.form.get("site_id")
    if not employee_id or not new_boss_id:
        return redirect("/manage")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE employees SET boss_id = ? WHERE id = ?", (new_boss_id, employee_id))
    conn.commit()
    conn.close()
    if site_id:
        return redirect(f"/manage?site_id={site_id}")
    return redirect("/manage")

@app.route("/add_employee", methods=["POST"])
def add_employee():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    boss_id = request.form.get("boss_id")
    employee_name = request.form.get("employee_name")
    employee_name = smart_capitalize(employee_name)
    site_id = request.form.get("site_id")
    if not boss_id or not employee_name:
        flash("Missing boss or employee name for new employee.", "error")
        if site_id:
            return redirect(f"/manage?site_id={site_id}")
        return redirect("/manage")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO employees (name, boss_id, current_owing, items) VALUES (?, ?, 0, '')", (employee_name, boss_id))
    conn.commit()
    conn.close()
    if site_id:
        return redirect(f"/manage?site_id={site_id}")
    return redirect("/manage")

@app.route("/update_bosses", methods=["POST"])
def update_bosses():
    site_id = request.form.get("site_id")
    boss_ids = request.form.getlist("boss_id")
    # Update or delete existing bosses
    for boss_id in boss_ids:
        if boss_id:  # Existing boss
            boss_name = request.form.get(f"boss_name_{boss_id}", "").strip()
            if boss_name == "":
                # Delete boss if name is empty
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM bosses WHERE id = ?", (boss_id,))
                # Optionally, handle employees under this boss (e.g., delete or reassign)
                c.execute("DELETE FROM employees WHERE boss_id = ?", (boss_id,))
                conn.commit()
                conn.close()
            else:
                # Update boss name
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE bosses SET name = ? WHERE id = ?", (boss_name, boss_id))
                conn.commit()
                conn.close()
    # Add new boss if provided
    new_boss_name = request.form.get("boss_name_new", "").strip()
    if new_boss_name:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO bosses (name, site_id) VALUES (?, ?)", (new_boss_name, site_id))
        conn.commit()
        conn.close()
    # Redirect back to manage page for the current site
    return redirect(url_for("manage", site_id=site_id))

def rand_str(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

@app.route("/add_site", methods=["POST"])
def add_site():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    
    location = request.form.get("location")
    
    # Collect all maestro inputs (all with name 'maestro')
    maestro_inputs = request.form.getlist("maestro")
    maestro_inputs = [m.strip() for m in maestro_inputs if m.strip()]
    maestro = ";".join(maestro_inputs)
    
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
    # Date range and pagination
    start = request.args.get("start")
    end = request.args.get("end")
    offset = int(request.args.get("offset", 0))
    limit = 50
    site_id = request.args.get("site_id")
    boss_id = request.args.get("boss_id")
    # Default date range: last 30 days
    if not start or not end:
        today = datetime.today().date()
        start = (today - timedelta(days=30)).isoformat()
        end = today.isoformat()
    # Get all sites and bosses for dropdowns
    c.execute("SELECT id, location FROM sites")
    sites = c.fetchall()
    c.execute("SELECT id, name, site_id FROM bosses")
    bosses = c.fetchall()
    # Get employees for filtering
    emp_ids = None
    if site_id:
        if boss_id:
            c.execute("SELECT id FROM employees WHERE boss_id = ?", (boss_id,))
            emp_ids = [row[0] for row in c.fetchall()]
        else:
            c.execute("SELECT id FROM employees WHERE boss_id IN (SELECT id FROM bosses WHERE site_id = ?)", (site_id,))
            emp_ids = [row[0] for row in c.fetchall()]
    # Query profits in date range, filtered by employees if needed
    if emp_ids is not None and emp_ids:
        qmarks = ','.join(['?']*len(emp_ids))
        c.execute(f"SELECT COUNT(*) FROM profit WHERE date_cleared BETWEEN ? AND ? AND employee_id IN ({qmarks})", (start, end, *emp_ids))
        length = c.fetchone()[0]
        c.execute(f"SELECT employee_id, original_order_id, items, total_paid, date_cleared FROM profit WHERE date_cleared BETWEEN ? AND ? AND employee_id IN ({qmarks}) ORDER BY date_cleared DESC LIMIT ? OFFSET ?", (start, end, *emp_ids, limit, offset))
        profits = c.fetchall()
    else:
        c.execute("SELECT COUNT(*) FROM profit WHERE date_cleared BETWEEN ? AND ?", (start, end))
        length = c.fetchone()[0]
        c.execute("SELECT employee_id, original_order_id, items, total_paid, date_cleared FROM profit WHERE date_cleared BETWEEN ? AND ? ORDER BY date_cleared DESC LIMIT ? OFFSET ?", (start, end, limit, offset))
        profits = c.fetchall()
    # Get employee names for display
    c.execute("SELECT id, name FROM employees")
    emp_names = {row[0]: row[1] for row in c.fetchall()}
    # Per-product stats
    summary = {}
    full_total = 0
    for emp_id, order_id, items, total_paid, date_cleared in profits:
        for item in items.split(","):
            item = item.strip()
            if ":" in item and ";" in item:
                try:
                    name_price, qty = item.split(";", 1)
                    name, price = name_price.split(":", 1)
                    name = name.strip()
                    price = int(price.strip())
                    qty = int(qty.strip())
                    if name not in summary:
                        summary[name] = {'qty': 0, 'total': 0}
                    summary[name]['qty'] += qty
                    summary[name]['total'] += price * qty
                    full_total += price * qty
                except Exception:
                    continue
    conn.close()
    return render_template("profit.html", profits=profits, emp_names=emp_names, start=start, end=end, offset=offset, length=length, summary=summary, full_total=full_total, sites=sites, bosses=bosses, selected_site=site_id, selected_boss=boss_id)

@app.route("/del_profit", methods=["POST"])
def del_profit():
    if not session.get("is_admin"):
        return "Unauthorized", 403
    profit_id = request.form.get("profit_id")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM profit WHERE original_order_id = ?", (profit_id,))
    conn.commit()
    conn.close()
    return redirect("/profit")

@app.route('/delete_owing', methods=['POST'])
def delete_owing():
    owing_id = request.form.get('owing_id')
    owing_type = request.form.get('owing_type')
    if not owing_id or not owing_type:
        flash('Missing owing information.', 'error')
        return redirect('/chart')
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        if owing_type == 'order':
            c.execute('DELETE FROM orders WHERE id = ?', (owing_id,))
        elif owing_type == 'payment':
            c.execute('DELETE FROM payments WHERE id = ?', (owing_id,))
        else:
            flash('Invalid owing type.', 'error')
            conn.close()
            return redirect('/chart')
        conn.commit()
        flash('Owing deleted.', 'success')
    except Exception as e:
        flash(f'Error deleting owing: {e}', 'error')
    finally:
        conn.close()
    return redirect('/chart')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port = 5000)

