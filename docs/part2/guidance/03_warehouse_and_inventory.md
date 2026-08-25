# Warehouse & Inventory

This document is the topical reference for the Warehouse & Inventory domain: the physical facility hierarchy, the supplier network that feeds it, the on-hand inventory record and its movement ledger, and the operational documents (replenishment orders, receipts, stock transfers, adjustments, cycle counts) that keep the record honest. It covers per-column semantics, the business rules the team relies on, and worked SQLite for each area.

Reporting convention throughout: TODAY is `2024-12-31`. Money is in US dollars with two decimal places, weights are in kilograms, dates are `YYYY-MM-DD`, and timestamps are ISO-8601. All SQL is written for SQLite.

Coded columns (`status`, `*_code`) are decoded via the **Code Dictionary** in `04_reference_keys_codes_and_conventions.md`; this guide names the code set each column uses, and that dictionary gives the integer values.

## The single most important rule in this domain: products are identified by `item_code`

Every table in the Warehouse & Inventory domain identifies a product by an **`item_code` (INTEGER)** column, **not** by `sku`. The value stored in `item_code` is the product's primary key: `item_code = products.product_id`. So `item_code` 42 is the same product as `products.product_id` 42, which carries `sku` `SKU-00042`.

This matters because the Order Management and Fulfillment domains identify the same products by the **`sku` (TEXT)** string (`order_lines.sku`, `return_lines.sku`, `shipment_items.sku`). The two vocabularies describe identical products but are stored in different types and formats, so you cannot join them directly. A query that writes `order_lines.sku = inventory.item_code` returns **zero rows and raises no error** — SQLite silently compares a text SKU string against an integer and finds no matches. That is the most common quiet mistake in cross-domain work.

The `products` table is the only bridge between the two vocabularies. Convert with:

```sql
-- item_code (integer) -> sku (text)
SELECT 'SKU-' || printf('%05d', 42);           -- 'SKU-00042'

-- sku (text) -> item_code (integer)
SELECT CAST(SUBSTR('SKU-00042', 5) AS INTEGER); -- 42
```

Or, more robustly, join through `products` and let the primary key do the work:

```sql
-- On-hand quantity for a product, addressed by its SKU on the order side
SELECT p.sku, p.name, SUM(i.quantity_on_hand) AS on_hand
FROM products p
JOIN inventory i ON i.item_code = p.product_id
WHERE p.sku = 'SKU-00042'
GROUP BY p.sku, p.name;
```

Whenever a question phrases a product by SKU but the data you need lives on the inventory side (on-hand, cost, lots, transactions, transfers, counts), route through `products.product_id = item_code`. The full treatment of the two identifier vocabularies, the bridge table, and the conversion rules lives in **04_reference_keys_codes_and_conventions.md**; consult it before joining across domains.

A second cross-cutting rule affects almost every table below: coded columns (anything ending in `_code`, plus the `status` / `status_code` columns) never store a label directly. They store an integer that must be decoded through a named code set. This document names the code set for each column; the integer values live only in **04_reference_keys_codes_and_conventions.md**. Critically, the same column name means different things in different tables — a `status` of "received" on a replenishment order, a `status_code` of "received" on a stock transfer, and a `status_code` of "reconciled" on a cycle count are entirely separate concepts drawn from three separate code sets (`PO_STATUS`, `TRANSFER_STATUS`, `CYCLE_COUNT_STATUS`). Never carry a decode from one table to another. The lifecycle and status semantics are treated in full in **04_reference_keys_codes_and_conventions.md**.

---

## 1. The physical hierarchy: warehouses, zones, bins

Inventory physically lives somewhere. The three tables `warehouses`, `warehouse_zones`, and `bins` model a strict three-level containment hierarchy: a warehouse contains zones, and a zone contains bins. Every level carries its own `capacity_units` so you can reason about space at whatever granularity a question needs.

### 1.1 `warehouses`

The top of the hierarchy and the anchor for almost everything in this domain.

| Column | Meaning |
|---|---|
| `warehouse_id` | Primary key. Referenced as `warehouse_id` by inventory, lots, transactions, replenishment orders, receipts, transfers, adjustments, and cycle counts. |
| `code` | Short unique business code for the warehouse (e.g. a facility mnemonic). `UNIQUE`. |
| `name` | Human-readable warehouse name. |
| `city`, `state`, `country` | Physical location. |
| `capacity_units` | Total holding capacity of the warehouse, in abstract storage units. |
| `is_active` | Boolean flag (stored as an integer 0/1). Only active warehouses should appear in operational and capacity reporting unless a question is explicitly about decommissioned or planned sites. |

`is_active` is a plain 0/1 boolean, not a coded column — there is no code set to decode. Treat `1` as active, `0` as inactive:

```sql
-- Active warehouses and their raw capacity, largest first
SELECT warehouse_id, code, name, city, state, capacity_units
FROM warehouses
WHERE is_active = 1
ORDER BY capacity_units DESC;
```

Do not confuse `warehouses` with `facilities` (in the Fulfillment domain). Facilities model the transportation network (origin DCs, hubs, cross-docks, last-mile depots, ports) that shipments move through; warehouses are the stock-holding sites that inventory is counted in and shipped from. A shipment's `origin_warehouse_id` points at `warehouses`; a shipment leg's `from_facility_id` / `to_facility_id` point at `facilities`. They are separate tables with separate keys.

### 1.2 `warehouse_zones`

A zone is a functional area inside a warehouse.

| Column | Meaning |
|---|---|
| `zone_id` | Primary key. |
| `warehouse_id` | The parent warehouse (FK to `warehouses`). |
| `zone_code` | Short code for the zone within its warehouse. Not globally unique — scoped to the warehouse. |
| `zone_type_code` | The functional role of the zone. Coded column; decode through the **ZONE_TYPE** code set. Labels include receiving, storage, picking, shipping, and cold_storage. |
| `capacity_units` | Holding capacity of the zone. |

`zone_type_code` tells you what the zone is for. Receiving zones absorb inbound stock, storage zones hold reserve, picking zones front the pick faces, shipping zones stage outbound, and cold_storage handles temperature-controlled goods. Because a zone's role is a coded value, always name the code set (ZONE_TYPE) and let the reader resolve the integer through 04_reference_keys_codes_and_conventions.md rather than hard-coding a number inline.

```sql
-- Count zones of each functional type per warehouse.
-- Replace :cold_storage_code with the ZONE_TYPE value for cold_storage from 04_reference_keys_codes_and_conventions.md.
SELECT w.name AS warehouse, COUNT(*) AS cold_zones, SUM(z.capacity_units) AS cold_capacity
FROM warehouse_zones z
JOIN warehouses w ON w.warehouse_id = z.warehouse_id
WHERE z.zone_type_code = :cold_storage_code
GROUP BY w.name
ORDER BY cold_capacity DESC;
```

The named-parameter placeholder above is deliberate: this document names the code set, and the actual integer is looked up once, in the dictionary. That two-hop discipline (column → code-set name here → values in the **Code Dictionary**) keeps decodes consistent and prevents the wrong integer from leaking into a query.

### 1.3 `bins`

A bin is the finest storage location — a specific shelf, slot, or pallet position.

| Column | Meaning |
|---|---|
| `bin_id` | Primary key. Referenced by `pick_lines.bin_id` and `cycle_counts.bin_id`. |
| `warehouse_id` | Parent warehouse (FK). Denormalized onto the bin for convenience. |
| `zone_id` | Parent zone (FK to `warehouse_zones`). |
| `bin_code` | Short code for the bin within its zone/warehouse. |
| `capacity_units` | Holding capacity of the individual bin. |

Note that `bins` carries both `warehouse_id` and `zone_id`. The `zone_id` already implies a warehouse (through `warehouse_zones`), so the denormalized `warehouse_id` is a convenience for querying bins directly by warehouse without a second join. The two should always agree; if you need to be strict, join `bins` to `warehouse_zones` and confirm the warehouse matches.

```sql
-- Full physical hierarchy for one warehouse: zone type -> bin -> capacity
SELECT w.code AS wh, z.zone_code, z.zone_type_code, b.bin_code, b.capacity_units
FROM bins b
JOIN warehouse_zones z ON z.zone_id = b.zone_id
JOIN warehouses w      ON w.warehouse_id = b.warehouse_id
WHERE w.code = 'DC-EAST'
ORDER BY z.zone_code, b.bin_code;
```

A useful capacity-reconciliation check is to compare a warehouse's declared `capacity_units` against the sum of its zone capacities, and each zone's capacity against the sum of its bins. These do not have to tie out exactly in a real operation (aisles, docks, and staging consume space that is not itself a bin), but large divergences are worth flagging:

```sql
-- Declared warehouse capacity vs the sum of its zone capacities
SELECT w.name,
       w.capacity_units                AS warehouse_capacity,
       COALESCE(SUM(z.capacity_units),0) AS zone_capacity_total
FROM warehouses w
LEFT JOIN warehouse_zones z ON z.warehouse_id = w.warehouse_id
GROUP BY w.warehouse_id, w.name, w.capacity_units
ORDER BY warehouse_capacity DESC;
```

Bins connect back to operations in two places: `pick_lines.bin_id` records the location a picker pulled from (see the Fulfillment domain), and `cycle_counts.bin_id` records the location that was counted. Both use `item_code` to identify the product, consistent with the rest of this domain.

---

## 2. The supplier network

Before stock can be received it has to be sourced. Three tables model the vendor side: `suppliers` (the vendor master), `supplier_products` (the catalog of what each supplier sells us, and at what cost and lead time), and `supplier_contacts` (the people).

### 2.1 `suppliers`

| Column | Meaning |
|---|---|
| `supplier_id` | Primary key. Referenced by `supplier_products`, `supplier_contacts`, `replenishment_orders`, and `supplier_invoices`. |
| `name` | Supplier / vendor name. |
| `country` | Supplier's country. |
| `status_code` | Relationship status with the vendor. Coded column; decode through the **SUPPLIER_STATUS** code set. Labels include active, on_hold, terminated, and pending_approval. |
| `default_lead_time_days` | The vendor's headline lead time in days, used as a fallback when a specific item does not carry its own lead time. |

`suppliers.status_code` uses the SUPPLIER_STATUS code set and nothing else. An "active" supplier here has no relationship to an "active" gift card, an "active" warehouse flag, or any order status — the SUPPLIER_STATUS "active" label is its own value in its own set. Only source new purchase orders from suppliers whose status decodes to active; on_hold and terminated vendors should be excluded from new sourcing, and pending_approval vendors are not yet cleared to buy from.

```sql
-- Suppliers eligible for new POs (status decodes to active in SUPPLIER_STATUS).
-- Replace :supplier_active with the SUPPLIER_STATUS value for active from 04_reference_keys_codes_and_conventions.md.
SELECT supplier_id, name, country, default_lead_time_days
FROM suppliers
WHERE status_code = :supplier_active
ORDER BY name;
```

`default_lead_time_days` is the supplier-level default. When you need the lead time for a specific product/supplier pairing, prefer the item-level `supplier_products.lead_time_days` and fall back to `default_lead_time_days` only when the item-level value is missing.

### 2.2 `supplier_products`

This is the sourcing catalog: one row per (supplier, product) pairing the supplier can fulfill. It is also where the **preferred supplier** for an item is recorded.

| Column | Meaning |
|---|---|
| `supplier_product_id` | Primary key. |
| `supplier_id` | The supplier (FK). |
| `item_code` | The product, as an INTEGER equal to `products.product_id`. This is the inventory-side identifier — join to `products.product_id`, never to a SKU string. |
| `supplier_sku` | The supplier's own catalog number for the product. This is the vendor's SKU, a free-text vendor reference — it is NOT our `products.sku` and must not be joined to `order_lines.sku` or used as our SKU. |
| `unit_cost` | The supplier's cost to us per unit, in dollars. This is a purchasing cost, distinct from `products.unit_price` (the customer-facing sell price). |
| `lead_time_days` | Item-specific lead time from this supplier, in days. |
| `is_preferred` | Boolean (0/1). Marks the preferred sourcing relationship for the item. |

Two identifiers on this table are easy to confuse. `item_code` is *our* product key (an integer, equal to `product_id`); `supplier_sku` is the *vendor's* free-text part number. Only `item_code` bridges to the rest of the warehouse — always join on `item_code = products.product_id`.

`is_preferred` designates the supplier we would normally buy a given item from. In a well-run master there is exactly one preferred supplier per item, but you should not assume that blindly — validate it:

```sql
-- Preferred supplier and its cost/lead time for each product
SELECT p.product_id AS item_code, p.sku, p.name,
       s.name AS preferred_supplier, sp.unit_cost, sp.lead_time_days
FROM supplier_products sp
JOIN products  p ON p.product_id = sp.item_code
JOIN suppliers s ON s.supplier_id = sp.supplier_id
WHERE sp.is_preferred = 1
ORDER BY p.product_id;
```

```sql
-- Data-quality check: items with more than one preferred supplier (should be none)
SELECT item_code, COUNT(*) AS preferred_rows
FROM supplier_products
WHERE is_preferred = 1
GROUP BY item_code
HAVING COUNT(*) > 1;
```

To answer "who is the cheapest supplier for this item, and are we buying from them?", compare `unit_cost` across suppliers for the same `item_code`:

```sql
-- Lowest-cost supplier per item vs the preferred one
SELECT sp.item_code,
       MIN(sp.unit_cost) AS lowest_cost,
       MAX(CASE WHEN sp.is_preferred = 1 THEN sp.unit_cost END) AS preferred_cost
FROM supplier_products sp
GROUP BY sp.item_code
HAVING preferred_cost > lowest_cost;   -- preferred is not the cheapest
```

The effective lead time for planning a purchase of an item from a supplier is the item-level value with a supplier-level fallback:

```sql
-- Effective lead time = item-level if present, else supplier default
SELECT sp.item_code, s.name AS supplier,
       COALESCE(sp.lead_time_days, s.default_lead_time_days) AS effective_lead_days
FROM supplier_products sp
JOIN suppliers s ON s.supplier_id = sp.supplier_id
WHERE sp.is_preferred = 1;
```

### 2.3 `supplier_contacts`

The people at each supplier.

| Column | Meaning |
|---|---|
| `contact_id` | Primary key. |
| `supplier_id` | The supplier (FK). |
| `name`, `email`, `phone` | Contact details. `email` and `phone` may be null. |
| `role` | The contact's role at the supplier (e.g. account manager, logistics, accounts receivable). This is a free-text label, NOT a coded column — there is no code set for it, so filter it as text. |

Because `role` is free text rather than a coded value, treat it as a string and be tolerant of formatting when filtering:

```sql
-- Primary billing/AR contacts across suppliers
SELECT s.name AS supplier, c.name AS contact, c.email, c.role
FROM supplier_contacts c
JOIN suppliers s ON s.supplier_id = c.supplier_id
WHERE LOWER(c.role) LIKE '%account%'
ORDER BY s.name;
```

Supplier invoices tie the vendor relationship to money. They are summarized under section 8 below and covered in full in **04_reference_keys_codes_and_conventions.md**.

---

## 3. Inventory: the on-hand record

The `inventory` table is the current stock position — the authoritative snapshot of how much of each product sits in each warehouse right now, together with the reorder parameters that drive replenishment.

### 3.1 `inventory` columns and the one-row-per-product-per-warehouse rule

| Column | Meaning |
|---|---|
| `inventory_id` | Primary key. |
| `warehouse_id` | The warehouse this stock position is in (FK). |
| `item_code` | The product (INTEGER = `products.product_id`). |
| `quantity_on_hand` | Physical units currently in the warehouse. |
| `quantity_allocated` | Units already committed to open orders / picks and therefore not free to promise. |
| `reorder_point` | The on-hand threshold at or below which the item should be reordered. |
| `reorder_qty` | The quantity to order when replenishing (see 3.4). |
| `last_counted_date` | The date this position was last physically verified (a cycle count or full count). |

The table carries `UNIQUE (warehouse_id, item_code)`: **exactly one row per product per warehouse.** This is load-bearing. It means a product's position in a given warehouse is a single row you can update in place, and it means that summing `quantity_on_hand` for an item across warehouses gives the network-wide on-hand without any risk of double counting. It also means a product that has never been stocked in a warehouse simply has no row there (not a zero row) — so "warehouses where item X is out of stock" is different from "warehouses with no inventory record for item X," and network rollups should decide explicitly whether a missing row counts as zero.

```sql
-- Network on-hand for a product across all warehouses (one row per warehouse guaranteed)
SELECT i.warehouse_id, w.name, i.quantity_on_hand, i.quantity_allocated
FROM inventory i
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
WHERE i.item_code = 42
ORDER BY w.name;
```

### 3.2 Available quantity

The single most important derived measure in this domain is **available quantity**, defined as:

```
available = quantity_on_hand − quantity_allocated
```

On-hand is what physically exists; allocated is what is already spoken for. Available is what is actually free to promise to a new order. Reporting on "stock we can sell/ship" should use available, not on-hand.

```sql
-- Available (free-to-promise) quantity by product and warehouse
SELECT i.item_code, w.name AS warehouse,
       i.quantity_on_hand,
       i.quantity_allocated,
       i.quantity_on_hand - i.quantity_allocated AS available
FROM inventory i
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
ORDER BY available ASC;
```

Available can be zero or, in a data-quality-defective row, negative (more allocated than on hand). Negative available is a red flag worth surfacing:

```sql
-- Over-allocated positions (allocated exceeds on-hand)
SELECT item_code, warehouse_id, quantity_on_hand, quantity_allocated,
       quantity_on_hand - quantity_allocated AS available
FROM inventory
WHERE quantity_allocated > quantity_on_hand;
```

The formal definition of available quantity, and the standard aggregations built on it, are recorded in **04_reference_keys_codes_and_conventions.md**; use that as the canonical wording.

Because of the `UNIQUE (warehouse_id, item_code)` rule, a network-wide availability rollup is a clean per-item sum with no double counting. This is the query behind "how many units of this product can we sell across the whole network right now":

```sql
-- Network availability by product, with the number of stocking warehouses
SELECT i.item_code, p.sku, p.name,
       COUNT(*)                                        AS stocking_warehouses,
       SUM(i.quantity_on_hand)                         AS network_on_hand,
       SUM(i.quantity_allocated)                       AS network_allocated,
       SUM(i.quantity_on_hand - i.quantity_allocated)  AS network_available
FROM inventory i
JOIN products p ON p.product_id = i.item_code
GROUP BY i.item_code, p.sku, p.name
ORDER BY network_available ASC;
```

A related planning question — "which warehouse should fill this order" — sorts a single item's positions by available descending, so the site with the most free-to-promise stock surfaces first:

```sql
-- Best warehouse to source a product from, by available quantity
SELECT i.warehouse_id, w.name,
       i.quantity_on_hand - i.quantity_allocated AS available
FROM inventory i
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
WHERE i.item_code = 42 AND w.is_active = 1
ORDER BY available DESC;
```

### 3.3 Below reorder point

An item is **below reorder point** in a warehouse when:

```
quantity_on_hand < reorder_point
```

Note the definition is stated on **`quantity_on_hand`**, not on available. This is deliberate and is the standard convention: the reorder trigger looks at physical stock. Do not silently substitute `available < reorder_point` — that is a different (stricter) question, and while some planners track it, the canonical "below reorder point" measure is the on-hand comparison. The comparison is strict (`<`), so a position exactly at its reorder point is not yet below it.

```sql
-- Items below reorder point, with the recommended reorder quantity
SELECT i.item_code, p.sku, w.name AS warehouse,
       i.quantity_on_hand, i.reorder_point, i.reorder_qty
FROM inventory i
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
JOIN products   p ON p.product_id  = i.item_code
WHERE i.quantity_on_hand < i.reorder_point
ORDER BY (i.reorder_point - i.quantity_on_hand) DESC;
```

The exact definition (`quantity_on_hand < reorder_point`) is also recorded in **04_reference_keys_codes_and_conventions.md**. When a question asks for "items that need reordering" or "stockouts risk," this is the measure to reach for.

### 3.4 `reorder_qty` — how much to reorder

`reorder_point` answers *when* to reorder; `reorder_qty` answers *how much*. When a position drops below its reorder point, the standard replenishment action is to raise a purchase for `reorder_qty` units (typically from the item's preferred supplier — see section 2.2). It is the fixed order quantity, not a target level: replenishment raises `reorder_qty` units, it does not "top up to `reorder_qty`."

A first-pass replenishment worklist therefore joins the below-reorder positions to the preferred supplier and the item's cost:

```sql
-- Replenishment worklist: what to buy, how much, from whom, at what cost
SELECT i.warehouse_id, w.name AS warehouse, i.item_code, p.name AS product,
       i.quantity_on_hand, i.reorder_point, i.reorder_qty,
       s.name AS preferred_supplier,
       sp.unit_cost,
       i.reorder_qty * sp.unit_cost AS estimated_po_cost
FROM inventory i
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
JOIN products   p ON p.product_id  = i.item_code
LEFT JOIN supplier_products sp ON sp.item_code = i.item_code AND sp.is_preferred = 1
LEFT JOIN suppliers s          ON s.supplier_id = sp.supplier_id
WHERE i.quantity_on_hand < i.reorder_point
ORDER BY estimated_po_cost DESC;
```

The `LEFT JOIN` to the preferred supplier is intentional: an item can be below reorder point yet have no preferred supplier on file, and that gap is itself worth surfacing rather than dropping the row with an inner join.

### 3.5 `last_counted_date` and count staleness

`last_counted_date` records when a position was last physically verified. It is the audit anchor for inventory accuracy: positions that have not been counted in a long time carry more risk that the system quantity has drifted from reality. Against TODAY = `2024-12-31`, staleness is a simple date arithmetic:

```sql
-- Positions not counted in over 180 days (stale as of 2024-12-31)
SELECT item_code, warehouse_id, quantity_on_hand, last_counted_date,
       CAST(julianday('2024-12-31') - julianday(last_counted_date) AS INTEGER) AS days_since_count
FROM inventory
WHERE julianday('2024-12-31') - julianday(last_counted_date) > 180
ORDER BY days_since_count DESC;
```

`last_counted_date` is updated by the cycle-count process (section 11); the two should be read together when auditing accuracy.

### 3.6 Days of cover from the movement ledger

On-hand alone does not tell you whether a position is healthy — the same 100 units is months of cover for a slow mover and days of cover for a fast one. To turn on-hand into a coverage horizon, pull a consumption rate from the shipment (outbound) movements in the ledger and divide. Shipment movements carry negative deltas, so the units consumed over a window is the negated sum of the shipment-typed deltas:

```sql
-- Days of cover: on-hand divided by average daily outbound consumption over the last 90 days.
-- Replace :txn_shipment with the INV_TXN_TYPE value for shipment from 04_reference_keys_codes_and_conventions.md.
WITH consumption AS (
    SELECT warehouse_id, item_code,
           SUM(-quantity_delta) AS units_out_90d
    FROM inventory_transactions
    WHERE txn_type_code = :txn_shipment
      AND txn_ts >= date('2024-12-31', '-90 days')
    GROUP BY warehouse_id, item_code
)
SELECT i.warehouse_id, i.item_code, p.name AS product,
       i.quantity_on_hand,
       c.units_out_90d,
       ROUND(c.units_out_90d / 90.0, 2) AS avg_daily_out,
       CASE WHEN c.units_out_90d > 0
            THEN ROUND(i.quantity_on_hand / (c.units_out_90d / 90.0), 1)
            END AS days_of_cover
FROM inventory i
JOIN products p    ON p.product_id = i.item_code
JOIN consumption c ON c.warehouse_id = i.warehouse_id AND c.item_code = i.item_code
ORDER BY days_of_cover ASC;
```

Positions with a very low days-of-cover figure are stockout risks even if they sit above their reorder point; positions with no consumption at all (no rows in the CTE) are candidates for slow-moving or dead stock review. The join is deliberately inner here so the coverage list contains only items that actually moved; switch to a `LEFT JOIN` and treat a null `units_out_90d` as zero movement when you want to surface the non-movers instead.

---

## 4. Inventory lots and expiry tracking

Where `inventory` is a single netted position, `inventory_lots` breaks the same stock down into receiving lots so that batch and expiry can be tracked.

| Column | Meaning |
|---|---|
| `lot_id` | Primary key. |
| `warehouse_id` | Warehouse holding the lot (FK). |
| `item_code` | The product (INTEGER = `products.product_id`). |
| `lot_number` | The lot / batch identifier as received. |
| `quantity` | Units remaining in this lot. |
| `received_date` | When the lot was received. |
| `expiry_date` | When the lot expires. **May be null** — non-perishable products carry no expiry. |

A single (warehouse, item_code) position can be composed of several lots received on different dates with different expiries. Summing lot quantities gives a lot-derived on-hand that should broadly agree with `inventory.quantity_on_hand` for the same warehouse and item, though the netted `inventory` figure is the authoritative on-hand.

`expiry_date` being nullable is meaningful: a null expiry means the product does not expire, not that the expiry is unknown. So expiry queries must guard for null explicitly rather than assuming every lot has a date.

```sql
-- Lots expiring within 90 days of TODAY (only lots that actually carry an expiry)
SELECT l.warehouse_id, w.name AS warehouse, l.item_code, p.name AS product,
       l.lot_number, l.quantity, l.received_date, l.expiry_date
FROM inventory_lots l
JOIN warehouses w ON w.warehouse_id = l.warehouse_id
JOIN products   p ON p.product_id  = l.item_code
WHERE l.expiry_date IS NOT NULL
  AND l.expiry_date <= date('2024-12-31', '+90 days')
  AND l.expiry_date >= '2024-12-31'
ORDER BY l.expiry_date;
```

```sql
-- Already-expired stock still showing quantity on hand
SELECT l.item_code, p.name, l.warehouse_id, l.lot_number, l.quantity, l.expiry_date
FROM inventory_lots l
JOIN products p ON p.product_id = l.item_code
WHERE l.expiry_date IS NOT NULL
  AND l.expiry_date < '2024-12-31'
  AND l.quantity > 0
ORDER BY l.expiry_date;
```

For age-based analysis (FIFO discipline, slow-moving batches), lean on `received_date`:

```sql
-- Oldest lot on hand per product/warehouse
SELECT item_code, warehouse_id, MIN(received_date) AS oldest_lot_received
FROM inventory_lots
WHERE quantity > 0
GROUP BY item_code, warehouse_id;
```

---

## 5. The inventory transaction ledger

`inventory_transactions` is the movement ledger. Where `inventory` holds the current balance, `inventory_transactions` records every event that changed it. It is the append-only history that reconciles on-hand movements, and it is the primary tool for auditing how a position got to where it is.

| Column | Meaning |
|---|---|
| `txn_id` | Primary key. |
| `warehouse_id` | Warehouse where the movement occurred (FK). |
| `item_code` | The product (INTEGER = `products.product_id`). |
| `txn_type_code` | The kind of movement. Coded column; decode through the **INV_TXN_TYPE** code set. Labels: receipt, shipment, transfer_out, transfer_in, adjustment, return_restock. |
| `quantity_delta` | The signed change in on-hand this movement caused (see the sign convention below). |
| `reference_type` | A text tag naming the kind of source document that drove the movement (e.g. the receipt, shipment, transfer, or adjustment table). |
| `reference_id` | The primary key of that source document. May be null when no single document applies. |
| `txn_ts` | Timestamp of the movement (ISO-8601). |

### 5.1 The sign convention

`quantity_delta` is **signed**: a **positive** delta adds to on-hand, a **negative** delta removes from it. The transaction *type* tells you the business reason; the *sign* tells you the direction. In a consistent ledger the two agree — inbound types (receipt, transfer_in, return_restock) carry positive deltas and outbound types (shipment, transfer_out) carry negative deltas — but the arithmetic that reconciles the balance depends only on the sign, so you sum `quantity_delta` directly and never re-derive direction from the type.

```sql
-- Net movement for a product in a warehouse: just sum the signed deltas
SELECT item_code, warehouse_id, SUM(quantity_delta) AS net_change
FROM inventory_transactions
WHERE item_code = 42 AND warehouse_id = 1
GROUP BY item_code, warehouse_id;
```

Because inbound and outbound already carry the correct sign, you never write `SUM(ABS(...))` or add a `CASE` to flip signs by type for a net-change calculation. If you want gross inbound and gross outbound separately, split on the sign:

```sql
-- Gross received vs gross shipped/removed from the ledger, by product
SELECT item_code,
       SUM(CASE WHEN quantity_delta > 0 THEN quantity_delta ELSE 0 END) AS gross_in,
       SUM(CASE WHEN quantity_delta < 0 THEN -quantity_delta ELSE 0 END) AS gross_out,
       SUM(quantity_delta) AS net
FROM inventory_transactions
GROUP BY item_code;
```

### 5.2 How the ledger reconciles on-hand

Receipts, shipments, transfers, and adjustments all post to this ledger. That means the cumulative sum of `quantity_delta` for a (warehouse, item_code) pair is the ledger's account of on-hand, and it should reconcile against `inventory.quantity_on_hand`. Reconciliation is the standard integrity check:

```sql
-- Reconcile ledger balance against the on-hand snapshot; surface any drift
SELECT i.warehouse_id, i.item_code,
       i.quantity_on_hand,
       COALESCE(t.ledger_balance, 0) AS ledger_balance,
       i.quantity_on_hand - COALESCE(t.ledger_balance, 0) AS drift
FROM inventory i
LEFT JOIN (
    SELECT warehouse_id, item_code, SUM(quantity_delta) AS ledger_balance
    FROM inventory_transactions
    GROUP BY warehouse_id, item_code
) t ON t.warehouse_id = i.warehouse_id AND t.item_code = i.item_code
WHERE i.quantity_on_hand <> COALESCE(t.ledger_balance, 0)
ORDER BY ABS(i.quantity_on_hand - COALESCE(t.ledger_balance, 0)) DESC;
```

### 5.3 Following the reference back to the source document

`reference_type` + `reference_id` form a soft (polymorphic) foreign key to whatever document drove the movement. `reference_type` names the source table and `reference_id` holds its primary key. Because it is a soft link, you cannot enforce it with a schema FK and you must branch on `reference_type` when joining back:

```sql
-- Ledger movements that came from receipts, joined back to the receipt header
SELECT t.txn_id, t.item_code, t.quantity_delta, t.txn_ts,
       r.received_ts, r.reference AS receipt_reference
FROM inventory_transactions t
JOIN receipts r ON r.receipt_id = t.reference_id
WHERE t.reference_type = 'receipt';
```

Movements typed as receipt should trace to receipt/replenishment activity, shipment movements to outbound fulfillment, transfer_out/transfer_in to stock transfers, and adjustment/return_restock to adjustments and return processing respectively. The ledger is the connective tissue that lets you tie a balance change to the operational document that caused it.

### 5.4 Throughput and movement mix

Because the ledger stamps every movement with a type and timestamp, it is the natural place to measure warehouse throughput and the mix of what is driving stock changes. A monthly movement profile by type answers "what is this warehouse actually doing":

```sql
-- Monthly movement volume by type for one warehouse in 2024.
-- Use the INV_TXN_TYPE code set in 04_reference_keys_codes_and_conventions.md to label txn_type_code.
SELECT strftime('%Y-%m', txn_ts) AS month,
       txn_type_code,
       COUNT(*)                  AS movements,
       SUM(ABS(quantity_delta))  AS units_moved
FROM inventory_transactions
WHERE warehouse_id = 1
  AND txn_ts >= '2024-01-01' AND txn_ts < '2025-01-01'
GROUP BY month, txn_type_code
ORDER BY month, txn_type_code;
```

Note the use of `ABS(quantity_delta)` here: throughput is about how much stock moved regardless of direction, which is the one place absolute value is appropriate. For a *net* balance change (section 5.1) you sum the signed delta instead. Mixing the two up — summing signed deltas when you meant throughput, or summing absolute values when you meant net change — is the most common arithmetic error against this table.

---

## 6. Replenishment orders (purchase orders)

Replenishment orders are the inbound purchase orders raised on suppliers to restock warehouses. They come in two tables: `replenishment_orders` (the header) and `replenishment_lines` (the line items).

### 6.1 `replenishment_orders`

| Column | Meaning |
|---|---|
| `repl_id` | Primary key. Referenced by `replenishment_lines`, `receipts`, and `supplier_invoices`. |
| `supplier_id` | The supplier the PO is placed with (FK). |
| `warehouse_id` | The destination warehouse (FK). |
| `status` | The PO's lifecycle state. Coded column; decode through the **PO_STATUS** code set. Labels: draft, open, partial, received, cancelled. |
| `order_date` | When the PO was placed. |
| `expected_date` | The expected delivery date. |
| `received_date` | When the PO was fully received. Null until then. |
| `total_cost` | The PO's total value in dollars. |

`replenishment_orders.status` is decoded with **PO_STATUS and only PO_STATUS**. The PO_STATUS "received" label is the terminal state of a purchase order — it is a completely different value from the TRANSFER_STATUS "received" used on stock transfers and unrelated to the CYCLE_COUNT_STATUS "reconciled" terminal on cycle counts. Do not reuse a decode from one of those tables here. The full lifecycle for each of these is laid out in **04_reference_keys_codes_and_conventions.md**.

- **Open POs** are those still awaiting stock — the draft/open/partial states (i.e. anything that has not reached received or cancelled).
- **Received POs** are complete (status decodes to received); `received_date` should be populated.
- **Partial** means some but not all ordered quantity has been received — a partial receipt (see 6.3).

```sql
-- Open purchase orders (not yet fully received, not cancelled), aged against TODAY.
-- Replace the placeholders with the PO_STATUS values from 04_reference_keys_codes_and_conventions.md.
SELECT po.repl_id, s.name AS supplier, w.name AS warehouse,
       po.order_date, po.expected_date, po.total_cost,
       CAST(julianday('2024-12-31') - julianday(po.expected_date) AS INTEGER) AS days_past_expected
FROM replenishment_orders po
JOIN suppliers  s ON s.supplier_id = po.supplier_id
JOIN warehouses w ON w.warehouse_id = po.warehouse_id
WHERE po.status IN (:po_draft, :po_open, :po_partial)
ORDER BY days_past_expected DESC;
```

```sql
-- Overdue POs: expected before TODAY and still not received
SELECT repl_id, supplier_id, warehouse_id, expected_date, total_cost
FROM replenishment_orders
WHERE status IN (:po_open, :po_partial)
  AND expected_date < '2024-12-31';
```

### 6.2 `replenishment_lines`

| Column | Meaning |
|---|---|
| `repl_line_id` | Primary key. |
| `repl_id` | Parent PO (FK). |
| `item_code` | The product ordered (INTEGER = `products.product_id`). |
| `qty_ordered` | Units ordered on this line. |
| `qty_received` | Units received against this line so far. |
| `unit_cost` | The agreed cost per unit on this PO line, in dollars. This is the price locked at order time and may differ from the current `supplier_products.unit_cost`. |

The line-level `qty_ordered` vs `qty_received` pair is where partial receipts become visible. Rolling the lines up gives PO-level fulfillment:

```sql
-- Line-level fill against a PO
SELECT rl.repl_id, rl.item_code, p.name AS product,
       rl.qty_ordered, rl.qty_received,
       rl.qty_ordered - rl.qty_received AS qty_outstanding,
       rl.unit_cost,
       rl.qty_received * rl.unit_cost AS received_value
FROM replenishment_lines rl
JOIN products p ON p.product_id = rl.item_code
WHERE rl.repl_id = 100
ORDER BY rl.item_code;
```

### 6.3 Open vs received, and partial receipts

There are two complementary ways to judge whether a PO is complete: its header `status`, and the line-level roll-up of `qty_received` against `qty_ordered`. In clean data they agree — a header decoded as received has every line fully received, and a header decoded as partial has at least one line short. Cross-checking them is a good integrity test:

```sql
-- POs whose header says fully received but whose lines are still short (data check).
-- Replace :po_received with the PO_STATUS value for received.
SELECT po.repl_id,
       SUM(rl.qty_ordered)  AS total_ordered,
       SUM(rl.qty_received) AS total_received
FROM replenishment_orders po
JOIN replenishment_lines rl ON rl.repl_id = po.repl_id
WHERE po.status = :po_received
GROUP BY po.repl_id
HAVING SUM(rl.qty_received) < SUM(rl.qty_ordered);
```

```sql
-- Outstanding units on the books (open commitments to receive)
SELECT SUM(rl.qty_ordered - rl.qty_received) AS units_outstanding
FROM replenishment_orders po
JOIN replenishment_lines rl ON rl.repl_id = po.repl_id
WHERE po.status IN (:po_open, :po_partial);
```

A received PO posts inbound movements to the inventory ledger (receipt-typed transactions with positive deltas) and generates receipt records (section 7). A supplier invoice is billed against the PO (section 8, detail in the **Pricing, Costs & Billing** section of `04_reference_keys_codes_and_conventions.md`).

### 6.4 Supplier lead-time and on-time performance

The PO header carries `order_date`, `expected_date`, and `received_date`, which together let you score how a supplier actually performs against the lead time it promised. Actual lead time is `received_date − order_date`; on-time delivery is `received_date <= expected_date`. Only fully received POs (those with a populated `received_date`) can be scored:

```sql
-- Supplier delivery performance on received POs: promised vs actual lead time, on-time rate.
-- Replace :po_received with the PO_STATUS value for received from 04_reference_keys_codes_and_conventions.md.
SELECT s.name AS supplier,
       COUNT(*) AS pos_received,
       ROUND(AVG(julianday(po.received_date) - julianday(po.order_date)), 1) AS avg_actual_lead_days,
       s.default_lead_time_days AS promised_default_lead,
       ROUND(100.0 * SUM(CASE WHEN po.received_date <= po.expected_date THEN 1 ELSE 0 END)
             / COUNT(*), 1) AS on_time_pct
FROM replenishment_orders po
JOIN suppliers s ON s.supplier_id = po.supplier_id
WHERE po.status = :po_received
  AND po.received_date IS NOT NULL
GROUP BY s.supplier_id, s.name, s.default_lead_time_days
ORDER BY on_time_pct ASC;
```

A supplier whose average actual lead time runs well beyond its `default_lead_time_days`, or whose on-time rate is low, is a candidate for a lead-time correction in `supplier_products` or a sourcing review. Note that on-time is measured against `expected_date` (the date promised on that specific PO), while the lead-time benchmark comes from the supplier/item master — the two can legitimately differ when a PO was placed with an unusual promised date.

---

## 7. Receipts

When stock physically arrives against a replenishment order, it is booked as a receipt. `receipts` is the receiving event header; `receipt_lines` records what and how much, and in what condition.

### 7.1 `receipts`

| Column | Meaning |
|---|---|
| `receipt_id` | Primary key. Referenced by `receipt_lines`. |
| `repl_id` | The replenishment order this receipt is against (FK). |
| `warehouse_id` | The receiving warehouse (FK). |
| `received_ts` | Timestamp the goods were received (ISO-8601). |
| `reference` | A free-text receiving reference (packing slip / ASN number). |

A single PO can generate more than one receipt over time (that is exactly how partial receipts accumulate): each delivery against the PO is its own `receipts` row, and their `receipt_lines` sum up to the PO's `qty_received`.

```sql
-- Receiving history for a PO
SELECT r.receipt_id, r.received_ts, r.reference,
       SUM(rlx.qty_received) AS units_this_receipt
FROM receipts r
JOIN receipt_lines rlx ON rlx.receipt_id = r.receipt_id
WHERE r.repl_id = 100
GROUP BY r.receipt_id, r.received_ts, r.reference
ORDER BY r.received_ts;
```

### 7.2 `receipt_lines`

| Column | Meaning |
|---|---|
| `receipt_line_id` | Primary key. |
| `receipt_id` | Parent receipt (FK). |
| `item_code` | The product received (INTEGER = `products.product_id`). |
| `qty_received` | Units received on this line. |
| `condition_code` | The condition the goods arrived in. Coded column; decode through the **ITEM_CONDITION** code set. Labels: new, opened, damaged, defective. |

`receipt_lines.condition_code` uses the **ITEM_CONDITION** code set — the same code set used by `return_lines.condition_code` on the returns side, because it describes the physical state of goods in both contexts. Only goods received in sellable condition (the new label) should flow to available stock; damaged/defective receipts are typically quarantined and may drive a supplier claim.

```sql
-- Damaged/defective inbound by supplier (which vendors ship us bad goods?).
-- Replace the placeholders with ITEM_CONDITION values from 04_reference_keys_codes_and_conventions.md.
SELECT s.name AS supplier,
       SUM(CASE WHEN rlx.condition_code IN (:cond_damaged, :cond_defective)
                THEN rlx.qty_received ELSE 0 END) AS bad_units,
       SUM(rlx.qty_received) AS total_units
FROM receipt_lines rlx
JOIN receipts r            ON r.receipt_id = rlx.receipt_id
JOIN replenishment_orders po ON po.repl_id = r.repl_id
JOIN suppliers s           ON s.supplier_id = po.supplier_id
GROUP BY s.name
ORDER BY bad_units DESC;
```

Reconciling receipt lines back to PO lines confirms that received-into-warehouse equals ordered-and-billed, and any gap is a receiving discrepancy:

```sql
-- Receipt totals vs PO line orders for one PO
SELECT rl.item_code,
       rl.qty_ordered,
       COALESCE(SUM(rlx.qty_received), 0) AS receipts_booked
FROM replenishment_lines rl
LEFT JOIN receipts r        ON r.repl_id = rl.repl_id
LEFT JOIN receipt_lines rlx ON rlx.receipt_id = r.receipt_id AND rlx.item_code = rl.item_code
WHERE rl.repl_id = 100
GROUP BY rl.item_code, rl.qty_ordered;
```

---

## 8. Supplier invoices (topical)

`supplier_invoices` is the accounts-payable side of the supplier relationship — the vendor's bill for goods delivered against a replenishment order.

| Column | Meaning |
|---|---|
| `supplier_invoice_id` | Primary key. |
| `supplier_id` | The billing supplier (FK). |
| `repl_id` | The replenishment order billed. **May be null** (some invoices are not tied to a single PO). |
| `invoice_number` | Vendor invoice number. `UNIQUE`. |
| `amount` | Invoice amount in dollars. |
| `status_code` | The invoice's AP lifecycle state. Coded column; decode through the **INVOICE_STATUS** code set. Labels: draft, submitted, approved, paid, disputed. |
| `invoice_date`, `due_date`, `paid_date` | Billing dates; `paid_date` is null until paid. |

`supplier_invoices.status_code` uses the **INVOICE_STATUS** code set — the same code set that decodes `carrier_invoices.status_code` on the fulfillment side, since both are AP invoices. It is unrelated to PO_STATUS, SUPPLIER_STATUS, or any other status column. A quick example at the topical level:

```sql
-- Unpaid, approved supplier invoices past due as of TODAY.
-- Replace the placeholders with INVOICE_STATUS values from 04_reference_keys_codes_and_conventions.md.
SELECT si.invoice_number, s.name AS supplier, si.amount, si.due_date
FROM supplier_invoices si
JOIN suppliers s ON s.supplier_id = si.supplier_id
WHERE si.status_code = :invoice_approved
  AND si.due_date < '2024-12-31'
  AND si.paid_date IS NULL
ORDER BY si.due_date;
```

Full invoice semantics — the status lifecycle, matching invoices to receipts, aging buckets, and how supplier invoices sit alongside carrier invoices in the cost picture — are documented in **04_reference_keys_codes_and_conventions.md**. Treat that file as authoritative for anything billing-related; this section only situates the table within the inventory flow.

---

## 9. Stock transfers

Stock transfers move inventory between warehouses within the network (as opposed to buying it from a supplier). The header is `stock_transfers`; the detail is `stock_transfer_lines`.

### 9.1 `stock_transfers`

| Column | Meaning |
|---|---|
| `transfer_id` | Primary key. Referenced by `stock_transfer_lines`. |
| `from_warehouse_id` | Source warehouse (FK to `warehouses`). |
| `to_warehouse_id` | Destination warehouse (FK to `warehouses`). |
| `status_code` | The transfer's lifecycle state. Coded column; decode through the **TRANSFER_STATUS** code set. Labels: requested, in_transit, received, cancelled. |
| `created_date` | When the transfer was requested. |
| `shipped_date` | When stock left the source. Null until shipped. |
| `received_date` | When stock arrived at the destination. Null until received. |

`stock_transfers.status_code` decodes through **TRANSFER_STATUS and only TRANSFER_STATUS**. The TRANSFER_STATUS "received" terminal here is a *different value in a different code set* from the PO_STATUS "received" on replenishment orders — do not carry a PO decode onto a transfer or vice versa. The three date columns and the status should stay consistent: an in_transit transfer has a `shipped_date` but no `received_date`; a received transfer has both. See **04_reference_keys_codes_and_conventions.md** for the state machine.

Note both `from_warehouse_id` and `to_warehouse_id` reference the same `warehouses` table, so joining warehouse names requires two aliased joins:

```sql
-- In-transit transfers with source and destination named.
-- Replace :transfer_in_transit with the TRANSFER_STATUS value for in_transit.
SELECT t.transfer_id,
       src.name AS from_warehouse,
       dst.name AS to_warehouse,
       t.created_date, t.shipped_date
FROM stock_transfers t
JOIN warehouses src ON src.warehouse_id = t.from_warehouse_id
JOIN warehouses dst ON dst.warehouse_id = t.to_warehouse_id
WHERE t.status_code = :transfer_in_transit
ORDER BY t.shipped_date;
```

### 9.2 `stock_transfer_lines`

| Column | Meaning |
|---|---|
| `transfer_line_id` | Primary key. |
| `transfer_id` | Parent transfer (FK). |
| `item_code` | The product moved (INTEGER = `products.product_id`). |
| `qty_requested` | Units requested to transfer. |
| `qty_shipped` | Units actually shipped from source. |
| `qty_received` | Units received at destination. |

The three quantity columns track the transfer end to end and expose shrinkage or short-ships in transit: `qty_requested` ≥ `qty_shipped` ≥ `qty_received` is the healthy ordering, and any gap between shipped and received is loss or damage in transit.

```sql
-- Transfer lines where units shipped did not all arrive (in-transit shrinkage)
SELECT tl.transfer_id, tl.item_code, p.name AS product,
       tl.qty_requested, tl.qty_shipped, tl.qty_received,
       tl.qty_shipped - tl.qty_received AS units_lost_in_transit
FROM stock_transfer_lines tl
JOIN products p ON p.product_id = tl.item_code
WHERE tl.qty_shipped > tl.qty_received
ORDER BY units_lost_in_transit DESC;
```

A shipped transfer posts a transfer_out (negative delta) movement at the source warehouse and a transfer_in (positive delta) movement at the destination in the inventory ledger, so the network on-hand nets out while the per-warehouse positions change. Auditing that both legs posted is a good integrity check on the ledger:

```sql
-- Both ledger legs for transfers of one product (out at source, in at destination).
-- Replace the placeholders with INV_TXN_TYPE values from 04_reference_keys_codes_and_conventions.md.
SELECT txn_type_code, warehouse_id, SUM(quantity_delta) AS net
FROM inventory_transactions
WHERE item_code = 42
  AND txn_type_code IN (:txn_transfer_out, :txn_transfer_in)
GROUP BY txn_type_code, warehouse_id;
```

---

## 10. Inventory adjustments

Not every change in on-hand comes from a receipt, shipment, or transfer. `inventory_adjustments` records manual corrections — damage write-offs, theft/shrinkage, found stock, and bookkeeping corrections.

| Column | Meaning |
|---|---|
| `adjustment_id` | Primary key. |
| `warehouse_id` | Warehouse adjusted (FK). |
| `item_code` | The product adjusted (INTEGER = `products.product_id`). |
| `adjustment_date` | Date of the adjustment. |
| `quantity_delta` | The signed change applied (positive adds stock, negative removes it) — the same sign convention as the transaction ledger. |
| `reason_code` | Why the adjustment was made. Coded column; decode through the **ADJ_REASON** code set. Labels: cycle_count, damage, theft, found, correction. |

`quantity_delta` here follows the identical sign convention as `inventory_transactions.quantity_delta`: positive increases on-hand, negative decreases it. Adjustments post to the inventory ledger as adjustment-typed movements, so an adjustment's delta will also appear in `inventory_transactions`.

`reason_code` categorizes the adjustment and drives loss analysis. The cycle_count reason label specifically means "the adjustment was posted to true up the book to a physical count" and ties back to the cycle-count process in section 11; damage and theft are shrinkage losses; found is unexpected stock discovered; correction is a bookkeeping fix.

```sql
-- Net adjustment impact by reason over 2024 (which reasons cost us stock?).
-- Reference the ADJ_REASON code set in 04_reference_keys_codes_and_conventions.md to label reason_code.
SELECT reason_code,
       COUNT(*)             AS adjustments,
       SUM(quantity_delta)  AS net_units,
       SUM(CASE WHEN quantity_delta < 0 THEN -quantity_delta ELSE 0 END) AS units_lost,
       SUM(CASE WHEN quantity_delta > 0 THEN  quantity_delta ELSE 0 END) AS units_gained
FROM inventory_adjustments
WHERE adjustment_date >= '2024-01-01' AND adjustment_date <= '2024-12-31'
GROUP BY reason_code
ORDER BY net_units;
```

To value shrinkage in dollars, join the adjusted item to its cost. A defensible unit cost is the preferred supplier's `unit_cost`:

```sql
-- Dollar value of stock lost to theft/damage in 2024 at preferred-supplier cost.
-- Replace the placeholders with the ADJ_REASON values for theft and damage.
SELECT a.item_code, p.name AS product,
       SUM(-a.quantity_delta) AS units_lost,
       sp.unit_cost,
       SUM(-a.quantity_delta) * sp.unit_cost AS loss_value
FROM inventory_adjustments a
JOIN products p ON p.product_id = a.item_code
LEFT JOIN supplier_products sp ON sp.item_code = a.item_code AND sp.is_preferred = 1
WHERE a.reason_code IN (:adj_theft, :adj_damage)
  AND a.quantity_delta < 0
  AND a.adjustment_date >= '2024-01-01' AND a.adjustment_date <= '2024-12-31'
GROUP BY a.item_code, p.name, sp.unit_cost
ORDER BY loss_value DESC;
```

---

## 11. Cycle counts and inventory accuracy

`cycle_counts` records physical inventory verification — the routine re-counting of stock, bin by bin, that keeps the book honest. It is the source of the inventory-accuracy metrics and, when it finds a discrepancy, the trigger for an adjustment.

| Column | Meaning |
|---|---|
| `count_id` | Primary key. |
| `warehouse_id` | Warehouse counted (FK). |
| `item_code` | The product counted (INTEGER = `products.product_id`). |
| `bin_id` | The specific bin counted (FK to `bins`). **May be null** for a warehouse-level count not tied to a single bin. |
| `system_qty` | What the system believed was on hand at count time. |
| `counted_qty` | What the counter physically found. |
| `variance` | The discrepancy, defined as **`counted_qty − system_qty`** (positive = more found than expected, negative = shortage). |
| `count_date` | When the count was performed. |
| `status_code` | The count's workflow state. Coded column; decode through the **CYCLE_COUNT_STATUS** code set. Labels: scheduled, counted, reconciled. |

### 11.1 Variance

`variance = counted_qty − system_qty`. It is signed the same way as the rest of the domain: a positive variance means the counter found more than the book, a negative variance means a shortage. Even though the column is stored, it is defined by that formula, so it should always equal `counted_qty − system_qty`; a stored variance that disagrees is a data-quality defect:

```sql
-- Data-quality check: stored variance disagrees with counted_qty - system_qty
SELECT count_id, item_code, warehouse_id, system_qty, counted_qty, variance
FROM cycle_counts
WHERE variance <> counted_qty - system_qty;
```

### 11.2 The count workflow status

`cycle_counts.status_code` uses the **CYCLE_COUNT_STATUS** code set — a three-state workflow whose terminal label is **reconciled**. This is the point to re-state HARD RULE 3 in context: the CYCLE_COUNT_STATUS "reconciled" terminal is *not* the PO_STATUS "received" and *not* the TRANSFER_STATUS "received." All three are terminal "done" states on different documents drawn from different code sets, and there is no shared integer or shared decode among them. A count moves scheduled → counted → reconciled: scheduled means planned but not yet performed, counted means the physical count is in but not yet actioned, and reconciled means any variance has been resolved (typically by posting an inventory adjustment with the cycle_count reason). The lifecycle is detailed in **04_reference_keys_codes_and_conventions.md**.

```sql
-- Counts that found a discrepancy but have not been reconciled yet.
-- Replace :cc_reconciled with the CYCLE_COUNT_STATUS value for reconciled.
SELECT c.count_id, c.warehouse_id, c.item_code, b.bin_code,
       c.system_qty, c.counted_qty, c.variance, c.count_date
FROM cycle_counts c
LEFT JOIN bins b ON b.bin_id = c.bin_id
WHERE c.variance <> 0
  AND c.status_code <> :cc_reconciled
ORDER BY ABS(c.variance) DESC;
```

### 11.3 Inventory accuracy metrics

Inventory accuracy is measured off cycle counts. Two standard framings:

**Count accuracy rate** — the share of counts that matched the book exactly (zero variance):

```sql
-- Count accuracy rate over 2024
SELECT
  ROUND(100.0 * SUM(CASE WHEN variance = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_accurate,
  COUNT(*) AS counts_performed
FROM cycle_counts
WHERE count_date >= '2024-01-01' AND count_date <= '2024-12-31';
```

**Absolute variance by warehouse** — which sites drift the most, using absolute variance so overs and shorts do not cancel:

```sql
-- Total absolute unit variance by warehouse (accuracy problem sites)
SELECT c.warehouse_id, w.name,
       SUM(ABS(c.variance))                                   AS total_abs_variance,
       COUNT(*)                                               AS counts,
       ROUND(1.0 * SUM(ABS(c.variance)) / COUNT(*), 2)        AS avg_abs_variance
FROM cycle_counts c
JOIN warehouses w ON w.warehouse_id = c.warehouse_id
GROUP BY c.warehouse_id, w.name
ORDER BY total_abs_variance DESC;
```

The canonical definitions of variance, count accuracy, and the below-reorder and available measures all live in **04_reference_keys_codes_and_conventions.md**; use those wordings when a report needs to match the standard.

Cycle counts also close the loop with `inventory.last_counted_date` (section 3.5): a count on an item/warehouse should advance that date, and reconciling a discrepant count posts an `inventory_adjustment` with the cycle_count reason (section 10), which in turn posts an adjustment-typed movement to the ledger (section 5). That chain — count → adjustment → ledger → refreshed on-hand — is how physical reality is written back into the book.

---

## 12. Putting it together: the inventory flow end to end

The tables in this domain describe one continuous flow, and most substantive questions traverse several of them. The shape to keep in mind:

1. **Source.** `suppliers` and `supplier_products` define who we buy from, at what cost, with what lead time, and which supplier is preferred per `item_code`.
2. **Trigger.** `inventory` positions drop below `reorder_point` (`quantity_on_hand < reorder_point`), which calls for a purchase of `reorder_qty` units from the preferred supplier.
3. **Order.** A `replenishment_orders` header with `replenishment_lines` records the purchase; its status runs through PO_STATUS toward the received terminal.
4. **Receive.** `receipts` and `receipt_lines` book the physical arrival (with an ITEM_CONDITION on each line); partial deliveries accumulate as multiple receipts and show as a partial PO status.
5. **Post.** Every receipt posts a positive-delta receipt movement to `inventory_transactions`, which raises `inventory.quantity_on_hand`.
6. **Bill.** `supplier_invoices` (INVOICE_STATUS) captures the vendor's bill against the PO — detail in 04_reference_keys_codes_and_conventions.md.
7. **Rebalance.** `stock_transfers` and `stock_transfer_lines` (TRANSFER_STATUS) move stock between warehouses, posting matched transfer_out/transfer_in movements so network on-hand nets while per-site positions shift.
8. **Consume.** Outbound fulfillment posts negative-delta shipment movements to the ledger, drawing down on-hand; allocations against open orders show up as `quantity_allocated`, and available = on_hand − allocated is what remains free to promise.
9. **Correct.** `inventory_adjustments` (ADJ_REASON) writes off damage/theft or books found stock, and `cycle_counts` (CYCLE_COUNT_STATUS) verify the book against reality, feeding adjustments and refreshing `last_counted_date`.

Three disciplines carry through every one of those steps and are worth restating as a closing checklist:

- **Identify products by `item_code`.** Every table here uses `item_code` (INTEGER = `products.product_id`). Never join it to a SKU string; bridge through `products` when a question is phrased in SKUs (see 04_reference_keys_codes_and_conventions.md).
- **Decode each coded column through its own named code set.** ZONE_TYPE, SUPPLIER_STATUS, PO_STATUS, INV_TXN_TYPE, ITEM_CONDITION, INVOICE_STATUS, TRANSFER_STATUS, ADJ_REASON, and CYCLE_COUNT_STATUS are all separate sets; the integer values live only in 04_reference_keys_codes_and_conventions.md. The "received" of a PO, the "received" of a transfer, and the "reconciled" of a cycle count are different values in different sets — never carry a decode across tables.
- **Trust the signed ledger for movement math.** `quantity_delta` (in both `inventory_transactions` and `inventory_adjustments`) already carries direction in its sign; sum it directly to reconcile on-hand, and it should tie back to `inventory.quantity_on_hand`.

For the precise definitions behind the derived measures used above, see 04_reference_keys_codes_and_conventions.md; for the status lifecycles, 04_reference_keys_codes_and_conventions.md; for identifiers and the SKU⇄item_code bridge, 04_reference_keys_codes_and_conventions.md; for code values, 04_reference_keys_codes_and_conventions.md; and for supplier and carrier billing, 04_reference_keys_codes_and_conventions.md.
