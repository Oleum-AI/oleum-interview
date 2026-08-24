CREATE TABLE categories (
    category_id        INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    parent_category_id INTEGER REFERENCES categories(category_id)
);

CREATE TABLE suppliers (
    supplier_id    INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    email          TEXT,
    country        TEXT NOT NULL,
    lead_time_days INTEGER NOT NULL,
    is_active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE products (
    product_id  INTEGER PRIMARY KEY,
    sku         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(category_id),
    supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    wac         REAL NOT NULL,
    unit_price  REAL NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);

CREATE TABLE stores (
    store_id    INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    city        TEXT NOT NULL,
    state       TEXT NOT NULL,
    country     TEXT NOT NULL,
    opened_date TEXT NOT NULL,
    gla         INTEGER NOT NULL
);

CREATE TABLE warehouses (
    warehouse_id   INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    city           TEXT NOT NULL,
    state          TEXT NOT NULL,
    country        TEXT NOT NULL,
    cap            INTEGER NOT NULL
);

CREATE TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    first_name  TEXT NOT NULL,
    last_name   TEXT NOT NULL,
    store_id    INTEGER REFERENCES stores(store_id),
    role        TEXT NOT NULL,
    hire_date   TEXT NOT NULL,
    hourly_wage REAL NOT NULL,
    is_active   INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE inventory (
    inventory_id        INTEGER PRIMARY KEY,
    store_id            INTEGER NOT NULL REFERENCES stores(store_id),
    product_id          INTEGER NOT NULL REFERENCES products(product_id),
    quantity_on_hand    INTEGER NOT NULL,
    rop                 INTEGER NOT NULL,
    roq                 INTEGER NOT NULL,
    last_restocked_date TEXT NOT NULL,
    UNIQUE (store_id, product_id)
);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    email        TEXT,
    city         TEXT NOT NULL,
    state        TEXT NOT NULL,
    signup_date  TEXT NOT NULL,
    loyalty_tier TEXT NOT NULL,
    seg          INTEGER NOT NULL
);

CREATE TABLE sales_orders (
    order_id        INTEGER PRIMARY KEY,
    store_id        INTEGER NOT NULL REFERENCES stores(store_id),
    customer_id     INTEGER REFERENCES customers(customer_id),
    employee_id     INTEGER NOT NULL REFERENCES employees(employee_id),
    order_date      TEXT NOT NULL,
    status          INTEGER NOT NULL,
    chan            INTEGER NOT NULL,
    payment_method  TEXT NOT NULL,
    subtotal        REAL NOT NULL,
    discount_amount REAL NOT NULL,
    total_amount    REAL NOT NULL
);

CREATE TABLE sales_order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES sales_orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    quantity      INTEGER NOT NULL,
    unit_price    REAL NOT NULL,
    line_total    REAL NOT NULL
);

CREATE TABLE purchase_orders (
    po_id         INTEGER PRIMARY KEY,
    supplier_id   INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    warehouse_id  INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    order_date    TEXT NOT NULL,
    expected_date TEXT NOT NULL,
    received_date TEXT,
    status        INTEGER NOT NULL,
    total_cost    REAL NOT NULL
);

CREATE TABLE purchase_order_items (
    po_item_id        INTEGER PRIMARY KEY,
    po_id             INTEGER NOT NULL REFERENCES purchase_orders(po_id),
    product_id        INTEGER NOT NULL REFERENCES products(product_id),
    quantity_ordered  INTEGER NOT NULL,
    quantity_received INTEGER NOT NULL,
    unit_cost         REAL NOT NULL
);
