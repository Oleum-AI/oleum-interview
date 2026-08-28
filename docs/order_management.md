# Order Management

This is the reference for the Order Management domain: who buys from us, what
they buy, what they pay, and the states an order moves through from creation to
fulfillment or cancellation. It covers the customer master, the product catalog,
orders and their lines, the order status ledger, payments, promotions, and gift
cards.

Order Management is the transactional heart of the warehouse. Almost every
question about revenue, demand, customer behaviour, or channel mix starts here
and joins outward into Fulfillment (see `fulfillment_and_shipping.md`) and
Warehouse & Inventory (see `warehouse_and_inventory.md`). Because those two
downstream domains identify products by a *different* key than orders do, read
the identifier notes in this document carefully and keep
`reference.md` open alongside it.

Coded columns (`status`, `*_code`) are decoded via the **Code Dictionary** in `reference.md`; this guide names the code set each column uses, and that dictionary gives the integer values.

## Tables in this domain

Fourteen tables make up Order Management. Grouped by area:

| Area | Tables | Grain |
|---|---|---|
| Customers | `customers`, `customer_addresses` | one row per customer / per address |
| Catalog | `product_categories`, `products`, `product_attributes`, `price_history` | category / product / attribute / effective-dated price |
| Orders | `orders`, `order_lines`, `order_status_history` | order header / order line / status transition |
| Money on the order | `payments`, `promotions`, `order_promotions` | payment / campaign / per-order discount |
| Gift cards | `gift_cards`, `gift_card_transactions` | card / card transaction |

The join spine is `customers` → `orders` → `order_lines`, with `orders` also the
anchor for `payments`, `order_promotions`, `order_status_history`, and — reaching
into the other domains — shipments, returns, and pick tasks. Products are the
bridge from the SKU vocabulary used here to the item_code vocabulary used in
inventory and supply.

## Conventions used in this document

A few conventions keep the worked examples consistent and safe to copy:

- **TODAY is `2024-12-31`.** Every "as of now" calculation anchors on that date.
  Order history runs from `2023-01-01` to TODAY; customers and gift cards can be
  older.
- **Money is USD with two decimals.** All amount columns are stored as SQLite
  `REAL`. Round only at presentation time. See `reference.md`.
- **Coded columns hold integers whose meaning is a two-hop lookup.** A column
  such as `orders.status` points at a *code set* (here, the ORDER_STATUS code
  set); the integer-to-label mapping for every code set lives in
  `reference.md`. This document names the code set and uses the
  human-readable label; it never prints the underlying integer next to the
  label. In the SQL examples, coded filters are written with a named parameter
  (for example `:fulfilled`) and a comment naming the code set and label — bind
  the integer from `reference.md` when you run the query.
- **`status` / `status_code` means something different in every table.** The
  ORDER_STATUS set that decodes `orders.status` does not decode
  `shipments.status`, `returns.status`, `payments.status_code`, or any other
  `status`-family column. Never carry a decode from one table to another. See
  `reference.md`.
- **Boolean flags (`is_active`, `is_default`, `is_preferred`) are plain 0/1
  columns**, not code sets, and are filtered directly (`is_active = 1`).

---

## Table: customers

- **Columns:** customer_id, first_name, last_name, email, phone, segment_code, signup_date, is_active
- **Joined by:** PK `customer_id` (← `orders.customer_id`, `customer_addresses.customer_id`, `gift_cards.customer_id`)

`customers` is the party master for people and organizations that place orders.

| Column | Meaning |
|---|---|
| `customer_id` | Surrogate primary key. The join key used by `orders`, `customer_addresses`, and optionally `gift_cards`. |
| `first_name`, `last_name` | Personal name parts. For business and government accounts these still carry the name of the contact on file. Concatenate for a display name. |
| `email` | Contact email. Nullable in the schema; treat a missing email as "no email on file", not as an error. |
| `phone` | Contact phone, free-text formatted `(NPA) NXX-XXXX`. Nullable. Not a reliable join or dedupe key. |
| `segment_code` | The customer's commercial segment. Decodes against the **CUSTOMER_SEGMENT** code set. |
| `signup_date` | ISO date the customer was created. Ranges back to 2018, i.e. earlier than the order history window. |
| `is_active` | 1 if the account is active, 0 if deactivated. A deactivated customer can still own historical orders. |

### Customer segments

`segment_code` decodes against the **CUSTOMER_SEGMENT** code set (values in
`reference.md`). The segments, from most to least common, are:

- **consumer** — individual retail shoppers. The large majority of accounts.
- **small_business** — small commercial buyers.
- **enterprise** — large commercial accounts.
- **government** — public-sector buyers. The smallest segment.

Segment is a property of the *customer*, not of the order. If you need
"revenue by segment" you join orders back to the customer and group on
`segment_code`; there is no segment column on `orders`.

```sql
-- Active customers by segment
SELECT segment_code,          -- CUSTOMER_SEGMENT; label via reference.md
       COUNT(*) AS customers
FROM customers
WHERE is_active = 1
GROUP BY segment_code
ORDER BY customers DESC;
```

Two things to keep in mind. First, `is_active = 0` does not mean the customer
never ordered; deactivated accounts retain their order history and should be
included in historical revenue unless the question is specifically about the
*current active base*. Second, `signup_date` predates the order window, so you
cannot assume every customer has an order — many will have none in the
`2023-01-01`..TODAY range.

```sql
-- Customers who have never placed an order (any status)
SELECT c.customer_id, c.first_name, c.last_name
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
```

`email` and `phone` are both nullable and neither is a stable identity key: the
schema does not enforce uniqueness on either, so do not use them to deduplicate
or join customers. `customer_id` is the only identity key. A display name is the
concatenation of `first_name` and `last_name`; expect duplicates across distinct
customers (two different `customer_id`s can share a name), which is another reason
to key on `customer_id`.

When attributing money to a segment, remember the segment lives on the customer,
so the internal_test exclusion (a property of the *order*) still applies on the
order side of the join:

```sql
-- Average order value and revenue by customer segment (reporting-eligible orders)
SELECT c.segment_code,                 -- CUSTOMER_SEGMENT; label via reference.md
       COUNT(o.order_id)              AS orders,
       ROUND(SUM(o.order_total), 2)   AS gross_revenue,
       ROUND(AVG(o.order_total), 2)   AS avg_order_value
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY c.segment_code
ORDER BY gross_revenue DESC;
```

Signup date supports simple cohorting. Because `signup_date` reaches back to
2018 while orders begin in 2023, a "signup-year cohort" is about acquisition, not
activity — a 2018 cohort customer may only have orders from 2023 onward:

```sql
-- Customer acquisition by signup year
SELECT substr(signup_date, 1, 4) AS signup_year, COUNT(*) AS customers
FROM customers
GROUP BY signup_year
ORDER BY signup_year;
```

---

## Table: customer_addresses

- **Columns:** address_id, customer_id, address_type_code, line1, city, state, postal_code, country, is_default
- **Joined by:** PK `address_id` (← `orders.ship_to_address_id`); FK `customer_id` → `customers.customer_id`

`customer_addresses` holds one or more postal addresses per customer. An order's
`ship_to_address_id` points into this table.

| Column | Meaning |
|---|---|
| `address_id` | Primary key; the target of `orders.ship_to_address_id`. |
| `customer_id` | Owning customer. |
| `address_type_code` | Billing, shipping, or both. Decodes against the **ADDRESS_TYPE** code set. |
| `line1`, `city`, `state`, `postal_code`, `country` | Postal geography. `country` is `USA` throughout this dataset. |
| `is_default` | 1 for the customer's default address, 0 otherwise. The first address created for each customer is the default. |

### Address type and default

`address_type_code` decodes against the **ADDRESS_TYPE** code set with labels
**billing**, **shipping**, and **both**. A customer has one or two addresses; the
first is always flagged `is_default = 1`. Do not assume the default address is a
shipping address — its type can be billing, shipping, or both. When you need
"where did this order ship", follow the order's `ship_to_address_id` rather than
guessing the default:

```sql
-- Ship-to geography for fulfilled orders, by state
SELECT a.state, COUNT(*) AS orders
FROM orders o
JOIN customer_addresses a ON a.address_id = o.ship_to_address_id
WHERE o.status = :fulfilled            -- ORDER_STATUS 'fulfilled'; reference.md
  AND o.priority_code <> :internal_test -- exclude internal/QA; ORDER_PRIORITY, see the Exclusions section of reference.md
GROUP BY a.state
ORDER BY orders DESC;
```

`orders.ship_to_address_id` is nullable (draft orders may not have one), so use
an inner join only when you specifically want orders that *have* a ship-to
address, and a left join when counting all orders.

Address type distribution across the base is a quick profile of how customers
maintain billing vs shipping addresses:

```sql
-- How customer addresses split by type, and how many are defaults
SELECT address_type_code,              -- ADDRESS_TYPE; label via reference.md
       COUNT(*) AS addresses,
       SUM(is_default) AS defaults
FROM customer_addresses
GROUP BY address_type_code
ORDER BY addresses DESC;
```

Because `country` is uniformly `USA` and geography is otherwise plain text, group
on `state` or `city` for regional cuts. There is no separate region/territory
table — regional rollups are derived from `state`.

A customer has one or two addresses, so joining orders to addresses is a
one-row-per-order lookup through `ship_to_address_id` and does not fan out. Do
**not** instead join `orders` to `customer_addresses` on `customer_id`: that
matches every address the customer owns and multiplies the order rows. The only
correct order → address path is through `ship_to_address_id`:

```sql
-- WRONG: fans out one order into one row per customer address
SELECT o.order_id, a.city
FROM orders o
JOIN customer_addresses a ON a.customer_id = o.customer_id;   -- duplicates orders

-- RIGHT: the order's actual ship-to
SELECT o.order_id, a.city
FROM orders o
JOIN customer_addresses a ON a.address_id = o.ship_to_address_id;
```

If you specifically want billing geography (say, for tax or AP-style cuts), you
cannot get it from `ship_to_address_id`; you would look up the customer's
address whose `address_type_code` carries the billing (or both) label of the
ADDRESS_TYPE code set. Keep in mind a customer may have no billing-typed address
at all, so use a LEFT JOIN when that is a real possibility.

---

## Product catalog

The catalog is four tables: `product_categories` (a hierarchy), `products` (the
sellable master and the identifier bridge), `product_attributes` (name/value
descriptors), and `price_history` (effective-dated list prices).

### Table: product_categories

- **Columns:** category_id, name, parent_category_id
- **Joined by:** PK `category_id` (← `products.category_id`); FK `parent_category_id` → `product_categories.category_id` (self-referencing)

A self-referencing hierarchy of merchandising categories.

| Column | Meaning |
|---|---|
| `category_id` | Primary key. |
| `name` | Category name. |
| `parent_category_id` | Parent category, or NULL for a top-level category. |

Top-level categories (Electronics, Home & Kitchen, Apparel, Grocery, Sports &
Outdoors, Toys & Games, Health & Beauty) have `parent_category_id IS NULL`. Some
have children (for example Electronics is the parent of Computers and Audio;
Home & Kitchen is the parent of Cookware and Furniture; Apparel is the parent of
Men's and Women's Clothing). Products attach to categories; in this dataset every
product sits on a *leaf* (child, or childless top-level) category, so a naive
`GROUP BY category_id` counts products at the leaf level.

To roll products up to their top-level category, walk one hop up the parent
chain and coalesce to self for categories that are already top-level:

```sql
-- Products per top-level category
SELECT COALESCE(top.name, cat.name) AS top_category,
       COUNT(p.product_id)          AS products
FROM products p
JOIN product_categories cat ON cat.category_id = p.category_id
LEFT JOIN product_categories top ON top.category_id = cat.parent_category_id
GROUP BY top_category
ORDER BY products DESC;
```

The hierarchy here is at most two levels deep, so a single self-join reaches the
root. If you ever need an arbitrary-depth walk (or want a query that survives a
deeper hierarchy later), use a recursive CTE seeded on the leaf and climbing
`parent_category_id` until it is NULL:

```sql
-- Root (top-level) category for every category, via recursive climb
WITH RECURSIVE climb(category_id, ancestor_id, ancestor_name, parent_id) AS (
    SELECT category_id, category_id, name, parent_category_id
    FROM product_categories
    UNION ALL
    SELECT c.category_id, pc.category_id, pc.name, pc.parent_category_id
    FROM climb c
    JOIN product_categories pc ON pc.category_id = c.parent_id
)
SELECT category_id, ancestor_name AS top_category
FROM climb
WHERE parent_id IS NULL;    -- the ancestor with no parent is the root
```

Revenue by category joins order lines up through `products` to the category, then
optionally rolls to the top level. Note the join to order lines is on `sku`
(order side); the category lives on `products`:

```sql
-- Revenue by leaf category (reporting-eligible orders)
SELECT cat.name AS category, ROUND(SUM(ol.line_total), 2) AS revenue
FROM order_lines ol
JOIN products p            ON p.sku = ol.sku
JOIN product_categories cat ON cat.category_id = p.category_id
JOIN orders o              ON o.order_id = ol.order_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY cat.name
ORDER BY revenue DESC;
```

### Table: products

- **Columns:** product_id, sku, name, category_id, unit_price, weight_kg, is_active, launched_date
- **Joined by:** PK `product_id` (= `item_code` on the inventory/supplier side — the SKU⇄item_code bridge); `sku` (← `order_lines.sku`, `return_lines.sku`, `shipment_items.sku`); FK `category_id` → `product_categories.category_id`

The master record for every sellable item, and the single bridge between the two
product-identifier vocabularies used across the warehouse.

| Column | Meaning |
|---|---|
| `product_id` | Surrogate primary key. On the inventory/supplier/warehouse side this same integer is the **`item_code`** (see below and `reference.md`). |
| `sku` | Business identifier, TEXT, formatted `SKU-00042`. On the order/returns/shipment side products are referenced by this `sku`. |
| `name` | Display name (brand + noun). |
| `category_id` | Leaf category, FK to `product_categories`. |
| `unit_price` | Current list price in USD. Authoritative for the *current* price of the product (see `reference.md` for how this relates to `price_history`). |
| `weight_kg` | Unit weight in kilograms. Used for shipment weight rollups in `fulfillment_and_shipping.md`. |
| `is_active` | 1 if the product is currently sellable, 0 if discontinued. New orders draw only from active products, but historical order and inventory rows can reference inactive ones. |
| `launched_date` | ISO date the product went live. Ranges 2019–2024. |

**The two identifier vocabularies (critical).** The same physical product is
referenced two different ways depending on which domain you are in:

- **Order / Returns / Shipment side** uses `sku` (TEXT), e.g. `SKU-00042`.
  Tables: `order_lines`, `return_lines`, `shipment_items`.
- **Inventory / Supplier / Warehouse side** uses `item_code` (INTEGER), which
  equals `products.product_id`, e.g. `42`. Tables: `supplier_products`,
  `inventory`, `inventory_lots`, `inventory_transactions`,
  `replenishment_lines`, `receipt_lines`, `stock_transfer_lines`,
  `inventory_adjustments`, `cycle_counts`, `pick_lines`.

`products` is the only place both keys live together. The conversions are:

```
item_code = CAST(SUBSTR(sku, 5) AS INTEGER)     -- 'SKU-00042' -> 42
sku       = 'SKU-' || printf('%05d', item_code) -- 42          -> 'SKU-00042'
```

Never join `order_lines.sku` directly to an inventory-side `item_code`: the
types differ, the join matches nothing, and SQLite returns **zero rows with no
error** — a silent wrong answer. Always bridge through `products`. This is the
single most common cross-domain mistake; `reference.md` treats it
in full and `reference.md` shows the correct patterns.

```sql
-- Catalog summary by activity flag
SELECT is_active, COUNT(*) AS products, ROUND(AVG(unit_price), 2) AS avg_list_price
FROM products
GROUP BY is_active;
```

`is_active` describes *current* sellability, not historical. New orders are
placed only against active products, but a product deactivated after some sales
still appears in historical `order_lines`, in `inventory`, and in supplier
records. So filter `products.is_active = 1` when you want the *current* sellable
assortment, and do **not** filter on it when you want complete historical
revenue or inventory — otherwise you silently drop discontinued items that
legitimately sold.

`launched_date` (2019–2024) supports "products launched in period" and
newness-based cuts; `weight_kg` is the per-unit weight that drives shipment
weight rollups in `fulfillment_and_shipping.md`. Neither carries a code set —
they are plain values.

### Table: product_attributes

- **Columns:** attribute_id, product_id, attr_name, attr_value
- **Joined by:** PK `attribute_id`; FK `product_id` → `products.product_id`

A flexible name/value bag of descriptive attributes, one row per attribute per
product.

| Column | Meaning |
|---|---|
| `attribute_id` | Primary key. |
| `product_id` | Owning product (join on `product_id`; this is the inventory-side key, not the SKU). |
| `attr_name` | Attribute name, e.g. `color`, `warranty_months`, `country_of_origin`. |
| `attr_value` | Attribute value, stored as TEXT even when numeric (e.g. `warranty_months` = `"24"`). |

Because this is an entity-attribute-value table, filtering on an attribute means
matching both `attr_name` and `attr_value`, and comparing numeric attributes
requires a cast:

```sql
-- Products with a warranty of 24 months or more
SELECT p.sku, p.name, CAST(pa.attr_value AS INTEGER) AS warranty_months
FROM product_attributes pa
JOIN products p ON p.product_id = pa.product_id
WHERE pa.attr_name = 'warranty_months'
  AND CAST(pa.attr_value AS INTEGER) >= 24
ORDER BY warranty_months DESC;
```

Attributes are optional metadata; not every analytical product attribute you
might want exists here, and the set of `attr_name`s is not guaranteed uniform
across all products. Check what names are present before building a report on
one:

```sql
SELECT attr_name, COUNT(*) AS rows FROM product_attributes GROUP BY attr_name;
```

To use several attributes side by side, pivot the name/value pairs into columns
with conditional aggregation rather than joining the table to itself repeatedly:

```sql
-- Pivot color / warranty / origin onto one row per product
SELECT p.sku, p.name,
       MAX(CASE WHEN pa.attr_name = 'color'            THEN pa.attr_value END) AS color,
       MAX(CASE WHEN pa.attr_name = 'warranty_months'  THEN pa.attr_value END) AS warranty_months,
       MAX(CASE WHEN pa.attr_name = 'country_of_origin' THEN pa.attr_value END) AS origin
FROM products p
LEFT JOIN product_attributes pa ON pa.product_id = p.product_id
GROUP BY p.sku, p.name;
```

The LEFT JOIN keeps products that are missing a given attribute (the pivoted cell
is NULL), which is the safe default when attribute coverage is uneven.

### Table: price_history

- **Columns:** price_history_id, product_id, effective_date, unit_price
- **Joined by:** PK `price_history_id`; FK `product_id` → `products.product_id`

An effective-dated log of list prices per product.

| Column | Meaning |
|---|---|
| `price_history_id` | Primary key. |
| `product_id` | Owning product. |
| `effective_date` | ISO date the price took effect. |
| `unit_price` | List price in USD effective from that date. |

Each product has one to four price-history rows. **`products.unit_price` is the
authoritative current list price**; `price_history` is the historical log used to
answer "what was the list price on date X". To get the price effective on a given
date, take the most recent effective row on or before that date:

```sql
-- List price of each product effective on a given date (:asof)
SELECT ph.product_id, ph.unit_price
FROM price_history ph
WHERE ph.effective_date = (
    SELECT MAX(ph2.effective_date)
    FROM price_history ph2
    WHERE ph2.product_id = ph.product_id
      AND ph2.effective_date <= :asof     -- e.g. '2024-06-30'
);
```

Two caveats. First, the most recent `price_history` row is not guaranteed to
equal the current `products.unit_price` — for the *current* list price use
`products.unit_price`, and use `price_history` only for a point-in-time historical
price. Second, neither of these is the price the customer actually *paid*: the
price on the order is captured on `order_lines.unit_price` at order time (see the
next section). The full treatment of which price is authoritative for which
purpose is in `reference.md`.

Because a product can have as few as one price-history row, the "price on date X"
subquery above can return no row for a product whose earliest effective date is
after X. Decide whether that means "no price then" (exclude) or "fall back to the
current list price" (coalesce to `products.unit_price`) based on the question;
do not assume every product has continuous price coverage back to any date.

```sql
-- Price on :asof, falling back to current list price where history has no row yet
SELECT p.product_id, p.sku,
       COALESCE((
           SELECT ph.unit_price FROM price_history ph
           WHERE ph.product_id = p.product_id AND ph.effective_date <= :asof
           ORDER BY ph.effective_date DESC LIMIT 1
       ), p.unit_price) AS price_on_asof
FROM products p;
```

---

## Table: orders

- **Columns:** order_id, customer_id, order_date, status, priority_code, channel_code, ship_to_address_id, promised_date, order_total
- **Joined by:** PK `order_id` (← `order_lines`, `order_status_history`, `payments`, `order_promotions`, `shipments`, `returns`, `pick_tasks`, `gift_card_transactions`); FK `customer_id` → `customers.customer_id`, `ship_to_address_id` → `customer_addresses.address_id`

`orders` is the order header — one row per order.

| Column | Meaning |
|---|---|
| `order_id` | Surrogate primary key. |
| `customer_id` | Placing customer, FK to `customers`. |
| `order_date` | ISO date the order was created. Order history spans `2023-01-01`..TODAY. |
| `status` | Current lifecycle state. Decodes against the **ORDER_STATUS** code set. |
| `priority_code` | Handling priority tier. Decodes against the **ORDER_PRIORITY** code set. |
| `channel_code` | Sales channel the order came through. Decodes against the **ORDER_CHANNEL** code set. |
| `ship_to_address_id` | FK to `customer_addresses`. Nullable (draft orders may lack one). |
| `promised_date` | ISO date delivery was promised to the customer. NULL for draft orders. |
| `order_total` | Order value in USD (see composition below). |

### Order status

`status` decodes against the **ORDER_STATUS** code set with labels **draft**,
**placed**, **confirmed**, **fulfilled**, **cancelled**, and **returned**. The
happy path runs draft → placed → confirmed → fulfilled; an order can instead be
cancelled, or move to returned after having been fulfilled. The **fulfilled**
label is the terminal "successful" state and is the one most revenue and
volume metrics filter to. Full state-machine notes, and the transition ledger,
are in `reference.md`.

Remember rule G2: this ORDER_STATUS decode applies **only** to `orders.status`
(and to `order_status_history.status`, which shares the set). It does not apply
to `shipments.status`, `returns.status`, `payments.status_code`, or anything
else. The integer that means "fulfilled" for an order does not mean the same
thing anywhere else.

```sql
-- Order counts by status (reporting-eligible orders only)
SELECT status,                         -- ORDER_STATUS; label via reference.md
       COUNT(*) AS orders
FROM orders
WHERE priority_code <> :internal_test  -- exclude internal/QA; ORDER_PRIORITY, see the Exclusions section of reference.md
GROUP BY status
ORDER BY orders DESC;
```

The great majority of orders reach the fulfilled state; smaller shares are
cancelled or returned, and a few remain in the earlier draft/placed/confirmed
states. Two distinctions matter for counting:

- **Draft** orders are incomplete — they may have no `ship_to_address_id`, no
  `promised_date`, and no payment. Exclude them from "orders placed" style
  counts unless you specifically want work-in-progress.
- **Cancelled** and **returned** are different events at different points in the
  lifecycle: cancelled orders never fulfilled (no shipment); returned orders were
  fulfilled and then came back (they have a shipment and a `returns` record).
  Neither should be counted as clean fulfilled demand. The relationship between
  order status and downstream shipments/returns is spelled out in
  `reference.md`.

A frequent reporting definition is "successfully fulfilled orders", which is the
fulfilled state with the internal_test exclusion applied:

```sql
-- Successfully fulfilled order count and value, by order month
SELECT substr(order_date, 1, 7) AS ym,
       COUNT(*) AS fulfilled_orders,
       ROUND(SUM(order_total), 2) AS gross_value
FROM orders
WHERE status = :fulfilled              -- ORDER_STATUS 'fulfilled'; reference.md
  AND priority_code <> :internal_test  -- see the Exclusions section of reference.md
GROUP BY ym
ORDER BY ym;
```

### Order priority — and the internal_test exclusion

`priority_code` decodes against the **ORDER_PRIORITY** code set. The real,
customer-facing tiers are **standard**, **expedited**, and **rush**. There is a
fourth tier, **internal_test**, used for internal and QA orders that are created
against the production system for testing and verification.

**Standard reporting excludes internal_test orders.** They are not real demand:
they should be dropped from order counts, revenue, fulfillment rates, channel
mix, and essentially every business metric. About 3% of order rows carry the
internal_test label, and they are deliberately indistinguishable from real orders
by any other field — normal customers, normal amounts, normal shipments — so the
only safe way to remove them is to filter on `priority_code`. Treat the exclusion
as a standing `WHERE priority_code <> :internal_test` on any orders-based report.
This rule and its rationale are documented in `reference.md`;
the ORDER_PRIORITY values are in `reference.md`.

```sql
-- Real order priority mix (internal_test removed)
SELECT priority_code,                  -- ORDER_PRIORITY; label via reference.md
       COUNT(*) AS orders
FROM orders
WHERE priority_code <> :internal_test  -- drop internal/QA orders; see the Exclusions section of reference.md
GROUP BY priority_code
ORDER BY orders DESC;
```

Because internal_test orders sail through the same status, payment, and shipment
generation as real ones, forgetting this filter inflates every downstream number
by roughly 3%. When in doubt, apply the exclusion; the only reports that
legitimately *include* internal_test orders are the ones explicitly auditing
that test traffic.

To see the size of the exclusion for a given report period, count the
internal_test share directly:

```sql
-- Share of orders carrying the internal_test priority label
SELECT
  SUM(CASE WHEN priority_code =  :internal_test THEN 1 ELSE 0 END) AS test_orders,
  SUM(CASE WHEN priority_code <> :internal_test THEN 1 ELSE 0 END) AS real_orders,
  ROUND(100.0 * SUM(CASE WHEN priority_code = :internal_test THEN 1 ELSE 0 END)
        / COUNT(*), 2) AS test_pct         -- ORDER_PRIORITY 'internal_test'; reference.md
FROM orders;
```

Downstream tables (shipments, payments, returns, pick tasks) inherit the same
contamination through their `order_id`, so the exclusion has to be applied by
joining back to `orders` and filtering `priority_code`, not by hoping the child
table carries a flag — it does not. Every child-table example in this document
and in `fulfillment_and_shipping.md` and `warehouse_and_inventory.md` therefore joins to `orders` to enforce it.

### Order channel

`channel_code` decodes against the **ORDER_CHANNEL** code set with labels
**web**, **mobile_app**, **phone**, **marketplace**, and **in_store**. Web and
mobile_app together dominate; marketplace is a meaningful third; phone and
in_store are small. Channel is often crossed with segment or status:

```sql
-- Channel mix among reporting-eligible orders
SELECT channel_code,                   -- ORDER_CHANNEL; label via reference.md
       COUNT(*) AS orders,
       ROUND(SUM(order_total), 2) AS gross_total
FROM orders
WHERE priority_code <> :internal_test  -- see the Exclusions section of reference.md
GROUP BY channel_code
ORDER BY orders DESC;
```

Channel is an attribute of the order, not the customer, so the same customer can
appear across several channels. That makes channel-by-segment a genuine
cross-tab rather than a customer property:

```sql
-- Orders and value by segment × channel (reporting-eligible orders)
SELECT c.segment_code,                 -- CUSTOMER_SEGMENT
       o.channel_code,                 -- ORDER_CHANNEL
       COUNT(*)                     AS orders,
       ROUND(SUM(o.order_total), 2) AS gross_total
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY c.segment_code, o.channel_code
ORDER BY c.segment_code, orders DESC;
```

### order_total and promised_date

`order_total` is the USD value of the order and is the **sum of its order-line
`line_total` values** (each of which is already net of the line-level
`discount_amount`). It does **not** subtract any `order_promotions` discount —
order-level promotional discounts are recorded separately and are not netted out
of `order_total`. See `reference.md` for the full composition of
order value and how to compute a promotion-net figure.

`promised_date` is the delivery commitment made to the customer at order time and
is NULL on draft orders. It is the order header's own promise; note that a
*shipment* carries its own `promised_date` for delivery-performance measurement,
and the two are maintained independently — for on-time / late analysis use the
shipment's dates (see `fulfillment_and_shipping.md`), not the order header's.

`order_date` is the placement date and is the natural time axis for order-volume
and revenue trends (monthly cuts with `substr(order_date, 1, 7)`, as above).
Order history is bounded to `2023-01-01`..TODAY, so a trend that appears to start
in 2023 reflects the data window, not a business inflection. When you need the
*fulfillment* timeline rather than the placement date, go to
`order_status_history` (below) for the timestamped transitions.

```sql
-- Reconcile header total against the sum of its lines (should match)
SELECT o.order_id, o.order_total,
       ROUND(SUM(ol.line_total), 2) AS lines_total
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY o.order_id, o.order_total
HAVING ROUND(o.order_total, 2) <> ROUND(SUM(ol.line_total), 2);
```

---

## Table: order_lines

- **Columns:** order_line_id, order_id, sku, quantity, unit_price, discount_amount, line_total
- **Joined by:** PK `order_line_id` (← `shipment_items.order_line_id`); FK `order_id` → `orders.order_id`; `sku` → `products.sku` (bridge to `item_code`)

`order_lines` holds the individual line items of an order — one row per product
per order.

| Column | Meaning |
|---|---|
| `order_line_id` | Primary key. Referenced by `shipment_items.order_line_id` in Fulfillment. |
| `order_id` | Owning order. |
| `sku` | Product identifier, TEXT, FK-by-convention to `products.sku`. **This is the SKU vocabulary**, not `item_code`. |
| `quantity` | Units ordered on this line. |
| `unit_price` | USD price per unit *captured at order time*. This is the price the customer was charged, and may differ from the product's current `unit_price` and from any `price_history` row. |
| `discount_amount` | USD line-level discount already applied (0.00 when none). |
| `line_total` | USD line value = `quantity * unit_price - discount_amount`. Rolls up to `orders.order_total`. |

**The SKU lives here.** Order lines reference products by `sku`. Inventory- and
supplier-side tables reference the same products by `item_code` (=
`products.product_id`). To connect an order line to inventory you must bridge
through `products` (`order_lines.sku = products.sku`, then
`products.product_id = <inventory-side>.item_code`). Joining `order_lines.sku`
straight to `inventory.item_code` returns zero rows silently. See
`reference.md`.

```sql
-- Top products by units ordered (reporting-eligible orders), joined via products
SELECT p.sku, p.name, SUM(ol.quantity) AS units
FROM order_lines ol
JOIN products p ON p.sku = ol.sku
JOIN orders  o ON o.order_id = ol.order_id
WHERE o.priority_code <> :internal_test     -- see the Exclusions section of reference.md
GROUP BY p.sku, p.name
ORDER BY units DESC
LIMIT 20;
```

`line_total` is the authoritative unit of revenue at line grain — always prefer
summing `line_total` over recomputing `quantity * unit_price`, because it already
reflects the line discount. Revenue and discount definitions are in
`reference.md` and `reference.md`.

Orders carry one or more lines (baskets of a few items are typical), so any
line-level metric — units, basket size, per-line discount — must be aggregated
back to the order or product grain deliberately. Basket size and attach are line
counts per order:

```sql
-- Average basket size (distinct products per order), reporting-eligible orders
SELECT ROUND(AVG(lines_per_order), 2) AS avg_lines_per_order
FROM (
    SELECT ol.order_id, COUNT(*) AS lines_per_order
    FROM order_lines ol
    JOIN orders o ON o.order_id = ol.order_id
    WHERE o.priority_code <> :internal_test    -- see the Exclusions section of reference.md
    GROUP BY ol.order_id
);
```

Be careful mixing grains: if you join `orders` to `order_lines` and also to
another one-to-many table (payments is one-per-order so it is safe, but
`order_promotions` or `shipment_items` are not), summing `order_total` across the
fanned-out rows double counts. Aggregate each many-side to the order grain in a
subquery first, then join, or sum `line_total` at the line grain and the header
`order_total` only once per order.

---

## Table: order_status_history

- **Columns:** history_id, order_id, status, changed_ts, note
- **Joined by:** PK `history_id`; FK `order_id` → `orders.order_id`

`order_status_history` is an append-only ledger of every status an order has
passed through.

| Column | Meaning |
|---|---|
| `history_id` | Primary key. |
| `order_id` | Owning order. |
| `status` | The status the order entered at this transition. Decodes against the **ORDER_STATUS** code set — the same set as `orders.status`. |
| `changed_ts` | ISO timestamp of the transition. |
| `note` | Optional free-text note; frequently NULL. |

Rows are inserted as the order advances, so the history reflects the path the
order took (for example a cancelled order shows draft → placed → cancelled; a
returned order shows draft → placed → confirmed → fulfilled → returned). The
current `orders.status` equals the status of the most recent history row for that
order. The `note` column is optional free text and is frequently NULL; do not
rely on it as a structured field — the structured signal is `status` +
`changed_ts`. This table is where you measure *timing* — how long an order sat in a
state, or when it reached fulfilled:

```sql
-- When each order first reached the 'fulfilled' state
SELECT order_id, MIN(changed_ts) AS fulfilled_ts
FROM order_status_history
WHERE status = :fulfilled              -- ORDER_STATUS 'fulfilled'; reference.md
GROUP BY order_id;
```

Because it shares the ORDER_STATUS code set with `orders.status`, the same
labels apply — but only these two columns use that set. Time-in-state and cycle
time analytics belong to `reference.md`.

A common timing measure is order-to-fulfillment cycle time: the gap between the
draft (creation) transition and the fulfilled transition. Pull both timestamps
from the ledger and difference them:

```sql
-- Order-to-fulfillment days for fulfilled, reporting-eligible orders
SELECT h.order_id,
       julianday(f.fulfilled_ts) - julianday(h.created_ts) AS days_to_fulfill
FROM (SELECT order_id, MIN(changed_ts) AS created_ts
      FROM order_status_history GROUP BY order_id) h
JOIN (SELECT order_id, MIN(changed_ts) AS fulfilled_ts
      FROM order_status_history
      WHERE status = :fulfilled          -- ORDER_STATUS 'fulfilled'; reference.md
      GROUP BY order_id) f ON f.order_id = h.order_id
JOIN orders o ON o.order_id = h.order_id
WHERE o.priority_code <> :internal_test; -- see the Exclusions section of reference.md
```

Use `MIN(changed_ts)` for the *first* time an order entered a state; an order
should reach fulfilled at most once, but taking the minimum is defensive.

---

## Table: payments

- **Columns:** payment_id, order_id, method_code, status_code, amount, paid_date
- **Joined by:** PK `payment_id`; FK `order_id` → `orders.order_id`

`payments` records the money movement associated with an order. Non-draft orders
carry a payment; the payment amount equals the order total.

| Column | Meaning |
|---|---|
| `payment_id` | Primary key. |
| `order_id` | Owning order. |
| `method_code` | Tender type. Decodes against the **PAYMENT_METHOD** code set. |
| `status_code` | Payment state. Decodes against the **PAYMENT_STATUS** code set. |
| `amount` | USD amount, equal to the order total at payment time. |
| `paid_date` | ISO date funds moved; present for authorized, captured, and refunded payments, NULL when no funds moved (a voided or failed payment). |

### Payment method

`method_code` decodes against the **PAYMENT_METHOD** code set with labels
**credit_card**, **debit_card**, **paypal**, **gift_card**, **net_terms**, and
**wire**. `net_terms` and `wire` skew toward business/government buyers;
`gift_card` ties back to the gift-card tables below. Note this is the tender used
for the order payment; a gift card can also be applied as partial tender and is
tracked in `gift_card_transactions`.

### Payment status

`status_code` decodes against the **PAYMENT_STATUS** code set with labels
**authorized**, **captured**, **refunded**, **voided**, and **failed**. The
normal successful path is authorized then captured; **captured** means the money
was collected. **refunded** payments correspond to returned orders (money given
back — see Returns in `fulfillment_and_shipping.md` and refund handling in
`reference.md`). **voided** and **failed** payments never
collected funds and carry no `paid_date`.

Crucially, `payments.status_code` uses PAYMENT_STATUS, which is a *different code
set* from ORDER_STATUS. The integer that means "captured" for a payment is
unrelated to any `orders.status` value. Do not reuse an order-status decode here.

```sql
-- Captured payment amount by tender (reporting-eligible orders)
SELECT p.method_code,                   -- PAYMENT_METHOD; label via reference.md
       ROUND(SUM(p.amount), 2) AS captured_amount,
       COUNT(*) AS payments
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE p.status_code = :captured         -- PAYMENT_STATUS 'captured'; reference.md
  AND o.priority_code <> :internal_test  -- see the Exclusions section of reference.md
GROUP BY p.method_code
ORDER BY captured_amount DESC;
```

Because payment `amount` mirrors `order_total`, do not treat captured-payment
sums as an independent revenue source: it is the same money viewed from the
tender side. Use whichever grain the question asks for, and keep the internal_test
exclusion on the joined orders.

Payment status tracks the order's commercial outcome: cancelled orders carry
payments that were authorized, voided, or failed (never captured); returned
orders carry a refunded payment; the normal completed path is captured. This
means you can approximate "money actually collected" as the sum of captured
payment amounts, and "money returned" as the sum of refunded payment amounts —
but always over reporting-eligible orders. A payment's `paid_date` is populated
whenever funds moved — authorized, captured, or refunded — and is NULL only for
voided or failed payments, so `paid_date IS NOT NULL` overcounts "collected".
Filter explicitly on the captured label of PAYMENT_STATUS for money actually
collected.

Tender mix by segment is a routine ask and shows how business/government buyers
lean on net_terms and wire:

```sql
-- Payment method mix by customer segment (reporting-eligible orders)
SELECT c.segment_code,                 -- CUSTOMER_SEGMENT; label via reference.md
       p.method_code,                  -- PAYMENT_METHOD;  label via reference.md
       COUNT(*) AS payments
FROM payments p
JOIN orders    o ON o.order_id = p.order_id
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY c.segment_code, p.method_code
ORDER BY c.segment_code, payments DESC;
```

---

## Promotions

Two tables cover promotions: `promotions` (the campaign catalog) and
`order_promotions` (which orders received which promotion, and the discount
granted).

### Table: promotions

- **Columns:** promotion_id, code, name, promo_type_code, value, start_date, end_date
- **Joined by:** PK `promotion_id` (← `order_promotions.promotion_id`)

| Column | Meaning |
|---|---|
| `promotion_id` | Primary key. |
| `code` | Promotion code (e.g. `PROMO001`). |
| `name` | Campaign name. |
| `promo_type_code` | Kind of promotion. Decodes against the **PROMO_TYPE** code set. |
| `value` | Type-dependent magnitude (see below). |
| `start_date`, `end_date` | ISO active window of the campaign. |

`promo_type_code` decodes against the **PROMO_TYPE** code set with labels
**percent_off**, **amount_off**, **bogo**, and **free_shipping**. The `value`
column's meaning depends on the type: for **percent_off** it is a percentage, for
**amount_off** it is a dollar amount, and for **bogo** and **free_shipping** the
`value` is not a meaningful monetary figure (it is recorded as 0). The actual
dollar discount granted to a given order is not derived from `value` at query
time — it is stored directly on `order_promotions.discount_amount` (below). Use
`value` to characterize the campaign, and `order_promotions.discount_amount` to
measure realized discount.

```sql
-- Promotions active on a given date (:asof)
SELECT promotion_id, code, name,
       promo_type_code,                -- PROMO_TYPE; label via reference.md
       value, start_date, end_date
FROM promotions
WHERE :asof BETWEEN start_date AND end_date;   -- e.g. '2024-06-30'
```

### Table: order_promotions

- **Columns:** order_promotion_id, order_id, promotion_id, discount_amount
- **Joined by:** PK `order_promotion_id`; FK `order_id` → `orders.order_id`, `promotion_id` → `promotions.promotion_id`

| Column | Meaning |
|---|---|
| `order_promotion_id` | Primary key. |
| `order_id` | Order the promotion was applied to. |
| `promotion_id` | The promotion applied. |
| `discount_amount` | USD discount granted on this order by this promotion. |

This is the per-order realized promotional discount. It is a separate discount
from the line-level `order_lines.discount_amount`, and — as noted above — it is
**not** subtracted from `orders.order_total`. If a question asks for order value
*net of promotions*, subtract `order_promotions.discount_amount` from
`order_total` explicitly:

```sql
-- Order value net of order-level promotions (reporting-eligible orders)
SELECT o.order_id,
       o.order_total,
       COALESCE(SUM(op.discount_amount), 0) AS promo_discount,
       ROUND(o.order_total - COALESCE(SUM(op.discount_amount), 0), 2) AS net_of_promo
FROM orders o
LEFT JOIN order_promotions op ON op.order_id = o.order_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY o.order_id, o.order_total;
```

An order can in principle receive more than one promotion row; sum
`discount_amount` per order rather than assuming a single row. Not every order
has a promotion — most do not — so join with a LEFT JOIN and coalesce the sum to
zero. Revenue-vs-discount definitions live in `reference.md`.

To measure a campaign's reach and cost, aggregate `order_promotions` up to the
promotion, then join the catalog for the campaign's name and type:

```sql
-- Reach and realized discount per promotion (reporting-eligible orders)
SELECT pr.code, pr.name,
       pr.promo_type_code,             -- PROMO_TYPE; label via reference.md
       COUNT(DISTINCT op.order_id)      AS orders_using,
       ROUND(SUM(op.discount_amount),2) AS total_discount
FROM order_promotions op
JOIN promotions pr ON pr.promotion_id = op.promotion_id
JOIN orders     o  ON o.order_id = op.order_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY pr.code, pr.name, pr.promo_type_code
ORDER BY total_discount DESC;
```

Watch the grain: joining `orders` → `order_lines` → `order_promotions` in one
flat query multiplies the promotion discount by the number of lines. Aggregate
`order_promotions` to the order (or promotion) grain in a subquery before
combining it with line-level revenue.

---

## Gift cards

Gift cards are both a product we sell and a form of tender. Two tables cover
them: `gift_cards` (the card master and its running balance) and
`gift_card_transactions` (the ledger of activity against each card).

### Table: gift_cards

- **Columns:** gift_card_id, code, initial_balance, current_balance, status_code, issued_date, customer_id
- **Joined by:** PK `gift_card_id` (← `gift_card_transactions.gift_card_id`); FK `customer_id` → `customers.customer_id` (nullable)

| Column | Meaning |
|---|---|
| `gift_card_id` | Primary key. |
| `code` | Card code (e.g. `GC000123`). |
| `initial_balance` | USD value loaded at issue. |
| `current_balance` | USD balance remaining now. |
| `status_code` | Card state. Decodes against the **GIFTCARD_STATUS** code set. |
| `issued_date` | ISO date the card was issued. |
| `customer_id` | Owning customer, FK to `customers`; **nullable** (a card need not be tied to a known customer). |

`status_code` decodes against the **GIFTCARD_STATUS** code set with labels
**active**, **redeemed**, **expired**, and **void**. An **active** card carries
its full or remaining balance; a **redeemed** card has been (largely) spent down;
**expired** and **void** cards carry no usable balance. As with every other
`status_code` column, this uses its own code set — GIFTCARD_STATUS decodes only
gift-card status, nothing else.

```sql
-- Outstanding gift-card liability (active cards still holding a balance)
SELECT ROUND(SUM(current_balance), 2) AS outstanding_balance,
       COUNT(*) AS active_cards
FROM gift_cards
WHERE status_code = :active            -- GIFTCARD_STATUS 'active'; reference.md
  AND current_balance > 0;
```

Because `customer_id` is nullable, a report of "gift-card balance by customer"
must decide how to treat unowned cards — either exclude NULL owners or bucket
them as "unassigned". Do not inner-join to `customers` and silently drop them
unless that is intended.

### Table: gift_card_transactions

- **Columns:** gc_txn_id, gift_card_id, order_id, txn_type_code, amount, txn_ts
- **Joined by:** PK `gc_txn_id`; FK `gift_card_id` → `gift_cards.gift_card_id`, `order_id` → `orders.order_id` (nullable)

| Column | Meaning |
|---|---|
| `gc_txn_id` | Primary key. |
| `gift_card_id` | The card this transaction hit. |
| `order_id` | **Nullable**, and NULL for every transaction in this dataset — the ledger is not linked to specific orders. |
| `txn_type_code` | Kind of transaction. Decodes against the **GIFTCARD_TXN_TYPE** code set. |
| `amount` | USD amount of the transaction. |
| `txn_ts` | ISO timestamp of the transaction. |

`txn_type_code` decodes against the **GIFTCARD_TXN_TYPE** code set with labels
**issue**, **redeem**, **reload**, and **refund**. An **issue** row records the
original loading of the card; a **redeem** row records the card being spent down
(reducing its balance); **reload** adds value; **refund** returns value to the
card. In this dataset `order_id` is NULL on every transaction — the ledger is not
linked to a specific order — so identify activity by `txn_type_code` and measure
it by the transaction `amount` and `txn_ts`. This is the audit trail behind
`current_balance`.

```sql
-- Gift-card redemption volume by month
SELECT substr(txn_ts, 1, 7) AS ym,
       ROUND(SUM(amount), 2) AS redeemed_amount,
       COUNT(*) AS redemptions
FROM gift_card_transactions
WHERE txn_type_code = :redeem          -- GIFTCARD_TXN_TYPE 'redeem'; reference.md
GROUP BY ym
ORDER BY ym;
```

When gift cards are used as tender they show up both here (as a redeem
transaction) and, at the order level, potentially as a `gift_card` payment method
in `payments`. Treat `gift_card_transactions` as the authoritative record of
card activity and balance movement; see `reference.md` for how
gift cards sit in the overall money picture.

An issue transaction and any reloads add value; redemptions and (rarely) refunds
against a card move it. Reconciling the ledger against the stored
`current_balance` is a data-quality check rather than a routine report, and it is
better handled as an approximate balance movement than an exact tie-out — see
`reference.md` for what to expect. The routine reporting
uses of these tables are (a) outstanding liability from active balances and (b)
redemption volume by transaction (the query above), both of which read cleanly.

Because `gift_card_transactions.order_id` is nullable — and in fact NULL on every
row here — do not join this ledger to `orders` or filter `order_id IS NOT NULL`
expecting order-linked rows; that returns nothing. Identify redemptions by
`txn_type_code = redeem` and measure them by `amount` and `txn_ts`.

---

## Worked combined analyses

A few end-to-end examples that stitch the tables above together correctly.

**Customer lifetime value (reporting-eligible orders).** One row per customer,
their order count and gross order value, with segment attached. Note the
internal_test exclusion on the order side and the aggregation at order-header
grain (summing `order_total` once per order, not per line):

```sql
SELECT c.customer_id, c.first_name, c.last_name,
       c.segment_code,                 -- CUSTOMER_SEGMENT; label via reference.md
       COUNT(o.order_id)              AS orders,
       ROUND(SUM(o.order_total), 2)   AS lifetime_value,
       MIN(o.order_date)              AS first_order,
       MAX(o.order_date)              AS last_order
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
  AND o.status <> :draft                        -- ORDER_STATUS 'draft'; drop WIP
GROUP BY c.customer_id
ORDER BY lifetime_value DESC;
```

**Products that sell but are no longer active.** Discontinued products
(`is_active = 0`) that still appear in historical order lines — a reason not to
filter `is_active` when measuring historical demand:

```sql
SELECT p.sku, p.name, SUM(ol.quantity) AS units_sold
FROM order_lines ol
JOIN products p ON p.sku = ol.sku
JOIN orders  o ON o.order_id = ol.order_id
WHERE p.is_active = 0
  AND o.priority_code <> :internal_test        -- see the Exclusions section of reference.md
GROUP BY p.sku, p.name
HAVING units_sold > 0
ORDER BY units_sold DESC;
```

**Order value with every discount broken out.** Combines line discounts (already
in `order_total`) and order-level promotions (not in `order_total`) at the order
grain, aggregating the promotion many-side in a subquery so it does not fan out:

```sql
SELECT o.order_id,
       o.order_total                                   AS net_of_line_discount,
       COALESCE(op.promo_discount, 0)                  AS promo_discount,
       ROUND(o.order_total - COALESCE(op.promo_discount, 0), 2) AS net_of_all_discounts
FROM orders o
LEFT JOIN (
    SELECT order_id, SUM(discount_amount) AS promo_discount
    FROM order_promotions GROUP BY order_id
) op ON op.order_id = o.order_id
WHERE o.priority_code <> :internal_test;       -- see the Exclusions section of reference.md
```

These patterns — aggregate each many-side to a single grain before joining, keep
the internal_test exclusion on orders, and bridge `sku` ⇄ `products` when
touching the product — recur throughout `reference.md`.

## Nullability and empty-set traps across the domain

Several columns here are nullable, and treating a NULL as a joinable value is a
recurring source of silently dropped rows. The ones to watch:

- **`orders.ship_to_address_id`** — NULL on some (typically draft) orders. Inner
  joins to `customer_addresses` drop those orders; use LEFT JOIN when counting
  all orders.
- **`orders.promised_date`** — NULL on draft orders. Any date arithmetic against
  it yields NULL; filter `promised_date IS NOT NULL` first.
- **`customers.email`, `customers.phone`** — nullable and non-unique; never a
  join or dedupe key.
- **`gift_cards.customer_id`** — NULL for unowned cards; inner-joining to
  `customers` silently drops them.
- **`gift_card_transactions.order_id`** — NULL for issue/reload rows; filter
  `IS NOT NULL` for order-linked activity only.
- **`payments.paid_date`** — NULL when funds were never captured (voided/failed
  payments).
- **`product_categories.parent_category_id`** — NULL marks a top-level category;
  it is the recursion/rollup terminator, not missing data.

Separately, the SKU ⇄ item_code mismatch produces the most dangerous empty set of
all: a wrong-vocabulary join returns zero rows with no error. When a
cross-domain query returns nothing, check the identifier bridge before assuming
the data is genuinely empty. Data-quality specifics and the exclusions that ride
on top of them are catalogued in `reference.md`.

## Putting the domain together

A few reminders that recur across every Order Management query:

1. **Exclude internal_test orders** from business reporting with
   `WHERE priority_code <> :internal_test`. They are ~3% of orders and are
   otherwise indistinguishable. See `reference.md`.
2. **Bridge SKU ⇄ item_code through `products`.** Order lines use `sku`;
   inventory/supplier tables use `item_code`. A direct join across the two
   returns zero rows silently. See `reference.md`.
3. **Every `status` / `status_code` column has its own code set.** ORDER_STATUS
   decodes `orders.status` and `order_status_history.status`; PAYMENT_STATUS
   decodes `payments.status_code`; GIFTCARD_STATUS decodes `gift_cards.status_code`.
   Never reuse a decode across tables. See `reference.md` and
   `reference.md`.
4. **`order_total` is the sum of line totals and is net of line discounts but
   not of order-level promotions.** For a promotion-net figure subtract
   `order_promotions.discount_amount`. See `reference.md` and
   `reference.md`.
5. **Prices come in three flavours:** current list (`products.unit_price`),
   historical list (`price_history`), and price paid (`order_lines.unit_price`).
   Use the right one for the question. See `reference.md`.

For the money side of orders — revenue recognition, refunds, promotions, gift
cards as tender, and how all of it composes — continue to
`reference.md`. For the physical journey of a fulfilled order —
picking, packing, shipping, tracking, and returns — see
`fulfillment_and_shipping.md`. For the canonical metric definitions used in
executive reporting, see `reference.md`.
