CREATE TABLE product_categories (
    category_id        INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    parent_category_id INTEGER REFERENCES product_categories(category_id)
);

CREATE TABLE products (
    product_id    INTEGER PRIMARY KEY,
    sku           TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    category_id   INTEGER NOT NULL REFERENCES product_categories(category_id),
    unit_price    REAL NOT NULL,
    weight_kg     REAL NOT NULL,
    is_active     INTEGER NOT NULL,
    launched_date TEXT NOT NULL
);

CREATE TABLE product_attributes (
    attribute_id INTEGER PRIMARY KEY,
    product_id   INTEGER NOT NULL REFERENCES products(product_id),
    attr_name    TEXT NOT NULL,
    attr_value   TEXT NOT NULL
);

CREATE TABLE price_history (
    price_history_id INTEGER PRIMARY KEY,
    product_id       INTEGER NOT NULL REFERENCES products(product_id),
    effective_date   TEXT NOT NULL,
    unit_price       REAL NOT NULL
);

CREATE TABLE customers (
    customer_id  INTEGER PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    email        TEXT,
    phone        TEXT,
    segment_code INTEGER NOT NULL,
    signup_date  TEXT NOT NULL,
    is_active    INTEGER NOT NULL
);

CREATE TABLE customer_addresses (
    address_id        INTEGER PRIMARY KEY,
    customer_id       INTEGER NOT NULL REFERENCES customers(customer_id),
    address_type_code INTEGER NOT NULL,
    line1             TEXT NOT NULL,
    city              TEXT NOT NULL,
    state             TEXT NOT NULL,
    postal_code       TEXT NOT NULL,
    country           TEXT NOT NULL,
    is_default        INTEGER NOT NULL
);

CREATE TABLE orders (
    order_id           INTEGER PRIMARY KEY,
    customer_id        INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date         TEXT NOT NULL,
    status             INTEGER NOT NULL,
    priority_code      INTEGER NOT NULL,
    channel_code       INTEGER NOT NULL,
    ship_to_address_id INTEGER REFERENCES customer_addresses(address_id),
    promised_date      TEXT,
    order_total        REAL NOT NULL
);

CREATE TABLE order_lines (
    order_line_id   INTEGER PRIMARY KEY,
    order_id        INTEGER NOT NULL REFERENCES orders(order_id),
    sku             TEXT NOT NULL,
    quantity        INTEGER NOT NULL,
    unit_price      REAL NOT NULL,
    discount_amount REAL NOT NULL,
    line_total      REAL NOT NULL
);

CREATE TABLE order_status_history (
    history_id INTEGER PRIMARY KEY,
    order_id   INTEGER NOT NULL REFERENCES orders(order_id),
    status     INTEGER NOT NULL,
    changed_ts TEXT NOT NULL,
    note       TEXT
);

CREATE TABLE payments (
    payment_id  INTEGER PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(order_id),
    method_code INTEGER NOT NULL,
    status_code INTEGER NOT NULL,
    amount      REAL NOT NULL,
    paid_date   TEXT
);

CREATE TABLE promotions (
    promotion_id    INTEGER PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    promo_type_code INTEGER NOT NULL,
    value           REAL NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL
);

CREATE TABLE order_promotions (
    order_promotion_id INTEGER PRIMARY KEY,
    order_id           INTEGER NOT NULL REFERENCES orders(order_id),
    promotion_id       INTEGER NOT NULL REFERENCES promotions(promotion_id),
    discount_amount    REAL NOT NULL
);

CREATE TABLE gift_cards (
    gift_card_id    INTEGER PRIMARY KEY,
    code            TEXT NOT NULL UNIQUE,
    initial_balance REAL NOT NULL,
    current_balance REAL NOT NULL,
    status_code     INTEGER NOT NULL,
    issued_date     TEXT NOT NULL,
    customer_id     INTEGER REFERENCES customers(customer_id)
);

CREATE TABLE gift_card_transactions (
    gc_txn_id     INTEGER PRIMARY KEY,
    gift_card_id  INTEGER NOT NULL REFERENCES gift_cards(gift_card_id),
    order_id      INTEGER REFERENCES orders(order_id),
    txn_type_code INTEGER NOT NULL,
    amount        REAL NOT NULL,
    txn_ts        TEXT NOT NULL
);

CREATE TABLE carriers (
    carrier_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    scac       TEXT NOT NULL,
    country    TEXT NOT NULL,
    is_active  INTEGER NOT NULL
);

CREATE TABLE carrier_services (
    service_id         INTEGER PRIMARY KEY,
    carrier_id         INTEGER NOT NULL REFERENCES carriers(carrier_id),
    service_level_code INTEGER NOT NULL,
    name               TEXT NOT NULL,
    transit_days_est   INTEGER NOT NULL
);

CREATE TABLE facilities (
    facility_id        INTEGER PRIMARY KEY,
    code               TEXT NOT NULL UNIQUE,
    name               TEXT NOT NULL,
    facility_type_code INTEGER NOT NULL,
    city               TEXT NOT NULL,
    state              TEXT NOT NULL,
    country            TEXT NOT NULL
);

CREATE TABLE warehouses (
    warehouse_id   INTEGER PRIMARY KEY,
    code           TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL,
    city           TEXT NOT NULL,
    state          TEXT NOT NULL,
    country        TEXT NOT NULL,
    capacity_units INTEGER NOT NULL,
    is_active      INTEGER NOT NULL
);

CREATE TABLE warehouse_zones (
    zone_id        INTEGER PRIMARY KEY,
    warehouse_id   INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    zone_code      TEXT NOT NULL,
    zone_type_code INTEGER NOT NULL,
    capacity_units INTEGER NOT NULL
);

CREATE TABLE bins (
    bin_id         INTEGER PRIMARY KEY,
    warehouse_id   INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    zone_id        INTEGER NOT NULL REFERENCES warehouse_zones(zone_id),
    bin_code       TEXT NOT NULL,
    capacity_units INTEGER NOT NULL
);

CREATE TABLE shipments (
    shipment_id         INTEGER PRIMARY KEY,
    order_id            INTEGER NOT NULL REFERENCES orders(order_id),
    carrier_id          INTEGER NOT NULL REFERENCES carriers(carrier_id),
    service_id          INTEGER NOT NULL REFERENCES carrier_services(service_id),
    origin_warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    status              INTEGER NOT NULL,
    ship_date           TEXT NOT NULL,
    delivered_date      TEXT,
    promised_date       TEXT,
    tracking_number     TEXT NOT NULL,
    weight_kg           REAL NOT NULL
);

CREATE TABLE packages (
    package_id          INTEGER PRIMARY KEY,
    shipment_id         INTEGER NOT NULL REFERENCES shipments(shipment_id),
    packaging_type_code INTEGER NOT NULL,
    weight_kg           REAL NOT NULL,
    length_cm           REAL NOT NULL,
    width_cm            REAL NOT NULL,
    height_cm           REAL NOT NULL
);

CREATE TABLE shipment_items (
    shipment_item_id INTEGER PRIMARY KEY,
    shipment_id      INTEGER NOT NULL REFERENCES shipments(shipment_id),
    package_id       INTEGER NOT NULL REFERENCES packages(package_id),
    order_line_id    INTEGER NOT NULL REFERENCES order_lines(order_line_id),
    sku              TEXT NOT NULL,
    quantity         INTEGER NOT NULL
);

CREATE TABLE shipment_legs (
    leg_id          INTEGER PRIMARY KEY,
    shipment_id     INTEGER NOT NULL REFERENCES shipments(shipment_id),
    leg_seq         INTEGER NOT NULL,
    mode_code       INTEGER NOT NULL,
    from_facility_id INTEGER NOT NULL REFERENCES facilities(facility_id),
    to_facility_id  INTEGER NOT NULL REFERENCES facilities(facility_id),
    status          INTEGER NOT NULL,
    departed_ts     TEXT NOT NULL,
    arrived_ts      TEXT
);

CREATE TABLE tracking_events (
    event_id    INTEGER PRIMARY KEY,
    shipment_id INTEGER NOT NULL REFERENCES shipments(shipment_id),
    event_code  INTEGER NOT NULL,
    event_ts    TEXT NOT NULL,
    facility_id INTEGER REFERENCES facilities(facility_id),
    message     TEXT NOT NULL
);

CREATE TABLE delivery_exceptions (
    exception_id        INTEGER PRIMARY KEY,
    shipment_id         INTEGER NOT NULL REFERENCES shipments(shipment_id),
    exception_type_code INTEGER NOT NULL,
    reported_ts         TEXT NOT NULL,
    resolved_ts         TEXT,
    note                TEXT
);

CREATE TABLE pick_tasks (
    pick_id      INTEGER PRIMARY KEY,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    order_id     INTEGER NOT NULL REFERENCES orders(order_id),
    status_code  INTEGER NOT NULL,
    created_ts   TEXT NOT NULL,
    completed_ts TEXT
);

CREATE TABLE pick_lines (
    pick_line_id INTEGER PRIMARY KEY,
    pick_id      INTEGER NOT NULL REFERENCES pick_tasks(pick_id),
    item_code    INTEGER NOT NULL,
    bin_id       INTEGER REFERENCES bins(bin_id),
    quantity     INTEGER NOT NULL
);

CREATE TABLE returns (
    return_id        INTEGER PRIMARY KEY,
    order_id         INTEGER NOT NULL REFERENCES orders(order_id),
    rma_number       TEXT NOT NULL UNIQUE,
    reason_code      INTEGER NOT NULL,
    status           INTEGER NOT NULL,
    disposition_code INTEGER,
    requested_date   TEXT NOT NULL,
    received_date    TEXT
);

CREATE TABLE return_lines (
    return_line_id INTEGER PRIMARY KEY,
    return_id      INTEGER NOT NULL REFERENCES returns(return_id),
    sku            TEXT NOT NULL,
    quantity       INTEGER NOT NULL,
    condition_code INTEGER
);

CREATE TABLE carrier_invoices (
    carrier_invoice_id INTEGER PRIMARY KEY,
    carrier_id         INTEGER NOT NULL REFERENCES carriers(carrier_id),
    invoice_number     TEXT NOT NULL UNIQUE,
    amount             REAL NOT NULL,
    status_code        INTEGER NOT NULL,
    invoice_date       TEXT NOT NULL,
    due_date           TEXT NOT NULL,
    paid_date          TEXT
);

CREATE TABLE route_lanes (
    lane_id               INTEGER PRIMARY KEY,
    origin_facility_id    INTEGER NOT NULL REFERENCES facilities(facility_id),
    dest_facility_id      INTEGER NOT NULL REFERENCES facilities(facility_id),
    mode_code             INTEGER NOT NULL,
    distance_km           REAL NOT NULL,
    standard_transit_days INTEGER NOT NULL
);

CREATE TABLE suppliers (
    supplier_id            INTEGER PRIMARY KEY,
    name                   TEXT NOT NULL,
    country                TEXT NOT NULL,
    status_code            INTEGER NOT NULL,
    default_lead_time_days INTEGER NOT NULL
);

CREATE TABLE supplier_products (
    supplier_product_id INTEGER PRIMARY KEY,
    supplier_id         INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    item_code           INTEGER NOT NULL,
    supplier_sku        TEXT NOT NULL,
    unit_cost           REAL NOT NULL,
    lead_time_days      INTEGER NOT NULL,
    is_preferred        INTEGER NOT NULL
);

CREATE TABLE supplier_contacts (
    contact_id  INTEGER PRIMARY KEY,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    name        TEXT NOT NULL,
    email       TEXT,
    phone       TEXT,
    role        TEXT NOT NULL
);

CREATE TABLE inventory (
    inventory_id       INTEGER PRIMARY KEY,
    warehouse_id       INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    item_code          INTEGER NOT NULL,
    quantity_on_hand   INTEGER NOT NULL,
    quantity_allocated INTEGER NOT NULL,
    reorder_point      INTEGER NOT NULL,
    reorder_qty        INTEGER NOT NULL,
    last_counted_date  TEXT NOT NULL,
    UNIQUE (warehouse_id, item_code)
);

CREATE TABLE inventory_lots (
    lot_id        INTEGER PRIMARY KEY,
    warehouse_id  INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    item_code     INTEGER NOT NULL,
    lot_number    TEXT NOT NULL,
    quantity      INTEGER NOT NULL,
    received_date TEXT NOT NULL,
    expiry_date   TEXT
);

CREATE TABLE inventory_transactions (
    txn_id         INTEGER PRIMARY KEY,
    warehouse_id   INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    item_code      INTEGER NOT NULL,
    txn_type_code  INTEGER NOT NULL,
    quantity_delta INTEGER NOT NULL,
    reference_type TEXT NOT NULL,
    reference_id   INTEGER,
    txn_ts         TEXT NOT NULL
);

CREATE TABLE replenishment_orders (
    repl_id       INTEGER PRIMARY KEY,
    supplier_id   INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    warehouse_id  INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    status        INTEGER NOT NULL,
    order_date    TEXT NOT NULL,
    expected_date TEXT NOT NULL,
    received_date TEXT,
    total_cost    REAL NOT NULL
);

CREATE TABLE replenishment_lines (
    repl_line_id INTEGER PRIMARY KEY,
    repl_id      INTEGER NOT NULL REFERENCES replenishment_orders(repl_id),
    item_code    INTEGER NOT NULL,
    qty_ordered  INTEGER NOT NULL,
    qty_received INTEGER NOT NULL,
    unit_cost    REAL NOT NULL
);

CREATE TABLE receipts (
    receipt_id   INTEGER PRIMARY KEY,
    repl_id      INTEGER NOT NULL REFERENCES replenishment_orders(repl_id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    received_ts  TEXT NOT NULL,
    reference    TEXT NOT NULL
);

CREATE TABLE receipt_lines (
    receipt_line_id INTEGER PRIMARY KEY,
    receipt_id      INTEGER NOT NULL REFERENCES receipts(receipt_id),
    item_code       INTEGER NOT NULL,
    qty_received    INTEGER NOT NULL,
    condition_code  INTEGER NOT NULL
);

CREATE TABLE supplier_invoices (
    supplier_invoice_id INTEGER PRIMARY KEY,
    supplier_id         INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    repl_id             INTEGER REFERENCES replenishment_orders(repl_id),
    invoice_number      TEXT NOT NULL UNIQUE,
    amount              REAL NOT NULL,
    status_code         INTEGER NOT NULL,
    invoice_date        TEXT NOT NULL,
    due_date            TEXT NOT NULL,
    paid_date           TEXT
);

CREATE TABLE stock_transfers (
    transfer_id       INTEGER PRIMARY KEY,
    from_warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    to_warehouse_id   INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    status_code       INTEGER NOT NULL,
    created_date      TEXT NOT NULL,
    shipped_date      TEXT,
    received_date     TEXT
);

CREATE TABLE stock_transfer_lines (
    transfer_line_id INTEGER PRIMARY KEY,
    transfer_id      INTEGER NOT NULL REFERENCES stock_transfers(transfer_id),
    item_code        INTEGER NOT NULL,
    qty_requested    INTEGER NOT NULL,
    qty_shipped      INTEGER NOT NULL,
    qty_received     INTEGER NOT NULL
);

CREATE TABLE inventory_adjustments (
    adjustment_id   INTEGER PRIMARY KEY,
    warehouse_id    INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    item_code       INTEGER NOT NULL,
    adjustment_date TEXT NOT NULL,
    quantity_delta  INTEGER NOT NULL,
    reason_code     INTEGER NOT NULL
);

CREATE TABLE cycle_counts (
    count_id     INTEGER PRIMARY KEY,
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(warehouse_id),
    item_code    INTEGER NOT NULL,
    bin_id       INTEGER REFERENCES bins(bin_id),
    system_qty   INTEGER NOT NULL,
    counted_qty  INTEGER NOT NULL,
    variance     INTEGER NOT NULL,
    count_date   TEXT NOT NULL,
    status_code  INTEGER NOT NULL
);
