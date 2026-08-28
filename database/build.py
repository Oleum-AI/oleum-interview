"""Data generator.

Builds a mid-size 3PL / omnichannel logistics database (46 tables, 3 domains)
into data.db. Deterministic (seed 42). Coded columns are unmarked in the schema;
their meaning lives in the guidance docs. See interviewer/SPEC.md for the
canonical spec and interviewer/GOTCHAS.md for the planted traps.
"""
import os
import random
import sqlite3
from datetime import date, timedelta

SEED = 42

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DB_PATH = os.environ.get("DB_PATH", os.path.join(ROOT, "data.db"))
SCHEMA = os.path.join(HERE, "schema.sql")

TODAY = date(2024, 12, 31)
ORDER_START = date(2023, 1, 1)

# ---- generation sizes -------------------------------------------------------
N_PRODUCTS = 600
N_CUSTOMERS = 3000
N_ORDERS = 20000
N_SUPPLIERS = 40
N_WAREHOUSES = 8
N_PROMOTIONS = 30
N_GIFT_CARDS = 500
N_REPLENISHMENTS = 1500
N_TRANSFERS = 800
N_ADJUSTMENTS = 3000
N_CYCLE_COUNTS = 3000

TEST_ORDER_RATE = 0.03          # G3: priority_code == 7
BELOW_ROP_RATE = 0.18           # inventory rows below reorder point
LATE_NOISE_HI = 4               # delivered-late spread (~25% late vs promised)
SPLIT_SHIP_RATE = 0.12          # fraction of multi-line shipped orders split across shipments
MULTIPAY_RATE = 0.12            # fraction of non-draft orders with a failed attempt before capture
MULTI_RECEIPT_RATE = 0.5        # fraction of multi-line received/partial POs delivered over >1 receipt
GC_PARTIAL_ACTIVE_RATE = 0.4    # fraction of active gift cards partially spent (balance < initial)


# ---- helpers ----------------------------------------------------------------
def iso(d):
    return d.isoformat()


def ts(d, h=None, m=None):
    h = random.randint(6, 20) if h is None else h
    m = random.randint(0, 59) if m is None else m
    return f"{d.isoformat()}T{h:02d}:{m:02d}:00"


def random_date(start, end):
    span = max((end - start).days, 0)
    return start + timedelta(days=random.randint(0, span))


def money(x):
    return round(x, 2)


def weighted(options):
    values, weights = zip(*options)
    return random.choices(values, weights=weights, k=1)[0]


def sku_of(pid):
    return f"SKU-{pid:05d}"


# ---- reference pools (continuity with Part 1) -------------------------------
CATEGORIES = [
    (1, "Electronics", None), (2, "Home & Kitchen", None), (3, "Apparel", None),
    (4, "Grocery", None), (5, "Sports & Outdoors", None), (6, "Toys & Games", None),
    (7, "Health & Beauty", None), (8, "Computers", 1), (9, "Audio", 1),
    (10, "Cookware", 2), (11, "Furniture", 2), (12, "Men's Clothing", 3),
    (13, "Women's Clothing", 3), (14, "Snacks", 4),
]
LEAF_CATEGORIES = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
PRICE_BANDS = {
    5: (10, 300, 1.4, 1.9), 6: (5, 90, 1.5, 2.2), 7: (2, 60, 1.6, 2.5),
    8: (120, 1200, 1.15, 1.4), 9: (20, 400, 1.3, 1.7), 10: (15, 250, 1.4, 2.0),
    11: (60, 800, 1.3, 1.8), 12: (6, 80, 1.8, 3.0), 13: (6, 90, 1.8, 3.0),
    14: (0.5, 12, 1.3, 1.8),
}
WEIGHT_BANDS = {
    5: (0.2, 6.0), 6: (0.1, 3.0), 7: (0.05, 1.5), 8: (0.3, 12.0), 9: (0.1, 8.0),
    10: (0.2, 5.0), 11: (2.0, 40.0), 12: (0.1, 1.2), 13: (0.1, 1.2), 14: (0.05, 1.0),
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
LOCS = [
    ("Seattle", "WA"), ("Portland", "OR"), ("San Francisco", "CA"), ("Los Angeles", "CA"),
    ("Denver", "CO"), ("Austin", "TX"), ("Chicago", "IL"), ("New York", "NY"),
    ("Boston", "MA"), ("Miami", "FL"), ("Phoenix", "AZ"), ("Atlanta", "GA"),
    ("Dallas", "TX"), ("Sacramento", "CA"), ("Columbus", "OH"), ("Nashville", "TN"),
]
STREETS = ["Main St", "Oak Ave", "Pine St", "Maple Dr", "Cedar Ln", "Elm St", "Market St",
           "Broadway", "1st Ave", "Sunset Blvd", "Lake Rd", "Hill St"]
SUPPLIER_COUNTRIES = ["USA", "USA", "USA", "China", "Vietnam", "Mexico", "Germany", "Canada", "South Korea"]
WAREHOUSE_SITES = [
    ("WDC", "West DC", "Sacramento", "CA"), ("CDC", "Central DC", "Dallas", "TX"),
    ("EDC", "East DC", "Columbus", "OH"), ("PNW", "Northwest DC", "Seattle", "WA"),
    ("SEA", "Southeast DC", "Atlanta", "GA"), ("NE", "Northeast DC", "Boston", "MA"),
    ("SW", "Southwest DC", "Phoenix", "AZ"), ("MW", "Midwest DC", "Chicago", "IL"),
]
CARRIER_DEFS = [
    ("Atlas Freight", "ATLF", "USA"), ("Nimbus Express", "NMBX", "USA"),
    ("Harbor Logistics", "HRBL", "USA"), ("Summit Parcel", "SMTP", "USA"),
    ("Pioneer Shipping", "PNRS", "USA"), ("Cobalt Cargo", "CBLC", "USA"),
    ("Meadow Transport", "MDWT", "Canada"), ("Cedar Line", "CDRL", "USA"),
    ("Vertex Air", "VRTA", "USA"), ("Nova Ocean", "NVOC", "USA"),
]
SERVICE_DEFS = [
    (1, "Ground", 5), (2, "2-Day", 2), (3, "Overnight", 1), (4, "Economy", 8), (5, "Freight", 10),
]
FACILITY_SITES = [
    ("origin_dc", 1), ("hub", 2), ("cross_dock", 3), ("last_mile_depot", 4), ("port", 5),
]


def build():
    random.seed(SEED)
    rows = {}   # table -> list of tuples

    # -- product categories ---------------------------------------------------
    categories = [(cid, name, parent) for (cid, name, parent) in CATEGORIES]
    rows["product_categories"] = categories

    # -- products -------------------------------------------------------------
    products = []
    product_price = {}
    product_weight = {}
    product_cat = {}
    active_products = []
    for pid in range(1, N_PRODUCTS + 1):
        cat = random.choice(LEAF_CATEGORIES)
        c_lo, c_hi, m_lo, m_hi = PRICE_BANDS[cat]
        cost = random.uniform(c_lo, c_hi)
        price = money(cost * random.uniform(m_lo, m_hi))
        w_lo, w_hi = WEIGHT_BANDS[cat]
        weight = round(random.uniform(w_lo, w_hi), 2)
        is_active = weighted([(1, 12), (0, 1)])
        launched = random_date(date(2019, 1, 1), date(2024, 6, 30))
        products.append((pid, sku_of(pid), f"{random.choice(BRANDS)} {random.choice(NOUNS[cat])}",
                         cat, price, weight, is_active, iso(launched)))
        product_price[pid] = price
        product_weight[pid] = weight
        product_cat[pid] = cat
        if is_active:
            active_products.append(pid)
    rows["products"] = products

    # -- product attributes ---------------------------------------------------
    COLORS = ["Black", "White", "Silver", "Blue", "Red", "Green", "Gray"]
    attrs = []
    aid = 0
    for pid in range(1, N_PRODUCTS + 1):
        for name, val in [("color", random.choice(COLORS)),
                          ("warranty_months", str(random.choice([0, 6, 12, 24, 36]))),
                          ("country_of_origin", random.choice(SUPPLIER_COUNTRIES))]:
            aid += 1
            attrs.append((aid, pid, name, val))
    rows["product_attributes"] = attrs

    # -- price history --------------------------------------------------------
    price_hist = []
    phid = 0
    for pid in range(1, N_PRODUCTS + 1):
        n = random.randint(1, 4)
        base = product_price[pid]
        d0 = date(2022, 1, 1)
        for i in range(n):
            phid += 1
            eff = random_date(d0, TODAY)
            p = money(base * random.uniform(0.85, 1.15)) if i > 0 else base
            price_hist.append((phid, pid, iso(eff), p))
    rows["price_history"] = price_hist

    # -- customers ------------------------------------------------------------
    customers = []
    for cid in range(1, N_CUSTOMERS + 1):
        first, last = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
        seg = weighted([(1, 70), (2, 16), (3, 10), (4, 4)])
        signup = random_date(date(2018, 1, 1), TODAY)
        is_active = weighted([(1, 9), (0, 1)])
        phone = f"({random.randint(200, 989)}) {random.randint(200, 989)}-{random.randint(1000, 9999)}"
        customers.append((cid, first, last, f"{first.lower()}.{last.lower()}{cid}@example.com",
                          phone, seg, iso(signup), is_active))
    rows["customers"] = customers

    # -- customer addresses ---------------------------------------------------
    addresses = []
    cust_addr = {}   # customer_id -> list of address_id
    adid = 0
    for cid in range(1, N_CUSTOMERS + 1):
        n = random.randint(1, 2)
        cust_addr[cid] = []
        for i in range(n):
            adid += 1
            city, st = random.choice(LOCS)
            atype = weighted([(1, 3), (2, 5), (3, 2)])
            addresses.append((adid, cid, atype, f"{random.randint(10, 9999)} {random.choice(STREETS)}",
                              city, st, f"{random.randint(10000, 99999)}", "USA", 1 if i == 0 else 0))
            cust_addr[cid].append(adid)
    rows["customer_addresses"] = addresses

    # -- promotions -----------------------------------------------------------
    promotions = []
    for pmid in range(1, N_PROMOTIONS + 1):
        ptype = weighted([(1, 5), (2, 4), (3, 2), (4, 3)])
        if ptype == 1:
            val = random.choice([5, 10, 15, 20, 25])
        elif ptype == 2:
            val = random.choice([5, 10, 20, 50])
        else:
            val = 0
        start = random_date(ORDER_START, date(2024, 6, 30))
        end = start + timedelta(days=random.randint(14, 120))
        promotions.append((pmid, f"PROMO{pmid:03d}", f"Campaign {pmid}", ptype, float(val),
                           iso(start), iso(end)))
    rows["promotions"] = promotions

    # -- warehouses -----------------------------------------------------------
    warehouses = []
    for i, (code, name, city, st) in enumerate(WAREHOUSE_SITES[:N_WAREHOUSES], start=1):
        warehouses.append((i, code, name, city, st, "USA", random.randint(50000, 250000),
                           weighted([(1, 15), (0, 1)])))
    rows["warehouses"] = warehouses
    warehouse_ids = [w[0] for w in warehouses]
    active_warehouses = [w[0] for w in warehouses if w[7] == 1] or warehouse_ids

    # -- warehouse zones ------------------------------------------------------
    zones = []
    wh_zones = {w: [] for w in warehouse_ids}
    zid = 0
    for w in warehouse_ids:
        for zt in [1, 2, 2, 3, 4]:   # receiving, storage x2, picking, shipping
            zid += 1
            zones.append((zid, w, f"Z{zt}-{zid}", zt, random.randint(5000, 40000)))
            wh_zones[w].append((zid, zt))
    rows["warehouse_zones"] = zones

    # -- bins -----------------------------------------------------------------
    bins = []
    wh_bins = {w: [] for w in warehouse_ids}
    bid = 0
    for w in warehouse_ids:
        for (zone_id, zt) in wh_zones[w]:
            for _ in range(random.randint(8, 14)):
                bid += 1
                bins.append((bid, w, zone_id, f"B{bid:05d}", random.randint(50, 500)))
                wh_bins[w].append(bid)
    rows["bins"] = bins

    # -- facilities -----------------------------------------------------------
    facilities = []
    fid = 0
    for (city, st) in LOCS:
        ftype = weighted([(1, 2), (2, 3), (3, 2), (4, 4), (5, 1)])
        fid += 1
        facilities.append((fid, f"FAC{fid:03d}", f"{city} {FACILITY_SITES[ftype - 1][0]}", ftype, city, st, "USA"))
    rows["facilities"] = facilities
    facility_ids = [f[0] for f in facilities]

    # -- route lanes ----------------------------------------------------------
    lanes = []
    lid = 0
    for _ in range(60):
        a, b = random.sample(facility_ids, 2)
        lid += 1
        mode = weighted([(1, 5), (2, 1), (3, 2), (4, 1), (5, 3)])
        lanes.append((lid, a, b, mode, round(random.uniform(50, 4000), 1), random.randint(1, 12)))
    rows["route_lanes"] = lanes

    # -- carriers + services --------------------------------------------------
    carriers = []
    for i, (name, scac, country) in enumerate(CARRIER_DEFS, start=1):
        carriers.append((i, name, scac, country, weighted([(1, 9), (0, 1)])))
    rows["carriers"] = carriers
    carrier_ids = [c[0] for c in carriers]

    services = []
    carrier_services = {c: [] for c in carrier_ids}
    sid = 0
    for c in carrier_ids:
        for (lvl, sname, transit) in SERVICE_DEFS:
            if random.random() < 0.75 or lvl == 1:
                sid += 1
                services.append((sid, c, lvl, f"{sname}", transit))
                carrier_services[c].append((sid, lvl, transit))
    rows["carrier_services"] = services

    # -- carrier invoices (freight billing, one per carrier per month) --------
    carrier_invoices = []
    cinv_id = 0
    for c in carrier_ids:
        m = date(2023, 1, 1)
        while m <= TODAY:
            cinv_id += 1
            amount = money(random.uniform(2000, 45000))
            istatus = weighted([(4, 6), (3, 2), (2, 1), (5, 1)])
            due = m + timedelta(days=30)
            paid = iso(min(due + timedelta(days=random.randint(-10, 20)), TODAY)) if istatus == 4 else None
            carrier_invoices.append((cinv_id, c, f"CINV{cinv_id:07d}", amount, istatus,
                                     iso(m), iso(due), paid))
            m = date(m.year + (m.month // 12), (m.month % 12) + 1, 1)
    rows["carrier_invoices"] = carrier_invoices

    # -- suppliers + contacts + supplier_products -----------------------------
    suppliers = []
    for sid_ in range(1, N_SUPPLIERS + 1):
        country = random.choice(SUPPLIER_COUNTRIES)
        status = weighted([(1, 80), (2, 8), (3, 5), (4, 7)])
        suppliers.append((sid_, f"{random.choice(BRANDS)} {random.choice(['Supply Co', 'Trading', 'Distributors', 'Imports', 'Wholesale', 'Group'])}",
                          country, status, random.randint(3, 45)))
    rows["suppliers"] = suppliers
    supplier_ids = [s[0] for s in suppliers]

    contacts = []
    ctid = 0
    for s in supplier_ids:
        for role in random.sample(["account_manager", "logistics", "billing", "sales"], random.randint(1, 3)):
            ctid += 1
            fn, ln = random.choice(FIRST_NAMES), random.choice(LAST_NAMES)
            contacts.append((ctid, s, f"{fn} {ln}", f"{fn.lower()}@supplier{s}.example.com",
                             f"({random.randint(200, 989)}) {random.randint(200, 989)}-{random.randint(1000, 9999)}", role))
    rows["supplier_contacts"] = contacts

    supplier_products = []
    product_cost = {}
    spid = 0
    for pid in range(1, N_PRODUCTS + 1):
        base_cost = product_price[pid] / random.uniform(1.2, 2.0)
        product_cost[pid] = money(base_cost)
        n_sup = random.randint(1, 3)
        chosen = random.sample(supplier_ids, n_sup)
        for i, s in enumerate(chosen):
            spid += 1
            cost = money(base_cost * random.uniform(0.9, 1.1))
            supplier_products.append((spid, s, pid, f"S{s}-{pid:05d}", cost,
                                      random.randint(3, 45), 1 if i == 0 else 0))
    rows["supplier_products"] = supplier_products

    # -- gift cards -----------------------------------------------------------
    # Balances follow GIFTCARD_STATUS: active(1) is live (some partially spent);
    # redeemed(2) is fully spent down to zero; expired(3)/void(4) are non-spendable
    # zero-balance terminals. The transaction ledger is built after orders exist so
    # that each redeem can be tied to the order it paid for (order_id populated).
    gift_cards = []
    gc_redeem_specs = []   # (gift_card_id, issued_date, redeemed_amount) for cards that were spent
    for gcid in range(1, N_GIFT_CARDS + 1):
        init = float(random.choice([25, 50, 75, 100, 150, 200]))
        status = weighted([(1, 6), (2, 3), (3, 1), (4, 1)])
        if status == 1:
            bal = money(init * random.uniform(0.3, 0.9)) if random.random() < GC_PARTIAL_ACTIVE_RATE else init
        else:
            bal = 0.0   # redeemed(2)=fully spent, expired(3)/void(4)=zero
        issued = random_date(date(2022, 1, 1), TODAY)
        owner = random.randint(1, N_CUSTOMERS) if random.random() < 0.7 else None
        gift_cards.append((gcid, f"GC{gcid:06d}", init, bal, status, iso(issued), owner))
        # A redeem records spend: active cards below their initial balance, and
        # every fully-spent redeemed(2) card. Expired/void lapsed without spend.
        if status == 2 or (status == 1 and bal < init):
            gc_redeem_specs.append((gcid, issued, money(init - bal)))
    rows["gift_cards"] = gift_cards

    # -- orders + lines + status history + payments + order_promotions --------
    orders = []            # list of dict (mutable promised_date)
    order_lines = []
    order_status_history = []
    payments = []
    order_promotions = []
    olid = 0
    hid = 0
    pmt_id = 0
    opid = 0

    # status: 1 draft,2 placed,3 confirmed,4 fulfilled,5 cancelled,6 returned
    STATUS_W = [(1, 2), (2, 5), (3, 8), (4, 70), (5, 8), (6, 7)]

    for oid in range(1, N_ORDERS + 1):
        cid = random.randint(1, N_CUSTOMERS)
        order_dt = random_date(ORDER_START, TODAY)
        status = weighted(STATUS_W)
        # G3: internal/test orders, no distinguishing signal
        if random.random() < TEST_ORDER_RATE:
            priority = 7
        else:
            priority = weighted([(1, 70), (2, 22), (3, 8)])
        channel = weighted([(1, 40), (2, 25), (3, 8), (4, 20), (5, 7)])
        ship_addr = random.choice(cust_addr[cid]) if cust_addr[cid] else None

        n_items = weighted([(1, 5), (2, 6), (3, 5), (4, 3), (5, 2)])
        chosen = random.sample(active_products, min(n_items, len(active_products)))
        total = 0.0
        line_ids_for_order = []
        for pid in chosen:
            olid += 1
            qty = weighted([(1, 6), (2, 4), (3, 2), (4, 1)])
            price = product_price[pid]
            disc = money(qty * price * random.uniform(0.05, 0.2)) if random.random() < 0.25 else 0.0
            line_total = money(qty * price - disc)
            total += line_total
            order_lines.append((olid, oid, sku_of(pid), qty, price, disc, line_total))
            line_ids_for_order.append((olid, pid, qty))
        total = money(total)

        promised = iso(order_dt + timedelta(days=random.randint(3, 12))) if status not in (1,) else None

        orders.append({"order_id": oid, "customer_id": cid, "order_date": order_dt,
                       "status": status, "priority": priority, "channel": channel,
                       "ship_addr": ship_addr, "promised": promised, "total": total,
                       "lines": line_ids_for_order})

        # status history: draft->...->current
        seq = [1]
        for s in (2, 3, 4, 5, 6):
            if s <= status and s != 1:
                seq.append(s)
        if status == 5:      # cancelled: draft/placed then cancelled
            seq = [1, 2, 5]
        if status == 6:      # returned: went through fulfilled
            seq = [1, 2, 3, 4, 6]
        cur = order_dt
        for s in seq:
            hid += 1
            order_status_history.append((hid, oid, s, ts(cur), None))
            cur = min(cur + timedelta(days=random.randint(0, 4)), TODAY)

        # payment (non-draft). An order can carry more than one payment row: some
        # orders see a failed attempt before the real one settles. Every row's
        # amount equals the order total (no split tender), so summing by order
        # over the captured/refunded statuses still recovers order revenue.
        if status != 1:
            method = weighted([(1, 45), (2, 22), (3, 15), (4, 8), (5, 6), (6, 4)])
            if random.random() < MULTIPAY_RATE:
                pmt_id += 1
                payments.append((pmt_id, oid, method, 5, total, None))   # failed attempt, no funds moved
            pmt_id += 1
            if status == 5:
                pstat, paid = weighted([(4, 6), (1, 2), (5, 2)]), None
            elif status == 6:
                pstat, paid = 3, iso(order_dt + timedelta(days=random.randint(1, 5)))   # refunded
            else:
                pstat, paid = weighted([(2, 9), (1, 1)]), iso(order_dt + timedelta(days=random.randint(0, 3)))
            payments.append((pmt_id, oid, method, pstat, total, paid))

        # promotion applied
        if random.random() < 0.3 and total > 0:
            opid += 1
            order_promotions.append((opid, oid, random.randint(1, N_PROMOTIONS),
                                     money(total * random.uniform(0.05, 0.15))))

    rows["orders"] = _order_tuples(orders)
    rows["order_lines"] = order_lines
    rows["order_status_history"] = order_status_history
    rows["payments"] = payments
    rows["order_promotions"] = order_promotions

    # -- gift card transactions (ledger) --------------------------------------
    # Issue rows have no order; redeem rows are applied to a real order, so
    # gift_card_transactions.order_id is populated on redemptions and NULL on issues.
    nondraft_oids = [o["order_id"] for o in orders if o["status"] != 1]
    gc_txns = []
    gtid = 0
    gc_redeem_lookup = {gcid: (issued, amt) for (gcid, issued, amt) in gc_redeem_specs}
    for (gcid, code, init, bal, status, issued_iso, owner) in gift_cards:
        gtid += 1
        issued_dt = date.fromisoformat(issued_iso)
        gc_txns.append((gtid, gcid, None, 1, init, ts(issued_dt)))   # issue: no order
        if gcid in gc_redeem_lookup:
            _issued, amt = gc_redeem_lookup[gcid]
            gtid += 1
            oid_link = random.choice(nondraft_oids)
            gc_txns.append((gtid, gcid, oid_link, 2, amt, ts(random_date(issued_dt, TODAY))))
    rows["gift_card_transactions"] = gc_txns

    # -- shipments and everything hanging off them ----------------------------
    shipments = []
    packages = []
    shipment_items = []
    shipment_legs = []
    tracking_events = []
    delivery_exceptions = []
    pick_tasks = []
    pick_lines = []
    ship_id = 0
    pkg_id = 0
    si_id = 0
    leg_id = 0
    ev_id = 0
    exc_id = 0
    pick_id = 0
    pl_id = 0
    order_ship_wh = {}   # order_id -> origin warehouse of its first shipment (for restock postings)

    for o in orders:
        if o["status"] not in (3, 4, 6):
            continue

        # Split shipments: a 3PL can fulfil one order in several shipments (e.g. a
        # backordered line follows later, or lines ship from two warehouses). We
        # split by line so every order line still ships complete in exactly one
        # shipment. Single-line orders never split.
        lines = o["lines"]
        if len(lines) >= 2 and random.random() < SPLIT_SHIP_RATE:
            cut = random.randint(1, len(lines) - 1)
            line_groups = [lines[:cut], lines[cut:]]
        else:
            line_groups = [lines]

        for grp_idx, grp_lines in enumerate(line_groups):
            ship_id += 1
            wh = random.choice(active_warehouses)
            carrier = random.choice(carrier_ids)
            svc_id, svc_lvl, transit_est = random.choice(carrier_services[carrier])
            ship_dt = min(o["order_date"] + timedelta(days=random.randint(0, 2)), TODAY)
            promised_dt = ship_dt + timedelta(days=transit_est + random.randint(1, 3))
            if grp_idx == 0:
                o["promised"] = iso(promised_dt)
                order_ship_wh[o["order_id"]] = wh
            weight = round(sum(product_weight[pid] * qty for (_, pid, qty) in grp_lines), 2)
            tracking = f"1Z{carrier:02d}{ship_id:08d}"

            if o["status"] in (4, 6):
                ship_status = weighted([(5, 92), (6, 6), (7, 2)])
                if ship_status == 5:
                    actual = max(1, transit_est + random.randint(-3, LATE_NOISE_HI))
                    delivered_dt = ship_dt + timedelta(days=actual)
                    delivered = iso(min(delivered_dt, TODAY))
                elif ship_status == 6:
                    delivered_dt = ship_dt + timedelta(days=transit_est + random.randint(2, 10))
                    delivered = iso(min(delivered_dt, TODAY))
                    ship_status = 5   # exception then delivered
                else:
                    delivered = None   # lost
            else:  # confirmed / in transit
                ship_status = weighted([(2, 2), (3, 6), (4, 2)])
                delivered = None

            shipments.append((ship_id, o["order_id"], carrier, svc_id, wh, ship_status,
                              iso(ship_dt), delivered, iso(promised_dt), tracking, weight))

            # packages (1-2) + shipment_items mapped from this shipment's lines
            n_pkg = 1 if len(grp_lines) <= 2 else random.randint(1, 2)
            pkg_ids = []
            for _ in range(n_pkg):
                pkg_id += 1
                ptype = weighted([(1, 6), (2, 2), (3, 1), (5, 1)])
                pw = round(weight / n_pkg, 2)
                packages.append((pkg_id, ship_id, ptype, pw,
                                 round(random.uniform(10, 80), 1), round(random.uniform(10, 60), 1),
                                 round(random.uniform(5, 50), 1)))
                pkg_ids.append(pkg_id)
            for (line_id, pid, qty) in grp_lines:
                si_id += 1
                shipment_items.append((si_id, ship_id, random.choice(pkg_ids), line_id, sku_of(pid), qty))

            # legs (1-3)
            n_legs = random.randint(1, 3)
            cur_ts = ship_dt
            for seq in range(1, n_legs + 1):
                leg_id += 1
                a, b = random.sample(facility_ids, 2)
                mode = weighted([(1, 6), (5, 3), (3, 1)])
                leg_status = 3 if (delivered or seq < n_legs) else weighted([(2, 2), (3, 1)])
                dep = ts(cur_ts)
                cur_ts = min(cur_ts + timedelta(days=random.randint(1, 4)), TODAY)
                arr = ts(cur_ts) if leg_status == 3 else None
                shipment_legs.append((leg_id, ship_id, seq, mode, a, b, leg_status, dep, arr))

            # tracking events
            ev_id += 1
            tracking_events.append((ev_id, ship_id, 1, ts(ship_dt), random.choice(facility_ids), "Label created"))
            for _ in range(random.randint(1, 3)):
                ev_id += 1
                tracking_events.append((ev_id, ship_id, weighted([(2, 3), (3, 3), (4, 1)]),
                                        ts(random_date(ship_dt, min(ship_dt + timedelta(days=transit_est + 5), TODAY))),
                                        random.choice(facility_ids), "In transit"))
            if delivered:
                ev_id += 1
                tracking_events.append((ev_id, ship_id, 5, ts(date.fromisoformat(delivered)),
                                        random.choice(facility_ids), "Delivered"))

            # delivery exception (~8%)
            if random.random() < 0.08:
                exc_id += 1
                etype = weighted([(1, 3), (2, 3), (3, 2), (4, 3), (5, 2), (6, 1)])
                rep = ts(random_date(ship_dt, min(ship_dt + timedelta(days=transit_est + 3), TODAY)))
                resolved = ts(min(ship_dt + timedelta(days=transit_est + random.randint(4, 8)), TODAY)) if random.random() < 0.7 else None
                delivery_exceptions.append((exc_id, ship_id, etype, rep, resolved, None))

            # pick task + lines at this shipment's origin warehouse (one pick per shipment)
            pick_id += 1
            pstatus = 4 if o["status"] in (4, 6) else weighted([(3, 2), (4, 3), (5, 1)])
            created = ts(o["order_date"])
            completed = ts(ship_dt) if pstatus == 4 else None
            pick_tasks.append((pick_id, wh, o["order_id"], pstatus, created, completed))
            for (line_id, pid, qty) in grp_lines:
                pl_id += 1
                bin_id = random.choice(wh_bins[wh]) if wh_bins[wh] else None
                pick_lines.append((pl_id, pick_id, pid, bin_id, qty))

    rows["shipments"] = shipments
    rows["packages"] = packages
    rows["shipment_items"] = shipment_items
    rows["shipment_legs"] = shipment_legs
    rows["tracking_events"] = tracking_events
    rows["delivery_exceptions"] = delivery_exceptions
    rows["pick_tasks"] = pick_tasks
    rows["pick_lines"] = pick_lines

    # -- returns (from returned/fulfilled orders) -----------------------------
    returns = []
    return_lines = []
    ret_id = 0
    rl_id = 0
    for o in orders:
        make = (o["status"] == 6) or (o["status"] == 4 and random.random() < 0.04)
        if not make:
            continue
        ret_id += 1
        reason = weighted([(1, 3), (2, 2), (3, 4), (4, 2), (5, 1)])
        rstatus = weighted([(3, 4), (4, 4), (1, 1), (2, 1), (5, 1)])
        disposition = weighted([(1, 5), (2, 2), (3, 2), (4, 1)]) if rstatus in (3, 4) else None
        req = o["order_date"] + timedelta(days=random.randint(5, 40))
        req = min(req, TODAY)
        received = iso(min(req + timedelta(days=random.randint(2, 10)), TODAY)) if rstatus in (3, 4) else None
        returns.append((ret_id, o["order_id"], f"RMA{ret_id:07d}", reason, rstatus, disposition,
                        iso(req), received))
        for (line_id, pid, qty) in random.sample(o["lines"], random.randint(1, len(o["lines"]))):
            rl_id += 1
            cond = weighted([(1, 3), (2, 4), (3, 2), (4, 2)]) if rstatus in (3, 4) else None
            return_lines.append((rl_id, ret_id, sku_of(pid), random.randint(1, qty), cond))
    rows["returns"] = returns
    rows["return_lines"] = return_lines

    # -- inventory ------------------------------------------------------------
    inventory = []
    inv_id = 0
    inv_index = {}   # (wh,item) -> inventory_id
    for w in warehouse_ids:
        stocked = random.sample(range(1, N_PRODUCTS + 1), random.randint(380, 520))
        for pid in stocked:
            inv_id += 1
            rop = random.randint(10, 50)
            roq = random.randint(50, 200)
            if random.random() < BELOW_ROP_RATE:
                qoh = random.randint(0, max(0, rop - 1))
            else:
                qoh = random.randint(rop, 400)
            alloc = random.randint(0, max(0, qoh // 3))
            counted = random_date(TODAY - timedelta(days=120), TODAY)
            inventory.append((inv_id, w, pid, qoh, alloc, rop, roq, iso(counted)))
            inv_index[(w, pid)] = inv_id
    rows["inventory"] = inventory

    # -- inventory lots -------------------------------------------------------
    lots = []
    lot_id = 0
    for (inv_id_, w, pid, qoh, alloc, rop, roq, counted) in inventory:
        for _ in range(random.randint(1, 2)):
            if qoh <= 0:
                break
            lot_id += 1
            q = random.randint(1, max(1, qoh))
            recv = random_date(TODAY - timedelta(days=200), TODAY)
            exp = iso(recv + timedelta(days=random.randint(180, 720))) if product_cat[pid] in (14, 7) else None
            lots.append((lot_id, w, pid, f"LOT{lot_id:07d}", q, iso(recv), exp))
    rows["inventory_lots"] = lots

    # -- replenishment orders + lines + receipts + receipt_lines + invoices ---
    repl_orders = []
    repl_lines = []
    receipts = []
    receipt_lines = []
    supplier_invoices = []
    rl2_id = 0
    rcpt_id = 0
    rcl_id = 0
    inv_num = 0
    for repl in range(1, N_REPLENISHMENTS + 1):
        supplier = random.choice(supplier_ids)
        wh = random.choice(warehouse_ids)
        order_dt = random_date(ORDER_START, TODAY)
        lead = random.randint(3, 45)
        expected = order_dt + timedelta(days=lead)
        if expected > TODAY:
            status = weighted([(2, 6), (1, 2), (3, 2)])   # open/draft/partial
        else:
            status = weighted([(4, 8), (5, 1), (3, 1)])   # received/cancelled/partial
        received = iso(min(expected + timedelta(days=random.randint(-3, 7)), TODAY)) if status == 4 else None

        line_pids = random.sample(range(1, N_PRODUCTS + 1), random.randint(2, 8))
        total_cost = 0.0
        this_lines = []
        for pid in line_pids:
            rl2_id += 1
            qo = random.randint(20, 500)
            uc = money(product_cost.get(pid, product_price[pid] * 0.6) * random.uniform(0.95, 1.05))
            qr = qo if status == 4 else (random.randint(0, qo) if status == 3 else 0)
            total_cost += qo * uc
            repl_lines.append((rl2_id, repl, pid, qo, qr, uc))
            this_lines.append((pid, qr, uc))
        total_cost = money(total_cost)
        repl_orders.append((repl, supplier, wh, status, iso(order_dt), iso(expected), received, total_cost))

        # Receipts: goods physically arrive against received (4) and partial (3)
        # POs. A PO can be delivered over more than one receipt (a supplier ships
        # the ordered SKUs in two drops), so we split the received lines across
        # 1-2 receipts. Only lines that actually received stock appear.
        if status in (3, 4):
            receivable = [(pid, qr, uc) for (pid, qr, uc) in this_lines if qr > 0]
            if receivable:
                if status == 4:
                    rbase = date.fromisoformat(received)
                else:   # partial PO: no header received_date, but stock did arrive
                    rbase = random_date(order_dt, TODAY)
                if len(receivable) >= 2 and random.random() < MULTI_RECEIPT_RATE:
                    cut = random.randint(1, len(receivable) - 1)
                    rcpt_groups = [receivable[:cut], receivable[cut:]]
                else:
                    rcpt_groups = [receivable]
                for grp_idx, grp in enumerate(rcpt_groups):
                    rcpt_id += 1
                    r_dt = rbase if grp_idx == 0 else min(rbase + timedelta(days=random.randint(1, 10)), TODAY)
                    receipts.append((rcpt_id, repl, wh, ts(r_dt), f"GRN{rcpt_id:07d}"))
                    for (pid, qr, uc) in grp:
                        rcl_id += 1
                        cond = weighted([(1, 9), (3, 1)])
                        receipt_lines.append((rcl_id, rcpt_id, pid, qr, cond))

        if status == 4:
            inv_num += 1
            istatus = weighted([(4, 6), (3, 2), (2, 1), (5, 1)])
            inv_date = date.fromisoformat(received)
            paid = iso(min(inv_date + timedelta(days=random.randint(15, 45)), TODAY)) if istatus == 4 else None
            supplier_invoices.append((inv_num, supplier, repl, f"SINV{inv_num:07d}", total_cost,
                                      istatus, iso(inv_date), iso(inv_date + timedelta(days=30)), paid))
    rows["replenishment_orders"] = repl_orders
    rows["replenishment_lines"] = repl_lines
    rows["receipts"] = receipts
    rows["receipt_lines"] = receipt_lines
    rows["supplier_invoices"] = supplier_invoices

    # -- stock transfers ------------------------------------------------------
    transfers = []
    transfer_lines = []
    tl_id = 0
    for tid in range(1, N_TRANSFERS + 1):
        a, b = random.sample(warehouse_ids, 2)
        created = random_date(ORDER_START, TODAY)
        status = weighted([(3, 6), (2, 2), (1, 1), (4, 1)])
        shipped = iso(created + timedelta(days=random.randint(0, 3))) if status in (2, 3) else None
        received = iso(min(created + timedelta(days=random.randint(3, 12)), TODAY)) if status == 3 else None
        transfers.append((tid, a, b, status, iso(created), shipped, received))
        for pid in random.sample(range(1, N_PRODUCTS + 1), random.randint(1, 6)):
            tl_id += 1
            qreq = random.randint(10, 200)
            qship = qreq if status in (2, 3) else 0
            qrecv = qreq if status == 3 else 0
            transfer_lines.append((tl_id, tid, pid, qreq, qship, qrecv))
    rows["stock_transfers"] = transfers
    rows["stock_transfer_lines"] = transfer_lines

    # -- inventory adjustments ------------------------------------------------
    adjustments = []
    for adj in range(1, N_ADJUSTMENTS + 1):
        w = random.choice(warehouse_ids)
        pid = random.randint(1, N_PRODUCTS)
        reason = weighted([(1, 5), (2, 3), (3, 1), (4, 2), (5, 2)])
        delta = random.randint(-30, 30)
        adjustments.append((adj, w, pid, iso(random_date(TODAY - timedelta(days=365), TODAY)), delta, reason))
    rows["inventory_adjustments"] = adjustments

    # -- cycle counts ---------------------------------------------------------
    cycle_counts = []
    for cc in range(1, N_CYCLE_COUNTS + 1):
        w = random.choice(warehouse_ids)
        pid = random.randint(1, N_PRODUCTS)
        sys_q = random.randint(0, 400)
        var = random.choice([0, 0, 0, -2, -1, 1, 2, -5, 5])
        counted_q = max(0, sys_q + var)
        bin_id = random.choice(wh_bins[w]) if wh_bins[w] else None
        status = weighted([(3, 5), (2, 3), (1, 2)])
        cycle_counts.append((cc, w, pid, bin_id, sys_q, counted_q, counted_q - sys_q,
                             iso(random_date(TODAY - timedelta(days=200), TODAY)), status))
    rows["cycle_counts"] = cycle_counts

    # -- inventory transactions ledger (derived from real events) -------------
    txns = []
    tx_id = 0

    def add_txn(w, item, ttype, delta, ref_type, ref_id, when):
        nonlocal tx_id
        tx_id += 1
        txns.append((tx_id, w, item, ttype, delta, ref_type, ref_id, when))

    for (rcl, rcpt, pid, qr, cond) in receipt_lines:
        rc = next(r for r in receipts if r[0] == rcpt)
        add_txn(rc[2], pid, 1, qr, "receipt", rcpt, rc[3])
    for (si, ship, pkg, line_id, sku, qty) in shipment_items:
        sh = next(s for s in shipments if s[0] == ship)
        add_txn(sh[4], int(sku[4:]), 2, -qty, "shipment", ship, ts(date.fromisoformat(sh[6])))
    for (adj, w, pid, adate, delta, reason) in adjustments:
        add_txn(w, pid, 5, delta, "adjustment", adj, ts(date.fromisoformat(adate)))
    for (tl, tid, pid, qreq, qship, qrecv) in transfer_lines:
        if qship:
            tr = next(t for t in transfers if t[0] == tid)
            add_txn(tr[1], pid, 3, -qship, "transfer", tid, ts(date.fromisoformat(tr[4])))
            if qrecv:
                add_txn(tr[2], pid, 4, qrecv, "transfer", tid, ts(date.fromisoformat(tr[4])))
    # return_restock: physically-received returns dispositioned back to sellable
    # stock post a positive delta at the warehouse that fulfilled the order.
    rlines_by_ret = {}
    for (rl, rid, sku, qty, cond) in return_lines:
        rlines_by_ret.setdefault(rid, []).append((sku, qty))
    for (rid, oid, rma, reason, rstatus, disposition, req_iso, received) in returns:
        if disposition != 1 or rstatus not in (3, 4) or received is None:
            continue
        wh = order_ship_wh.get(oid) or random.choice(active_warehouses)
        for (sku, qty) in rlines_by_ret.get(rid, []):
            add_txn(wh, int(sku[4:]), 6, qty, "return", rid, ts(date.fromisoformat(received)))
    rows["inventory_transactions"] = txns

    _write(rows)
    _summary(rows)


def _order_tuples(orders):
    return [(o["order_id"], o["customer_id"], iso(o["order_date"]), o["status"],
             o["priority"], o["channel"], o["ship_addr"], o["promised"], o["total"])
            for o in orders]


def _write(rows):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = OFF")
    with open(SCHEMA) as f:
        conn.executescript(f.read())
    for table, data in rows.items():
        if not data:
            continue
        n = len(data[0])
        conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * n)})", data)
    conn.commit()
    conn.close()


def _summary(rows):
    total = sum(len(v) for v in rows.values())
    print(f"data.db built: {len(rows)} tables, {total:,} rows")


if __name__ == "__main__":
    build()
