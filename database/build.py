import os
import random
import sqlite3
from datetime import date, timedelta

SEED = 42

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.environ.get("DB_PATH", os.path.join(ROOT, "data.db"))
SCHEMA = os.path.join(HERE, "schema.sql")

# ---- generation sizes -------------------------------------------------------
N_SUPPLIERS = 25
N_PRODUCTS = 220
N_CUSTOMERS = 1500
N_ORDERS = 7000
N_PURCHASE_ORDERS = 400

TODAY = date(2024, 12, 31)
ORDER_START = date(2023, 1, 1)
ORDER_END = TODAY

# ---- coded values (unmarked in the schema — documented in docs/DATA_GUIDE.md) ----
# sales_orders.status
ST_PENDING, ST_SHIPPED, ST_DELIVERED, ST_RETURNED, ST_CANCELLED = 1, 2, 3, 4, 5
# purchase_orders.status
PO_OPEN, PO_RECEIVED, PO_CANCELLED = 1, 2, 3
# sales_orders.chan (sales channel)
CH_IN_STORE, CH_ONLINE, CH_PICKUP = 1, 2, 3


# ---- helpers ----------------------------------------------------------------
def iso(d: date) -> str:
    return d.isoformat()


def random_date(start: date, end: date) -> date:
    return start + timedelta(days=random.randint(0, max((end - start).days, 0)))


def money(x: float) -> float:
    return round(x, 2)


def weighted(options):
    values, weights = zip(*options)
    return random.choices(values, weights=weights, k=1)[0]


# ---- static reference data --------------------------------------------------
CATEGORIES = [
    (1, "Electronics", None), (2, "Home & Kitchen", None), (3, "Apparel", None),
    (4, "Grocery", None), (5, "Sports & Outdoors", None), (6, "Toys & Games", None),
    (7, "Health & Beauty", None), (8, "Computers", 1), (9, "Audio", 1),
    (10, "Cookware", 2), (11, "Furniture", 2), (12, "Men's Clothing", 3),
    (13, "Women's Clothing", 3), (14, "Snacks", 4),
]
LEAF_CATEGORIES = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
# category_id -> (cost_low, cost_high, margin_low, margin_high)
PRICE_BANDS = {
    5: (10, 300, 1.4, 1.9), 6: (5, 90, 1.5, 2.2), 7: (2, 60, 1.6, 2.5),
    8: (120, 1200, 1.15, 1.4), 9: (20, 400, 1.3, 1.7), 10: (15, 250, 1.4, 2.0),
    11: (60, 800, 1.3, 1.8), 12: (6, 80, 1.8, 3.0), 13: (6, 90, 1.8, 3.0),
    14: (0.5, 12, 1.3, 1.8),
}
NOUNS = {
    5: ["Yoga Mat", "Dumbbell Set", "Tent", "Water Bottle", "Running Shoes", "Bike Helmet", "Camping Stove"],
    6: ["Building Blocks", "Board Game", "Action Figure", "Puzzle", "RC Car", "Doll", "Card Game"],
    7: ["Shampoo", "Face Cream", "Vitamins", "Toothpaste", "Sunscreen", "Lip Balm", "Body Wash"],
    8: ["Laptop", "Desktop PC", "Monitor", "Keyboard", "Mouse", "Webcam", "External SSD"],
    9: ["Headphones", "Bluetooth Speaker", "Soundbar", "Earbuds", "Turntable", "Microphone"],
    10: ["Frying Pan", "Knife Set", "Saucepan", "Blender", "Toaster", "Mixing Bowl", "Kettle"],
    11: ["Office Chair", "Bookshelf", "Coffee Table", "Desk", "Dining Chair", "Nightstand"],
    12: ["T-Shirt", "Jeans", "Hoodie", "Jacket", "Socks", "Polo Shirt", "Shorts"],
    13: ["Blouse", "Dress", "Leggings", "Cardigan", "Skirt", "Scarf", "Tank Top"],
    14: ["Potato Chips", "Granola Bars", "Trail Mix", "Cookies", "Crackers", "Pretzels", "Popcorn"],
}
BRANDS = ["Acme", "Vertex", "Nimbus", "Summit", "Harbor", "Pioneer", "Cobalt",
          "Meadow", "Atlas", "Fable", "Nova", "Cedar"]
STORES = [
    ("Downtown Seattle", "Seattle", "WA"), ("Portland Pearl", "Portland", "OR"),
    ("SF Market Street", "San Francisco", "CA"), ("LA Sunset", "Los Angeles", "CA"),
    ("Denver LoDo", "Denver", "CO"), ("Austin Congress", "Austin", "TX"),
    ("Chicago Loop", "Chicago", "IL"), ("NYC SoHo", "New York", "NY"),
]
WAREHOUSES = [
    ("West DC", "Sacramento", "CA"), ("Central DC", "Dallas", "TX"), ("East DC", "Columbus", "OH"),
]
ROLE_WAGES = {
    "cashier": (15, 22), "sales_associate": (16, 26), "stock_clerk": (16, 24),
    "store_manager": (32, 55), "buyer": (34, 60), "regional_manager": (45, 80),
}
SELLING_ROLES = {"cashier", "sales_associate", "store_manager"}
SUPPLIER_COUNTRIES = ["USA", "USA", "USA", "China", "Vietnam", "Mexico", "Germany", "Canada", "South Korea"]
CUSTOMER_LOCS = [
    ("Seattle", "WA"), ("Portland", "OR"), ("San Francisco", "CA"), ("Los Angeles", "CA"),
    ("Denver", "CO"), ("Austin", "TX"), ("Chicago", "IL"), ("New York", "NY"),
    ("Boston", "MA"), ("Miami", "FL"), ("Phoenix", "AZ"), ("Atlanta", "GA"),
    ("Dallas", "TX"), ("Sacramento", "CA"), ("Columbus", "OH"), ("Nashville", "TN"),
]
FIRST_NAMES = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
               "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
               "Thomas", "Sarah", "Chris", "Karen", "Daniel", "Nancy", "Matthew", "Lisa",
               "Anthony", "Betty", "Mark", "Sandra", "Priya", "Wei", "Sofia", "Diego",
               "Aisha", "Kenji", "Olga", "Liam", "Emma", "Noah", "Ava", "Lucas"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
              "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
              "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
              "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Nguyen",
              "Kim", "Patel", "Chen", "Singh", "Ali", "Rossi", "Kowalski", "Okafor", "Silva"]


def build():
    random.seed(SEED)

    # -- categories -----------------------------------------------------------
    categories = [(cid, name, parent) for (cid, name, parent) in CATEGORIES]

    # -- suppliers ------------------------------------------------------------
    suppliers = []
    supplier_lead = {}
    for sid in range(1, N_SUPPLIERS + 1):
        name = f"{random.choice(BRANDS)} {random.choice(['Supply Co', 'Trading', 'Distributors', 'Imports', 'Wholesale', 'Group'])}"
        country = random.choice(SUPPLIER_COUNTRIES)
        lead = random.randint(3, 45)
        is_active = weighted([(1, 9), (0, 1)])
        suppliers.append((sid, name, f"orders@supplier{sid}.example.com", country, lead, is_active))
        supplier_lead[sid] = lead

    # -- products -------------------------------------------------------------
    products = []
    product_supplier, product_price, product_cost = {}, {}, {}
    for pid in range(1, N_PRODUCTS + 1):
        cat = random.choice(LEAF_CATEGORIES)
        sup = random.randint(1, N_SUPPLIERS)
        c_lo, c_hi, m_lo, m_hi = PRICE_BANDS[cat]
        cost = money(random.uniform(c_lo, c_hi))
        price = money(cost * random.uniform(m_lo, m_hi))
        is_active = weighted([(1, 12), (0, 1)])
        created = random_date(date(2020, 1, 1), date(2023, 6, 30))
        products.append((pid, f"SKU-{pid:05d}", f"{random.choice(BRANDS)} {random.choice(NOUNS[cat])}",
                         cat, sup, cost, price, is_active, iso(created)))
        product_supplier[pid] = sup
        product_price[pid] = price
        product_cost[pid] = cost
    active_products = [p[0] for p in products if p[7] == 1]
    products_by_supplier = {}
    for pid, sup in product_supplier.items():
        products_by_supplier.setdefault(sup, []).append(pid)

    # -- stores ---------------------------------------------------------------
    stores = []
    store_opened = {}
    for i, (name, city, st) in enumerate(STORES, start=1):
        opened = random_date(date(2014, 1, 1), date(2021, 6, 30))
        stores.append((i, name, city, st, "USA", iso(opened), random.randint(8000, 45000)))
        store_opened[i] = opened

    # -- warehouses -----------------------------------------------------------
    warehouses = []
    for i, (name, city, st) in enumerate(WAREHOUSES, start=1):
        warehouses.append((i, name, city, st, "USA", random.randint(50000, 200000)))

    # -- employees ------------------------------------------------------------
    employees = []
    store_selling_emps = {i: [] for i in range(1, len(STORES) + 1)}
    emp_id = 0

    def make_emp(store_id, role, hire_from, hire_to):
        nonlocal emp_id
        emp_id += 1
        hire = random_date(hire_from, hire_to)
        lo, hi = ROLE_WAGES[role]
        is_active = weighted([(1, 6), (0, 1)])
        employees.append((emp_id, random.choice(FIRST_NAMES), random.choice(LAST_NAMES),
                          store_id, role, iso(hire), money(random.uniform(lo, hi)), is_active))
        if store_id is not None and role in SELLING_ROLES:
            store_selling_emps[store_id].append((emp_id, hire))

    for sid in range(1, len(STORES) + 1):
        opened = store_opened[sid]
        make_emp(sid, "store_manager", opened, opened + timedelta(days=30))
        for _ in range(random.randint(8, 13)):
            role = weighted([("cashier", 4), ("sales_associate", 3), ("stock_clerk", 2)])
            make_emp(sid, role, opened, TODAY - timedelta(days=30))
    for _ in range(6):
        role = weighted([("buyer", 3), ("regional_manager", 2)])
        make_emp(None, role, date(2014, 1, 1), date(2020, 12, 31))

    # -- customers (tier filled in after orders) ------------------------------
    customers_raw = []  # (id, first, last, email, city, state, signup_date_obj)
    for cid in range(1, N_CUSTOMERS + 1):
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        city, st = random.choice(CUSTOMER_LOCS)
        signup = random_date(date(2018, 1, 1), TODAY)
        customers_raw.append((cid, first, last, f"{first.lower()}.{last.lower()}{cid}@example.com", city, st, signup))
    customers_by_signup = sorted(customers_raw, key=lambda c: c[6])

    # -- inventory ------------------------------------------------------------
    inventory = []
    inv_id = 0
    for sid in range(1, len(STORES) + 1):
        for pid in range(1, N_PRODUCTS + 1):
            if random.random() > 0.85:
                continue
            inv_id += 1
            qoh = random.randint(0, 10) if random.random() < 0.15 else random.randint(20, 400)
            rop = random.randint(10, 40)                 # reorder point
            reorder_qty = random.randint(60, 200)
            restocked = random_date(TODAY - timedelta(days=150), TODAY)
            inventory.append((inv_id, sid, pid, qoh, rop, reorder_qty, iso(restocked)))

    # -- sales orders + items -------------------------------------------------
    sales_orders = []
    order_items = []
    customer_spend = {c[0]: 0.0 for c in customers_raw}
    oi_id = 0
    for oid in range(1, N_ORDERS + 1):
        sid = random.randint(1, len(STORES))
        order_dt = random_date(max(ORDER_START, store_opened[sid]), ORDER_END)

        eligible = [e for (e, h) in store_selling_emps[sid] if h <= order_dt]
        employee_id = random.choice(eligible)

        customer_id = None
        if random.random() < 0.65:
            pool = [c for c in customers_by_signup if c[6] <= order_dt]
            if pool:
                customer_id = random.choice(pool)[0]

        n_items = weighted([(1, 5), (2, 6), (3, 5), (4, 3), (5, 2), (6, 1)])
        chosen = random.sample(active_products, min(n_items, len(active_products)))
        subtotal, pending_items = 0.0, []
        for pid in chosen:
            qty = weighted([(1, 6), (2, 4), (3, 2), (4, 1), (5, 1)])
            price = product_price[pid]
            line = money(qty * price)
            subtotal += line
            pending_items.append((pid, qty, price, line))
        subtotal = money(subtotal)

        discount = money(subtotal * random.uniform(0.05, 0.20)) if random.random() < 0.30 else 0.0
        total = money(subtotal - discount)

        # Recent orders are still in flight; older orders have settled.
        days_ago = (TODAY - order_dt).days
        if days_ago <= 21:
            status = weighted([(ST_PENDING, 4), (ST_SHIPPED, 5), (ST_DELIVERED, 3),
                               (ST_RETURNED, 1), (ST_CANCELLED, 1)])
        else:
            status = weighted([(ST_DELIVERED, 86), (ST_RETURNED, 8), (ST_CANCELLED, 6)])

        chan = weighted([(CH_IN_STORE, 70), (CH_ONLINE, 22), (CH_PICKUP, 8)])
        payment = weighted([("credit_card", 45), ("debit_card", 25), ("cash", 20), ("gift_card", 10)])

        sales_orders.append((oid, sid, customer_id, employee_id, iso(order_dt),
                             status, chan, payment, subtotal, discount, total))
        for (pid, qty, price, line) in pending_items:
            oi_id += 1
            order_items.append((oi_id, oid, pid, qty, price, line))

        # lifetime spend for loyalty tier: delivered orders by known customers
        if customer_id is not None and status == ST_DELIVERED:
            customer_spend[customer_id] += total

    # -- derive loyalty tier from lifetime delivered spend --------------------
    def tier_for(spend: float) -> str:
        if spend >= 5000:
            return "platinum"
        if spend >= 2000:
            return "gold"
        if spend >= 500:
            return "silver"
        return "none"

    # -- internal segmentation code (customers.seg) --------------------------
    # 1 standard retail, 2 small business, 3 employee, 9 internal/test seed.
    # No data signal distinguishes these — meaning lives only in the guide.
    cust_seg = {c[0]: weighted([(1, 78), (2, 12), (3, 7), (9, 3)]) for c in customers_raw}
    # A test account is the single highest-spending "customer" in the data.
    top_spender = max(customer_spend, key=lambda cid: customer_spend[cid])
    cust_seg[top_spender] = 9

    customers = [(cid, first, last, email, city, st, iso(signup), tier_for(customer_spend[cid]), cust_seg[cid])
                 for (cid, first, last, email, city, st, signup) in customers_raw]

    # -- purchase orders + items ---------------------------------------------
    purchase_orders = []
    po_items = []
    poi_id = 0
    for po_id in range(1, N_PURCHASE_ORDERS + 1):
        supplier_id = random.choice([s for s in products_by_supplier if products_by_supplier[s]])
        warehouse_id = random.randint(1, len(WAREHOUSES))
        order_dt = random_date(ORDER_START, ORDER_END)
        expected = order_dt + timedelta(days=supplier_lead[supplier_id])

        if expected > TODAY:
            status = PO_OPEN
        else:
            status = weighted([(PO_RECEIVED, 9), (PO_CANCELLED, 1)])

        if status == PO_RECEIVED:
            received = min(expected + timedelta(days=random.randint(-3, 7)), TODAY)
            received_str = iso(received)
        else:
            received_str = None

        sup_products = products_by_supplier[supplier_id]
        n_lines = random.randint(2, min(8, len(sup_products)))
        line_products = random.sample(sup_products, n_lines)
        total_cost, pending_lines = 0.0, []
        for pid in line_products:
            qty_ordered = random.randint(20, 500)
            unit_cost = money(product_cost[pid] * random.uniform(0.95, 1.05))
            qty_received = qty_ordered if status == PO_RECEIVED else 0
            total_cost += qty_ordered * unit_cost
            pending_lines.append((pid, qty_ordered, qty_received, unit_cost))
        total_cost = money(total_cost)

        purchase_orders.append((po_id, supplier_id, warehouse_id, iso(order_dt),
                               iso(expected), received_str, status, total_cost))
        for (pid, qo, qr, uc) in pending_lines:
            poi_id += 1
            po_items.append((poi_id, po_id, pid, qo, qr, uc))

    # -- write ----------------------------------------------------------------
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA) as f:
        conn.executescript(f.read())

    conn.executemany("INSERT INTO categories VALUES (?,?,?)", categories)
    conn.executemany("INSERT INTO suppliers VALUES (?,?,?,?,?,?)", suppliers)
    conn.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)", products)
    conn.executemany("INSERT INTO stores VALUES (?,?,?,?,?,?,?)", stores)
    conn.executemany("INSERT INTO warehouses VALUES (?,?,?,?,?,?)", warehouses)
    conn.executemany("INSERT INTO employees VALUES (?,?,?,?,?,?,?,?)", employees)
    conn.executemany("INSERT INTO inventory VALUES (?,?,?,?,?,?,?)", inventory)
    conn.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?)", customers)
    conn.executemany("INSERT INTO sales_orders VALUES (?,?,?,?,?,?,?,?,?,?,?)", sales_orders)
    conn.executemany("INSERT INTO sales_order_items VALUES (?,?,?,?,?,?)", order_items)
    conn.executemany("INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?,?)", purchase_orders)
    conn.executemany("INSERT INTO purchase_order_items VALUES (?,?,?,?,?,?)", po_items)
    conn.commit()

    conn.close()


if __name__ == "__main__":
    build()
