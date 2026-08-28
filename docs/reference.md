# Reference: Keys, Codes & Reporting Conventions

Cross-cutting reference for the logistics dataset. The three domain guides
(`order_management.md`, `fulfillment_and_shipping.md`,
`warehouse_and_inventory.md`) describe each domain's tables and name the
code set every coded column uses; this document defines those code sets, the
identifier/key conventions that bridge the domains, and the standard reporting
rules (exclusions, metric definitions). Coded columns resolve in two steps:
the domain guide names the code set, and the **Code Dictionary** section below
gives its integer values.

This document holds eight sections:

- [Warehouse Analyst Guide — Overview and Orientation](#warehouse-analyst-guide--overview-and-orientation)
- [Identifiers and Keys](#identifiers-and-keys)
- [Code Dictionary](#code-dictionary)
- [Lifecycle and Statuses](#lifecycle-and-statuses)
- [Exclusions, Reporting Conventions, and Data Quality](#exclusions-reporting-conventions-and-data-quality)
- [Metrics and Definitions — the Canonical Catalog](#metrics-and-definitions--the-canonical-catalog)
- [Pricing, Costs & Billing](#pricing-costs--billing)
- [Query Recipes and Pitfalls](#query-recipes-and-pitfalls)

---

## Warehouse Analyst Guide — Overview and Orientation

Welcome to the analytics reference for our operational data warehouse. This is
the starting point for anyone writing queries against the business. Read it
once end to end; afterward you will mostly use it as a map to the more specific
guidance documents. Everything here is written for the person who has to turn a
business question into correct SQL and defend the number.

### What the company does

We are a mid-size third-party logistics (3PL) and omnichannel retail logistics
operator. In plain terms: customers place orders through several sales channels,
we pick and pack those orders in our distribution centers, we hand them to
carriers who move them across a multi-leg transportation network to the
customer's door, and we manage the inventory and supplier replenishment that
keeps stock on the shelf so the orders can be filled in the first place. When
something comes back, we process the return and decide what to do with the item.

Because we operate as a 3PL as well as running our own omnichannel retail flow,
the same data model has to serve both the "sell it" side (orders, payments,
promotions, gift cards) and the "move it and stock it" side (shipments, picks,
inventory, suppliers, transfers, receipts, cycle counts). The value of this
warehouse to an analyst is that all three worlds share keys, so cross-domain
questions — "how long did fulfilled orders take to deliver," "which products
that sell fastest are below reorder point," "which carriers cost the most per
delivered shipment" — are answerable in one place.

### The three domains and how they connect

The warehouse is organized into three domains. Think of them as three stages of
the same physical journey.

1. **Order Management** — the demand side. A customer, their addresses and
   segment, the orders they place, the lines on each order, the payments,
   promotions applied, and any gift cards used. This domain answers "what did we
   sell, to whom, through what channel, for how much."

2. **Fulfillment / Shipping** — the movement side. Once an order is ready to
   ship, it becomes one or more shipments carried by a carrier on a chosen
   service level, packed into packages, moving over one or more legs through a
   network of facilities, emitting tracking events, occasionally hitting
   delivery exceptions. This domain also holds the warehouse pick tasks that
   assemble an order, and the returns process that runs after delivery. It
   answers "did it get there, on time, at what carrier cost, and what came
   back."

3. **Warehouse & Inventory** — the supply side. Physical warehouses, their
   zones and bins, the suppliers we buy from, purchase (replenishment) orders
   and the receipts against them, on-hand and allocated stock, lot tracking, the
   ledger of every inventory movement, stock transfers between warehouses, and
   the audit tools (adjustments and cycle counts). It answers "do we have the
   stock, where is it, when will more arrive, and is the book accurate."

**How they connect.** The order is the spine. An `orders` row links to the
customer on one side and, on the other, fans out to `shipments` (fulfillment),
`returns`, and `pick_tasks`. Each shipment ships **from** a warehouse
(`shipments.origin_warehouse_id`), which is the join into the inventory domain.
Products are the second connective tissue: an order line names a product, and
the same product is stocked, replenished, and counted on the inventory side.
Suppliers feed warehouses through replenishment orders and receipts. See the
relationship notes in the **Identifiers and Keys** section for the exact join columns.

A few concrete cross-domain paths you will use constantly:

- **Order to delivery outcome:** `orders` → `shipments` (by `order_id`) →
  `shipment_legs` / `tracking_events` / `delivery_exceptions` (by `shipment_id`).
  This lets you go from "an order" to "was it delivered, when, and did anything go
  wrong on the way."
- **Order to warehouse work:** `orders` → `pick_tasks` (by `order_id`) →
  `pick_lines`. This connects demand to the physical picking that fulfilled it.
- **Order to after-sale:** `orders` → `returns` (by `order_id`) → `return_lines`,
  and `orders` → `payments`.
- **Fulfillment to stock:** `shipments.origin_warehouse_id` → `warehouses`, and
  from a warehouse into `inventory`, `bins`, `warehouse_zones`, and the inbound
  supply chain (`replenishment_orders`, `receipts`, `stock_transfers`).
- **Product everywhere:** an order line's `sku` and an inventory row's
  `item_code` both resolve to the same `products` row — the bridge between the two
  halves of the business.

One connection point deserves special attention up front, covered next.

### Two product-identifier systems (read this before you join products)

The single most important thing to internalize before writing cross-domain
queries: **the same product is referenced by two different identifier
vocabularies depending on which side of the business you are on.**

- On the **order / returns / shipment side**, a product is referenced by its
  **`sku`** — a `TEXT` value formatted like `SKU-00042`. You will see the `sku`
  column on `order_lines`, `return_lines`, and `shipment_items`.

- On the **inventory / supplier / warehouse side**, the same product is
  referenced by its **`item_code`** — an `INTEGER` equal to
  `products.product_id` (e.g. `42`). You will see the `item_code` column on
  `supplier_products`, `inventory`, `inventory_lots`, `inventory_transactions`,
  `replenishment_lines`, `receipt_lines`, `stock_transfer_lines`,
  `inventory_adjustments`, `cycle_counts`, and `pick_lines`.

These are two encodings of one product. The `products` table is the only bridge:
it carries both `product_id` and `sku`. Numerically,
`item_code = CAST(SUBSTR(sku, 5) AS INTEGER)` and
`sku = 'SKU-' || printf('%05d', item_code)`. A join that treats them as directly
equal (for example `order_lines.sku = inventory.item_code`) returns zero rows
without raising an error, because a text value never equals an integer here.
Always route product joins through `products`. The full mechanics, with worked
examples, are in the **Identifiers and Keys** section.

### The entity landscape (map of the ~47 tables)

Below is a narrative map of every table, grouped by domain, with one line on its
role. Use it to find the right table quickly; the topic docs go deeper.

#### Order Management (14 tables)

- **product_categories** — category tree; `parent_category_id` self-references
  for a hierarchy.
- **products** — the product master. Holds both `product_id` and `sku`, so it is
  the bridge between the two identifier systems; also unit price, weight, active
  flag, launch date.
- **product_attributes** — flexible name/value attributes attached to a product.
- **price_history** — dated unit-price changes for a product over time.
- **customers** — the customer master, with segment and active flag.
- **customer_addresses** — billing/shipping addresses per customer, with a
  default flag.
- **orders** — the order header: customer, date, status, priority, channel,
  ship-to address, promised date, and total. The spine of the warehouse.
- **order_lines** — the line items on an order; references product by `sku`.
- **order_status_history** — the timestamped audit trail of an order's status
  changes.
- **payments** — payments applied to an order, with method and status.
- **promotions** — promotion definitions (code, type, value, active window).
- **order_promotions** — which promotions were applied to which order and the
  discount granted.
- **gift_cards** — gift card master, with balances and status.
- **gift_card_transactions** — the ledger of issue/redeem/reload/refund activity
  on gift cards.

#### Fulfillment / Shipping (15 tables)

- **carriers** — the carriers we tender freight to (name, SCAC, active flag).
- **carrier_services** — the named service offerings a carrier sells, each at a
  service level with an estimated transit time.
- **facilities** — the transportation network nodes (hubs, cross-docks, ports,
  last-mile depots, origin DCs) that legs move between.
- **shipments** — a shipment fulfilling an order: carrier, service, origin
  warehouse, status, ship/delivered/promised dates, tracking number, weight. The
  hub of the fulfillment domain.
- **packages** — the physical parcels within a shipment, with packaging type and
  dimensions/weight.
- **shipment_items** — the contents of a shipment, tying a package and an order
  line to a `sku` and quantity.
- **shipment_legs** — the ordered legs of a shipment's journey between
  facilities, each with a transport mode and status.
- **tracking_events** — the append-only stream of tracking scans for a shipment.
- **delivery_exceptions** — problems reported against a shipment, open until a
  `resolved_ts` is set.
- **pick_tasks** — the warehouse work of assembling an order for shipment.
- **pick_lines** — the item-level detail of a pick task; references product by
  `item_code`.
- **returns** — a return authorization (RMA) against an order, with reason,
  status, and disposition.
- **return_lines** — the items on a return; references product by `sku`, with an
  item condition.
- **carrier_invoices** — invoices carriers bill us for freight, with status and
  payment dates.
- **route_lanes** — the standard lane definitions (origin/dest facility, mode,
  distance, standard transit days) that legs run on.

#### Warehouse & Inventory (18 tables)

- **warehouses** — our physical distribution centers, with capacity and active
  flag.
- **warehouse_zones** — functional zones within a warehouse (receiving, storage,
  picking, shipping, cold storage).
- **bins** — the individual storage locations within a zone.
- **suppliers** — the vendors we buy inventory from, with status and default lead
  time.
- **supplier_products** — the catalog of what each supplier sells us, with cost,
  lead time, and a preferred-source flag; references product by `item_code`.
- **supplier_contacts** — named contacts at a supplier.
- **inventory** — the on-hand position of a product at a warehouse: on-hand,
  allocated, reorder point, reorder quantity, last counted date. Unique per
  (warehouse, item).
- **inventory_lots** — lot-level stock with received and (optional) expiry dates.
- **inventory_transactions** — the movement ledger; every receipt, shipment,
  transfer, and adjustment posts here. (`return_restock` is a defined type but is
  not posted in this dataset.)
- **replenishment_orders** — purchase orders to suppliers to restock a warehouse.
- **replenishment_lines** — the line items on a replenishment order, with ordered
  and received quantities.
- **receipts** — physical receiving events against a replenishment order.
- **receipt_lines** — the items received on a receipt, with a condition.
- **supplier_invoices** — invoices suppliers bill us, optionally tied to a
  replenishment order.
- **stock_transfers** — movements of stock between two warehouses.
- **stock_transfer_lines** — the items on a transfer, with requested/shipped/
  received quantities.
- **inventory_adjustments** — manual stock corrections, with a reason.
- **cycle_counts** — scheduled physical counts comparing system vs counted
  quantity, with the resulting variance.

That is 14 + 15 + 18 = 47 tables.

### Global data conventions

These conventions hold across the whole warehouse. Learn them once and apply
them everywhere.

- **TODAY is 2024-12-31.** The dataset is a snapshot as of the end of 2024. Any
  "as of now," "currently," "still open," "overdue," or "how many days since"
  question should be evaluated against `2024-12-31`, not against the real-world
  current date. There is no data after this point.

- **Money is US dollars, stored as `REAL` with two decimal places.** All amount,
  price, cost, and balance columns are dollars. Do not scale or convert. When
  aggregating, round only at presentation; the stored values already carry cents.

- **Weights are in kilograms.** Every `weight_kg` column (products, shipments,
  packages) is kilograms. There is no mixed-unit pitfall; do not convert.

- **Dates are `YYYY-MM-DD`; timestamps are ISO-8601.** Columns ending in
  `_date` hold a plain date string; columns ending in `_ts` hold a full
  timestamp. Both are stored as `TEXT` and sort and compare correctly as
  strings, so ordinary string comparison and SQLite date functions both work.
  There is no timezone offset to reconcile.

- **`is_active` flags mark current/usable records.** `products`, `customers`,
  `carriers`, and `warehouses` carry an `is_active` flag. An inactive product,
  customer, carrier, or warehouse still appears in history — an inactive product
  can have historical orders — so filter on `is_active` only when the question
  is about the *current* usable set, not about historical activity.

- **How NULLs are used.** NULL means "not applicable yet" or "no value," and it
  is used deliberately as a lifecycle signal. A NULL `delivered_date` on a
  shipment means it has not been delivered; a NULL `resolved_ts` on a delivery
  exception means it is still open; a NULL `received_date` on a return or a
  replenishment order means it has not been received; a NULL `disposition_code`
  on a return means disposition is not yet decided; a NULL `arrived_ts` on a leg
  means the leg has not completed; a NULL `paid_date` on an invoice means it is
  unpaid. Because NULLs are meaningful, be careful with comparisons: `x <> value`
  and inequalities silently drop NULL rows, so use `IS NULL` / `IS NOT NULL`
  explicitly when a NULL is part of what you are measuring. See
  the **Exclusions, Reporting Conventions, and Data Quality** section.

### Short business glossary

- **SKU** — the text product identifier (`SKU-00042`) used on the order/shipping
  side. See the **Identifiers and Keys** section.
- **item_code** — the integer product identifier (equal to `products.product_id`)
  used on the inventory/supplier side. Same product, different vocabulary.
- **DC / warehouse** — a distribution center; a physical stocking and shipping
  site. Rows live in `warehouses`; shipments originate from one.
- **Facility** — a node in the *transportation* network (hub, cross-dock, port,
  last-mile depot, origin DC) that shipment legs travel between. Distinct from a
  warehouse: warehouses hold inventory, facilities route freight.
- **Carrier** — the company that physically transports a shipment.
- **Service level** — the speed/class of a carrier service (ground, two-day,
  overnight, economy, freight); named in `carrier_services`.
- **Replenishment / PO** — a purchase order placed to a supplier to restock a
  warehouse (`replenishment_orders`). "Replenishment order" and "PO" are the same
  thing here.
- **Receipt** — the physical receiving of goods against a replenishment order
  (`receipts` / `receipt_lines`).
- **Cycle count** — a periodic physical stock count that compares system
  quantity to counted quantity, yielding a variance (`cycle_counts`).
- **RMA** — Return Merchandise Authorization; the identifier and record for a
  return (`returns.rma_number`).
- **Reorder point** — the on-hand level at or below which a product should be
  reordered; a product is "below reorder point" when
  `quantity_on_hand < reorder_point`.
- **Allocated vs on-hand** — `quantity_on_hand` is the physical stock in the
  warehouse; `quantity_allocated` is the portion already committed to orders.
  Available-to-promise is on-hand minus allocated. See
  `warehouse_and_inventory.md` and the **Metrics and Definitions** section.
- **Lot** — a batch of received stock, tracked with received and optional expiry
  dates (`inventory_lots`).
- **Lane** — a standard origin→destination transport route with a mode and
  standard transit time (`route_lanes`).

### Index of the guidance documents

The corpus is four documents. Three cover the operational domains, and this
document is the cross-cutting reference. Use this index to jump to the right
place.

- **order_management.md** — orders, order lines, customers, addresses,
  payments, promotions, gift cards; order totals, discounts, and channels.
- **fulfillment_and_shipping.md** — shipments, packages, legs, tracking,
  exceptions, pick tasks, returns, carriers, services, facilities, lanes; on-time
  and transit semantics.
- **warehouse_and_inventory.md** — warehouses, zones, bins, suppliers,
  inventory positions, lots, the transaction ledger, replenishment, receipts,
  transfers, adjustments, cycle counts.
- **reference.md** *(this document)* — the
  cross-cutting reference, organized into eight sections:
  - **Overview and Orientation** — what the company does, the domains, the full
    table map, global conventions, the glossary, and this index.
  - **Identifiers and Keys** — primary/foreign keys, join paths, and the full
    treatment of the two product-identifier systems (`sku` vs `item_code`) and
    how to bridge them through `products`.
  - **Code Dictionary** — the single authoritative decode of every coded column:
    each code set's integer values and their labels. This is the only place
    integer code values appear.
  - **Lifecycle and Statuses** — the state machine of every stateful entity, each
    driven by its own code set, with terminal states, allowed transitions, and
    the critical rule that a `status` decode never carries across tables.
  - **Exclusions, Reporting Conventions, and Data Quality** — records to exclude
    from reporting (including internal/test orders), NULL handling, and known
    data-quality cautions.
  - **Metrics and Definitions** — the canonical definitions of business metrics
    (revenue, on-time delivery, fill rate, days-to-deliver, below reorder point,
    etc.) so numbers reconcile across analysts.
  - **Pricing, Costs & Billing** — unit price vs cost, price history, promotions
    and discounts, gift cards, carrier and supplier invoicing.
  - **Query Recipes and Pitfalls** — worked query patterns and the common
    mistakes to avoid, tying together the rules from the other sections.

Coded columns resolve in two steps: a domain file names the code set a column
uses, and the **Code Dictionary** section here gives the integer values. When a
question spans domains, start with the map above, confirm identifiers in the
**Identifiers and Keys** section, decode any coded column via the domain file
plus the **Code Dictionary** section, and pin the exact metric definition in the
**Metrics and Definitions** section.

### How to approach a question (a short workflow)

Because the warehouse is broad and several conventions are load-bearing, a
consistent approach avoids most errors:

1. **Identify the grain.** Is the question about orders, order lines, shipments,
   shipment items, inventory positions, or transactions? Counting at the wrong
   grain (for example counting order lines when the question means orders, or
   shipments when it means orders) is the most common source of a
   plausible-but-wrong number. Decide the grain first, then choose the table.

2. **Resolve identifiers.** If the query crosses the sell/stock boundary, route
   product joins through `products` (`sku` ⇄ `item_code`); never equate the two
   columns directly. Confirm the join keys in the **Identifiers and Keys** section.

3. **Decode coded columns via the right code set.** Any column ending in `_code`,
   or named `status`/`status_code`, is an integer that means nothing until you
   decode it. Find the code set name in the relevant topic doc (or
   the **Lifecycle and Statuses** section for statuses) and the integer values in
   the **Code Dictionary** section. Remember that a `status` decode is per-table.

4. **Apply the standard exclusions.** Internal/test orders (the `internal_test`
   tier of the ORDER_PRIORITY code set) are excluded from all business reporting;
   see the **Exclusions, Reporting Conventions, and Data Quality** section. Decide whether cancelled orders,
   inactive products, or undelivered shipments belong in your population.

5. **Handle NULLs deliberately.** Where a NULL is a lifecycle signal (undelivered,
   unresolved, unreceived, unpaid), use `IS NULL` / `IS NOT NULL` explicitly
   rather than inequalities that silently drop NULL rows.

6. **Anchor time to the snapshot.** "Now," "current," "overdue," and "days since"
   are all measured against TODAY = 2024-12-31.

7. **Pin the metric definition.** Before reporting revenue, on-time rate, fill
   rate, or any named KPI, confirm the canonical definition in
   the **Metrics and Definitions** section so your number reconciles with everyone
   else's.

Following these seven steps in order will keep cross-domain queries correct and
consistent, which is the entire point of this reference set.

---

## Identifiers and Keys

This is the authoritative reference for how the warehouse's 47 tables are keyed
and joined. Read it before writing any cross-table query. It covers the primary
key of every table, the foreign-key relationships grouped by domain, the two
product-identifier vocabularies that split the model down the middle, and the
worked join paths that connect Order Management, Fulfillment/Shipping, and
Warehouse & Inventory.

Two conventions in this document:

- Coded columns (anything ending in `_code`, plus the several `status` /
  `status_code` columns) are decoded per table in
  the **Lifecycle and Statuses** section and the **Code Dictionary** section. This document
  never prints the integer behind a label; when a join or filter depends on a
  code we reference the code set by name and leave the literal to the **Code Dictionary** section.
- Some foreign keys are enforced by a `REFERENCES` clause in the DDL, and some
  are *logical* — the column carries a value that identifies a row in another
  table but there is no database-level constraint. The most important logical
  relationship in the whole model is the product link, and it is deliberately
  expressed two different ways. That is the central topic below.

---

### 1. How to read the key model

Every table has a single-column integer surrogate primary key named
`<entity>_id` (for example `order_id`, `shipment_id`, `inventory_id`). There are
no composite primary keys. A handful of tables carry an additional business key
enforced `UNIQUE`:

- `products.sku`
- `warehouses.code`
- `facilities.code`
- `promotions.code`
- `gift_cards.code`
- `returns.rma_number`
- `carrier_invoices.invoice_number`
- `supplier_invoices.invoice_number`
- `inventory` has a compound `UNIQUE (warehouse_id, item_code)` — a warehouse
  holds at most one inventory row per product.

Joins are almost always `<child>.<parent>_id = <parent>.<parent>_id`. The
exceptions — where the join is on a code or a formatted string rather than a
surrogate id — are the ones that cause silent wrong answers, and they get their
own sections.

---

### 2. Primary keys and foreign keys by domain

Each table below lists its primary key and every foreign key as
`column → referenced_table(referenced_column)`. Keys marked *(logical)* are not
declared in the DDL but are real relationships you must respect in queries. Keys
marked *(NULL)* are nullable, so joins on them should usually be `LEFT JOIN` and
be prepared for missing parents.

#### Domain 1 — Order Management (14 tables)

**product_categories** — PK `category_id`
- `parent_category_id → product_categories(category_id)` *(NULL; self-reference
  for the category tree; top-level categories have `parent_category_id IS NULL`)*

**products** — PK `product_id`; business key `sku` UNIQUE
- `category_id → product_categories(category_id)`
- This is the bridge table for the two product vocabularies. `product_id` is the
  integer identity used on the inventory side as `item_code`; `sku` is the text
  identity used on the order side. See section 3.

**product_attributes** — PK `attribute_id`
- `product_id → products(product_id)`

**price_history** — PK `price_history_id`
- `product_id → products(product_id)`
- Historical list prices by `effective_date`. `products.unit_price` is the
  current price; `order_lines.unit_price` is the price actually charged on a
  line and should be used for revenue (see the **Metrics and Definitions** section).

**customers** — PK `customer_id`
- `segment_code` decodes via CUSTOMER_SEGMENT.

**customer_addresses** — PK `address_id`
- `customer_id → customers(customer_id)`
- `address_type_code` decodes via ADDRESS_TYPE.

**orders** — PK `order_id`
- `customer_id → customers(customer_id)`
- `ship_to_address_id → customer_addresses(address_id)` *(NULL)*
- `status` decodes via ORDER_STATUS, `priority_code` via ORDER_PRIORITY,
  `channel_code` via ORDER_CHANNEL. The `internal_test` value of ORDER_PRIORITY
  is excluded from all reporting (see the **Exclusions, Reporting Conventions, and Data Quality** section).

**order_lines** — PK `order_line_id`
- `order_id → orders(order_id)`
- `sku → products(sku)` *(logical, TEXT match)* — see section 3.

**order_status_history** — PK `history_id`
- `order_id → orders(order_id)`
- `status` decodes via ORDER_STATUS. One row per status transition; the current
  status also lives on `orders.status`.

**payments** — PK `payment_id`
- `order_id → orders(order_id)`
- `method_code` decodes via PAYMENT_METHOD; `status_code` via PAYMENT_STATUS.

**promotions** — PK `promotion_id`; business key `code` UNIQUE
- `promo_type_code` decodes via PROMO_TYPE.

**order_promotions** — PK `order_promotion_id` *(association table)*
- `order_id → orders(order_id)`
- `promotion_id → promotions(promotion_id)`
- One order can carry several promotions and one promotion applies to many
  orders. Joining `orders` through here fans out — see section 6.

**gift_cards** — PK `gift_card_id`; business key `code` UNIQUE
- `customer_id → customers(customer_id)` *(NULL — a gift card need not be tied to
  a customer)*
- `status_code` decodes via GIFTCARD_STATUS.

**gift_card_transactions** — PK `gc_txn_id`
- `gift_card_id → gift_cards(gift_card_id)`
- `order_id → orders(order_id)` *(NULL — reloads and refunds are not tied to an
  order)*
- `txn_type_code` decodes via GIFTCARD_TXN_TYPE.

#### Domain 2 — Fulfillment / Shipping (15 tables)

**carriers** — PK `carrier_id`

**carrier_services** — PK `service_id`
- `carrier_id → carriers(carrier_id)`
- `service_level_code` decodes via SERVICE_LEVEL.

**facilities** — PK `facility_id`; business key `code` UNIQUE
- `facility_type_code` decodes via FACILITY_TYPE.
- Facilities are the transit nodes used by legs and lanes. They are distinct
  from `warehouses` (the fulfillment origins that hold inventory). Do not join
  `facility_id` to `warehouse_id`; they are separate identifier spaces.

**shipments** — PK `shipment_id`
- `order_id → orders(order_id)`
- `carrier_id → carriers(carrier_id)`
- `service_id → carrier_services(service_id)`
- `origin_warehouse_id → warehouses(warehouse_id)`
- `status` decodes via SHIP_STATUS. `delivered_date` and `promised_date` are
  nullable; on-time logic lives in the **Metrics and Definitions** section.

**packages** — PK `package_id`
- `shipment_id → shipments(shipment_id)`
- `packaging_type_code` decodes via PACKAGING_TYPE.

**shipment_items** — PK `shipment_item_id`
- `shipment_id → shipments(shipment_id)`
- `package_id → packages(package_id)`
- `order_line_id → order_lines(order_line_id)`
- `sku → products(sku)` *(logical, TEXT match)* — see section 3.
- This is the grain at which shipped units are recorded. Because one order line
  can ship in more than one package or shipment, joining here multiplies order
  rows — see section 6.

**shipment_legs** — PK `leg_id`
- `shipment_id → shipments(shipment_id)`
- `from_facility_id → facilities(facility_id)`
- `to_facility_id → facilities(facility_id)`
- `mode_code` decodes via TRANSPORT_MODE; `status` via LEG_STATUS. `leg_seq`
  orders the legs within a shipment; `arrived_ts` is nullable for in-progress
  legs.

**tracking_events** — PK `event_id`
- `shipment_id → shipments(shipment_id)`
- `facility_id → facilities(facility_id)` *(NULL)*
- `event_code` decodes via TRACK_EVENT.

**delivery_exceptions** — PK `exception_id`
- `shipment_id → shipments(shipment_id)`
- `exception_type_code` decodes via EXCEPTION_TYPE. `resolved_ts` is nullable for
  open exceptions.

**pick_tasks** — PK `pick_id`
- `warehouse_id → warehouses(warehouse_id)`
- `order_id → orders(order_id)`
- `status_code` decodes via PICK_STATUS. `completed_ts` nullable while open.

**pick_lines** — PK `pick_line_id`
- `pick_id → pick_tasks(pick_id)`
- `bin_id → bins(bin_id)` *(NULL)*
- `item_code → products(product_id)` *(logical, INTEGER match)* — see section 3.
  Note this Fulfillment table sits on the `item_code` side of the product split,
  not the `sku` side.

**returns** — PK `return_id`; business key `rma_number` UNIQUE
- `order_id → orders(order_id)`
- `reason_code` decodes via RETURN_REASON; `status` via RETURN_STATUS;
  `disposition_code` via RETURN_DISPOSITION *(NULL until dispositioned)*.
  `received_date` nullable until the return is received.

**return_lines** — PK `return_line_id`
- `return_id → returns(return_id)`
- `sku → products(sku)` *(logical, TEXT match)* — see section 3.
- `condition_code` decodes via ITEM_CONDITION *(NULL until inspected)*.

**carrier_invoices** — PK `carrier_invoice_id`; business key `invoice_number` UNIQUE
- `carrier_id → carriers(carrier_id)`
- `status_code` decodes via INVOICE_STATUS. `paid_date` nullable until paid.

**route_lanes** — PK `lane_id`
- `origin_facility_id → facilities(facility_id)`
- `dest_facility_id → facilities(facility_id)`
- `mode_code` decodes via TRANSPORT_MODE. Standard reference data for the
  distance and standard transit days between two facilities.

#### Domain 3 — Warehouse & Inventory (18 tables)

**warehouses** — PK `warehouse_id`; business key `code` UNIQUE

**warehouse_zones** — PK `zone_id`
- `warehouse_id → warehouses(warehouse_id)`
- `zone_type_code` decodes via ZONE_TYPE.

**bins** — PK `bin_id`
- `warehouse_id → warehouses(warehouse_id)`
- `zone_id → warehouse_zones(zone_id)`

**suppliers** — PK `supplier_id`
- `status_code` decodes via SUPPLIER_STATUS.

**supplier_products** — PK `supplier_product_id`
- `supplier_id → suppliers(supplier_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)* — see section 3.
- Carries the supplier's own `supplier_sku` (their catalog code, unrelated to our
  `products.sku`), plus `unit_cost`, `lead_time_days`, and `is_preferred`.

**supplier_contacts** — PK `contact_id`
- `supplier_id → suppliers(supplier_id)`

**inventory** — PK `inventory_id`; UNIQUE `(warehouse_id, item_code)`
- `warehouse_id → warehouses(warehouse_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)*.
- One row per product per warehouse. `quantity_on_hand`, `quantity_allocated`,
  `reorder_point`, `reorder_qty` drive availability and reorder logic (section 6
  and the **Metrics and Definitions** section).

**inventory_lots** — PK `lot_id`
- `warehouse_id → warehouses(warehouse_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)*.
- Lot-level receipts with `received_date` and nullable `expiry_date`.

**inventory_transactions** — PK `txn_id`
- `warehouse_id → warehouses(warehouse_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)*.
- `txn_type_code` decodes via INV_TXN_TYPE. The movement ledger: receipts,
  shipments, transfers, and adjustments post signed `quantity_delta` rows here.
  (`return_restock` is a defined type but is never posted in this dataset.) `reference_type` / `reference_id` point loosely at
  the originating document (for example a `receipt_id` or `adjustment_id`) but are
  not a declared foreign key.

**replenishment_orders** — PK `repl_id`
- `supplier_id → suppliers(supplier_id)`
- `warehouse_id → warehouses(warehouse_id)`
- `status` decodes via PO_STATUS. `received_date` nullable until fully received.
  This is the purchase-order header.

**replenishment_lines** — PK `repl_line_id`
- `repl_id → replenishment_orders(repl_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)*.

**receipts** — PK `receipt_id`
- `repl_id → replenishment_orders(repl_id)`
- `warehouse_id → warehouses(warehouse_id)`

**receipt_lines** — PK `receipt_line_id`
- `receipt_id → receipts(receipt_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)*.
- `condition_code` decodes via ITEM_CONDITION.

**supplier_invoices** — PK `supplier_invoice_id`; business key `invoice_number` UNIQUE
- `supplier_id → suppliers(supplier_id)`
- `repl_id → replenishment_orders(repl_id)` *(NULL — not every supplier invoice
  is tied to a single PO)*
- `status_code` decodes via INVOICE_STATUS.

**stock_transfers** — PK `transfer_id`
- `from_warehouse_id → warehouses(warehouse_id)`
- `to_warehouse_id → warehouses(warehouse_id)`
- `status_code` decodes via TRANSFER_STATUS. `shipped_date` / `received_date`
  nullable through the transfer's life.

**stock_transfer_lines** — PK `transfer_line_id`
- `transfer_id → stock_transfers(transfer_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)*.

**inventory_adjustments** — PK `adjustment_id`
- `warehouse_id → warehouses(warehouse_id)`
- `item_code → products(product_id)` *(logical, INTEGER match)*.
- `reason_code` decodes via ADJ_REASON. `quantity_delta` is signed.

**cycle_counts** — PK `count_id`
- `warehouse_id → warehouses(warehouse_id)`
- `bin_id → bins(bin_id)` *(NULL)*
- `item_code → products(product_id)` *(logical, INTEGER match)*.
- `status_code` decodes via CYCLE_COUNT_STATUS. `variance = counted_qty -
  system_qty` is stored on the row.

---

### 3. The two product identifier systems (read this section carefully)

The single most common source of wrong-but-plausible results in this warehouse
is the product identifier. The same physical product is referenced by two
different columns, in two different types, on two different sides of the model.

**Order / Returns / Shipment side — `sku` (TEXT).** A product is referenced by
its stock-keeping unit, a text string formatted as `SKU-` followed by a
zero-padded 5-digit number. For example, product 42 is `SKU-00042`. Tables that
carry `sku`:

- `order_lines.sku`
- `return_lines.sku`
- `shipment_items.sku`

**Inventory / Supplier / Warehouse side — `item_code` (INTEGER).** The same
product is referenced by its integer item code, which is exactly equal to
`products.product_id`. For example, `SKU-00042` is item code `42`. Tables that
carry `item_code`:

- `supplier_products.item_code`
- `inventory.item_code`
- `inventory_lots.item_code`
- `inventory_transactions.item_code`
- `replenishment_lines.item_code`
- `receipt_lines.item_code`
- `stock_transfer_lines.item_code`
- `inventory_adjustments.item_code`
- `cycle_counts.item_code`
- `pick_lines.item_code`

Note that `pick_lines` lives in the Fulfillment domain but is on the `item_code`
side — picking is a warehouse operation, so it speaks the warehouse's product
vocabulary even though the pick task is tied to an order.

**`products` is the only bridge.** The `products` table is the one place both
identifiers coexist: `product_id` (the integer, equal to `item_code`) and `sku`
(the text, UNIQUE). Any query that needs to relate an order-side row to an
inventory-side row must pass through `products`, or convert one identifier into
the other explicitly.

#### 3.1 The exact conversion, both directions

The formatting is fixed and lossless, so you can convert either way without a
lookup when a join to `products` is inconvenient:

```sql
-- sku  →  item_code : strip the 'SKU-' prefix (4 characters) and cast to integer
item_code = CAST(SUBSTR(sku, 5) AS INTEGER)

-- item_code  →  sku : zero-pad to 5 digits and prepend 'SKU-'
sku = 'SKU-' || printf('%05d', item_code)
```

`SUBSTR(sku, 5)` starts at the 5th character (SQLite is 1-indexed), which is the
first digit after `SKU-`. `printf('%05d', 42)` produces `00042`.

#### 3.2 The pitfall: comparing sku to item_code directly

Because `sku` is TEXT and `item_code` is INTEGER, a direct comparison does **not
match any rows, and SQLite raises no error**. SQLite compares a TEXT value and
an INTEGER value across type classes, and `'SKU-00042' = 42` is simply false.
The query runs, returns zero matched rows, and looks like "there is no
inventory for these products" when in fact the join condition was meaningless.

```sql
-- WRONG: returns zero rows silently, no error
SELECT ol.order_line_id, inv.quantity_on_hand
FROM order_lines ol
JOIN inventory inv ON ol.sku = inv.item_code;   -- TEXT = INTEGER, never true
```

Always either bridge through `products` or convert explicitly. Both correct
forms follow.

#### 3.3 Correct join via the `products` bridge

```sql
-- order line  →  product  →  inventory, through the bridge table
SELECT ol.order_line_id,
       p.sku,
       p.name,
       inv.warehouse_id,
       inv.quantity_on_hand
FROM order_lines ol
JOIN products  p   ON p.sku = ol.sku
JOIN inventory inv ON inv.item_code = p.product_id;
```

#### 3.4 Correct join via explicit conversion

When you have an order-side `sku` and an inventory-side `item_code` and do not
want a third table in the join, convert one to the other:

```sql
-- convert the order-side sku into an integer item_code to meet the inventory side
SELECT ol.order_line_id,
       ol.sku,
       inv.warehouse_id,
       inv.quantity_on_hand
FROM order_lines ol
JOIN inventory inv
  ON inv.item_code = CAST(SUBSTR(ol.sku, 5) AS INTEGER);

-- or convert the inventory-side item_code into a sku to meet the order side
SELECT si.shipment_item_id,
       si.sku,
       il.lot_number
FROM shipment_items si
JOIN inventory_lots il
  ON ('SKU-' || printf('%05d', il.item_code)) = si.sku;
```

Both produce the same matches as the bridge join. Prefer the bridge when you
also want product attributes (name, category, weight, price); prefer the
conversion when you already have the two line tables in hand and want to avoid an
extra join. Do not mix the two carelessly — pick one and keep the type on both
sides of the `ON` consistent.

#### 3.5 Which side of the split is each table on?

Every table that references a product does so through exactly one of the two
vocabularies. Tables that reference products only indirectly (through a parent
that carries the identifier) are listed as "neither."

| Table | Product reference |
|---|---|
| products | both (`product_id` = item_code, `sku`) — the bridge |
| product_categories | neither |
| product_attributes | via `product_id` (bridge-native, INTEGER) |
| price_history | via `product_id` (bridge-native, INTEGER) |
| customers | neither |
| customer_addresses | neither |
| orders | neither (product is on the lines) |
| order_lines | `sku` (TEXT) |
| order_status_history | neither |
| payments | neither |
| promotions | neither |
| order_promotions | neither |
| gift_cards | neither |
| gift_card_transactions | neither |
| carriers | neither |
| carrier_services | neither |
| facilities | neither |
| shipments | neither (product is on the items) |
| packages | neither |
| shipment_items | `sku` (TEXT) |
| shipment_legs | neither |
| tracking_events | neither |
| delivery_exceptions | neither |
| pick_tasks | neither |
| pick_lines | `item_code` (INTEGER) |
| returns | neither |
| return_lines | `sku` (TEXT) |
| carrier_invoices | neither |
| route_lanes | neither |
| warehouses | neither |
| warehouse_zones | neither |
| bins | neither |
| suppliers | neither |
| supplier_products | `item_code` (INTEGER) |
| supplier_contacts | neither |
| inventory | `item_code` (INTEGER) |
| inventory_lots | `item_code` (INTEGER) |
| inventory_transactions | `item_code` (INTEGER) |
| replenishment_orders | neither |
| replenishment_lines | `item_code` (INTEGER) |
| receipts | neither |
| receipt_lines | `item_code` (INTEGER) |
| supplier_invoices | neither |
| stock_transfers | neither |
| stock_transfer_lines | `item_code` (INTEGER) |
| inventory_adjustments | `item_code` (INTEGER) |
| cycle_counts | `item_code` (INTEGER) |

`product_attributes` and `price_history` carry `product_id` directly (they are
children of `products`), so they use the integer identity but never need
conversion — they join to `products` on `product_id` like any ordinary child.

---

### 4. Order Management join paths

**orders → order_lines → products → inventory.** The canonical path from an
order to what is physically in stock for the products it contains. Note the
bridge in the middle and the switch from `sku` to `item_code`.

```sql
SELECT o.order_id,
       p.sku,
       p.name,
       inv.warehouse_id,
       inv.quantity_on_hand - inv.quantity_allocated AS quantity_available
FROM orders o
JOIN order_lines ol ON ol.order_id  = o.order_id
JOIN products    p  ON p.sku        = ol.sku
JOIN inventory   inv ON inv.item_code = p.product_id
WHERE o.order_id = 1001;
```

**orders → payments** and **orders → order_promotions → promotions** are plain
`order_id` joins. A non-draft order has exactly one payment row (its `amount`
equals the `order_total`; there is no split tender in this dataset), but it may
have several promotions, so aggregate promotions before joining if you need one
row per order.

---

### 5. Fulfillment join paths

**orders → shipments → {packages, shipment_items, shipment_legs,
tracking_events, delivery_exceptions}.** A shipment hangs off an order and is the
hub for everything physical about the delivery.

```sql
-- everything about how one order shipped
SELECT o.order_id,
       s.shipment_id,
       s.tracking_number,
       pk.package_id,
       si.sku,
       si.quantity,
       lg.leg_seq,
       te.event_ts,
       de.exception_id
FROM orders o
JOIN shipments          s  ON s.order_id      = o.order_id
LEFT JOIN packages      pk ON pk.shipment_id  = s.shipment_id
LEFT JOIN shipment_items si ON si.shipment_id = s.shipment_id
LEFT JOIN shipment_legs  lg ON lg.shipment_id = s.shipment_id
LEFT JOIN tracking_events te ON te.shipment_id = s.shipment_id
LEFT JOIN delivery_exceptions de ON de.shipment_id = s.shipment_id
WHERE o.order_id = 1001;
```

In practice you rarely join all five children at once — each is one-to-many, so
the combination explodes into a cross-product of packages × items × legs ×
events × exceptions. Join only the child you need, and aggregate the others
separately. See the **Query Recipes and Pitfalls** section for the fan-out discussion.

**orders → returns → return_lines.** Returns reference the order; return lines
carry the `sku`.

```sql
SELECT o.order_id, r.rma_number, rl.sku, rl.quantity
FROM orders o
JOIN returns      r  ON r.order_id   = o.order_id
JOIN return_lines rl ON rl.return_id = r.return_id
WHERE o.order_id = 1001;
```

**orders → pick_tasks → pick_lines.** Picking is per warehouse and per order;
pick lines carry the integer `item_code`, so to show a product name you bridge
through `products` on `product_id`.

```sql
SELECT o.order_id,
       pt.warehouse_id,
       p.sku,
       p.name,
       pl.quantity
FROM orders o
JOIN pick_tasks pt ON pt.order_id = o.order_id
JOIN pick_lines pl ON pl.pick_id  = pt.pick_id
JOIN products   p  ON p.product_id = pl.item_code;
```

Notice the same order reaches its products two different ways: through
`order_lines.sku` and through `pick_lines.item_code`. That is the two-vocabulary
split in one order.

**shipment_legs.from/to_facility_id → facilities, and route_lanes between
facilities.** Legs move between facilities; route lanes describe the standard
transit between a facility pair. To attach the standard transit days for the
lane a leg used:

```sql
SELECT lg.leg_id,
       ff.name AS from_facility,
       tf.name AS to_facility,
       rl.distance_km,
       rl.standard_transit_days
FROM shipment_legs lg
JOIN facilities ff ON ff.facility_id = lg.from_facility_id
JOIN facilities tf ON tf.facility_id = lg.to_facility_id
LEFT JOIN route_lanes rl
       ON rl.origin_facility_id = lg.from_facility_id
      AND rl.dest_facility_id   = lg.to_facility_id
      AND rl.mode_code          = lg.mode_code;
```

Match the lane on origin, destination, and `mode_code` together — a facility
pair can be served by more than one transport mode, each its own lane.

---

### 6. Warehouse & Inventory join paths

**shipments.origin_warehouse_id → warehouses → {inventory, bins,
warehouse_zones}.** The origin warehouse of a shipment ties the fulfillment side
back to the physical building.

```sql
SELECT s.shipment_id,
       w.code AS warehouse_code,
       wz.zone_code,
       b.bin_code
FROM shipments s
JOIN warehouses      w  ON w.warehouse_id  = s.origin_warehouse_id
LEFT JOIN warehouse_zones wz ON wz.warehouse_id = w.warehouse_id
LEFT JOIN bins        b  ON b.warehouse_id  = w.warehouse_id
                        AND b.zone_id       = wz.zone_id
WHERE s.shipment_id = 5001;
```

**replenishment_orders → {suppliers, warehouses, replenishment_lines,
receipts → receipt_lines, supplier_invoices}.** The purchasing side. The PO
header links a supplier to a receiving warehouse; lines carry `item_code`;
receipts and their lines record what actually arrived; supplier invoices bill
the PO.

```sql
SELECT ro.repl_id,
       sup.name AS supplier,
       w.code   AS warehouse,
       rl.item_code,
       rl.qty_ordered,
       rl.qty_received,
       rcl.qty_received AS receipted_qty,
       si.invoice_number,
       si.amount
FROM replenishment_orders ro
JOIN suppliers            sup ON sup.supplier_id = ro.supplier_id
JOIN warehouses           w   ON w.warehouse_id  = ro.warehouse_id
LEFT JOIN replenishment_lines rl ON rl.repl_id   = ro.repl_id
LEFT JOIN receipts        rc  ON rc.repl_id       = ro.repl_id
LEFT JOIN receipt_lines   rcl ON rcl.receipt_id   = rc.receipt_id
                             AND rcl.item_code     = rl.item_code
LEFT JOIN supplier_invoices si ON si.repl_id      = ro.repl_id
WHERE ro.repl_id = 700;
```

As with shipments, joining all of these one-to-many children at once fans out;
pull one branch at a time when you need clean counts.

**supplier_products → suppliers, and supplier_products → products (via
item_code).** The supplier catalog links a supplier to the products they can
provide, at their own cost and lead time.

```sql
SELECT sup.name AS supplier,
       p.sku,
       p.name AS product,
       sp.supplier_sku,
       sp.unit_cost,
       sp.lead_time_days,
       sp.is_preferred
FROM supplier_products sp
JOIN suppliers sup ON sup.supplier_id = sp.supplier_id
JOIN products  p   ON p.product_id    = sp.item_code
WHERE sp.item_code = 42;   -- i.e. SKU-00042
```

`supplier_sku` is the supplier's own catalog code for the item and has nothing
to do with our `products.sku`; never join on `supplier_sku`.

---

### 7. Facilities vs warehouses — do not conflate

Two similar-sounding tables anchor the physical network, and they are separate
identifier spaces:

- **warehouses** are the fulfillment buildings that hold inventory. They are
  referenced by `origin_warehouse_id` on shipments and by `warehouse_id` on
  every inventory, pick, receipt, transfer, adjustment, and cycle-count table.
- **facilities** are the transit nodes (origin DCs, hubs, cross-docks, last-mile
  depots, ports) used by `shipment_legs` and `route_lanes`.

There is no foreign key between them and no shared surrogate id. A `warehouse_id`
is not a `facility_id`. If a question spans "where the stock is" and "how it
moved between facilities," you connect them through the shipment: the shipment's
`origin_warehouse_id` gives the warehouse, and the shipment's legs give the
facility path.

---

### 8. Nullable-key checklist

These foreign keys are nullable; join them with `LEFT JOIN` unless you
deliberately want to drop rows with no parent:

- `orders.ship_to_address_id`
- `product_categories.parent_category_id`
- `gift_cards.customer_id`
- `gift_card_transactions.order_id`
- `pick_lines.bin_id`
- `tracking_events.facility_id`
- `cycle_counts.bin_id`
- `supplier_invoices.repl_id`

And these non-key date columns are commonly NULL and gate lifecycle logic
(covered in the **Lifecycle and Statuses** section and the **Exclusions, Reporting Conventions, and Data Quality** section):
`shipments.delivered_date`, `shipments.promised_date`, `orders.promised_date`,
`returns.received_date`, `replenishment_orders.received_date`,
`shipment_legs.arrived_ts`, `delivery_exceptions.resolved_ts`,
`pick_tasks.completed_ts`, `payments.paid_date`, and the various invoice
`paid_date` columns.

---

### 9. Quick reference — every table's keys at a glance

| Table | PK | Foreign keys (→ referenced table) |
|---|---|---|
| product_categories | category_id | parent_category_id→product_categories |
| products | product_id | category_id→product_categories |
| product_attributes | attribute_id | product_id→products |
| price_history | price_history_id | product_id→products |
| customers | customer_id | — |
| customer_addresses | address_id | customer_id→customers |
| orders | order_id | customer_id→customers; ship_to_address_id→customer_addresses |
| order_lines | order_line_id | order_id→orders; sku→products.sku *(logical)* |
| order_status_history | history_id | order_id→orders |
| payments | payment_id | order_id→orders |
| promotions | promotion_id | — |
| order_promotions | order_promotion_id | order_id→orders; promotion_id→promotions |
| gift_cards | gift_card_id | customer_id→customers *(NULL)* |
| gift_card_transactions | gc_txn_id | gift_card_id→gift_cards; order_id→orders *(NULL)* |
| carriers | carrier_id | — |
| carrier_services | service_id | carrier_id→carriers |
| facilities | facility_id | — |
| shipments | shipment_id | order_id→orders; carrier_id→carriers; service_id→carrier_services; origin_warehouse_id→warehouses |
| packages | package_id | shipment_id→shipments |
| shipment_items | shipment_item_id | shipment_id→shipments; package_id→packages; order_line_id→order_lines; sku→products.sku *(logical)* |
| shipment_legs | leg_id | shipment_id→shipments; from_facility_id→facilities; to_facility_id→facilities |
| tracking_events | event_id | shipment_id→shipments; facility_id→facilities *(NULL)* |
| delivery_exceptions | exception_id | shipment_id→shipments |
| pick_tasks | pick_id | warehouse_id→warehouses; order_id→orders |
| pick_lines | pick_line_id | pick_id→pick_tasks; bin_id→bins *(NULL)*; item_code→products.product_id *(logical)* |
| returns | return_id | order_id→orders |
| return_lines | return_line_id | return_id→returns; sku→products.sku *(logical)* |
| carrier_invoices | carrier_invoice_id | carrier_id→carriers |
| route_lanes | lane_id | origin_facility_id→facilities; dest_facility_id→facilities |
| warehouses | warehouse_id | — |
| warehouse_zones | zone_id | warehouse_id→warehouses |
| bins | bin_id | warehouse_id→warehouses; zone_id→warehouse_zones |
| suppliers | supplier_id | — |
| supplier_products | supplier_product_id | supplier_id→suppliers; item_code→products.product_id *(logical)* |
| supplier_contacts | contact_id | supplier_id→suppliers |
| inventory | inventory_id | warehouse_id→warehouses; item_code→products.product_id *(logical)* |
| inventory_lots | lot_id | warehouse_id→warehouses; item_code→products.product_id *(logical)* |
| inventory_transactions | txn_id | warehouse_id→warehouses; item_code→products.product_id *(logical)* |
| replenishment_orders | repl_id | supplier_id→suppliers; warehouse_id→warehouses |
| replenishment_lines | repl_line_id | repl_id→replenishment_orders; item_code→products.product_id *(logical)* |
| receipts | receipt_id | repl_id→replenishment_orders; warehouse_id→warehouses |
| receipt_lines | receipt_line_id | receipt_id→receipts; item_code→products.product_id *(logical)* |
| supplier_invoices | supplier_invoice_id | supplier_id→suppliers; repl_id→replenishment_orders *(NULL)* |
| stock_transfers | transfer_id | from_warehouse_id→warehouses; to_warehouse_id→warehouses |
| stock_transfer_lines | transfer_line_id | transfer_id→stock_transfers; item_code→products.product_id *(logical)* |
| inventory_adjustments | adjustment_id | warehouse_id→warehouses; item_code→products.product_id *(logical)* |
| cycle_counts | count_id | warehouse_id→warehouses; bin_id→bins *(NULL)*; item_code→products.product_id *(logical)* |

For the meaning of every `_code` / `status` column referenced above — which
code set each column uses and the values in each set — see the **Code
Dictionary** section. For reporting rules that depend on these keys — excluding
internal test orders, revenue definitions, on-time delivery, availability — see
the **Exclusions, Reporting Conventions, and Data Quality** section and the
**Metrics and Definitions** section.

---

## Code Dictionary

This is the authoritative reference for every coded (integer-valued) column in the
warehouse. Where a column stores a small integer that stands for a human-readable
label — a status, a type, a reason, a channel — the mapping from that integer to its
meaning lives **here and only here**. No other document restates these integer values;
they all point back to this file.

The dataset models a mid-size 3PL / omnichannel retail logistics operator. All money is
in **US dollars** (two decimals), all weights are in **kilograms**, all dates are ISO
`YYYY-MM-DD`, and the reporting "today" is **2024-12-31**. The physical store is SQLite,
so these codes are plain `INTEGER` columns with no database-level enum or check
constraint — the meaning is a convention documented here, not enforced by the engine.

---

### How to use this dictionary

Reading a coded column is a **two-step lookup**, by design:

1. **Which code set does this column use?** A topic/domain doc — for orders and payments,
   for shipping and fulfillment, for warehouse and inventory — tells you which *code set*
   a given `table.column` draws from. The column name alone is not enough (see the warning
   below).
2. **What do the integers mean?** Come here. Find the named code set, and read the
   integer → label → meaning table.

So a question like "how many orders are `confirmed`?" resolves as: the orders topic doc
says `orders.status` uses the **ORDER_STATUS** code set → this dictionary says
ORDER_STATUS value `3` is `confirmed` → filter `orders.status = 3`.

#### Same-named status columns are NOT the same code set

The single most important thing to internalize: a column named `status` or `status_code`
means something **different in every table**. There is no global status enum. `status = 4`
means `fulfilled` on an order, `out_for_delivery` on a shipment, `completed` on a pick
task, `received` on a replenishment order, `refunded` on a return, `paid` on an invoice,
and `void` on a gift card. Decoding one table's status with another table's mapping
produces answers that are plausible and wrong.

Because that is so easy to get wrong, here is the **complete status-family index** —
every status/status_code column, and the code set it maps to — collected in one place.
Treat this table as step 1 of the lookup for any status column:

| Table.column | Code set |
|---|---|
| `orders.status` | ORDER_STATUS |
| `order_status_history.status` | ORDER_STATUS |
| `shipments.status` | SHIP_STATUS |
| `shipment_legs.status` | LEG_STATUS |
| `returns.status` | RETURN_STATUS |
| `replenishment_orders.status` | PO_STATUS |
| `payments.status_code` | PAYMENT_STATUS |
| `pick_tasks.status_code` | PICK_STATUS |
| `gift_cards.status_code` | GIFTCARD_STATUS |
| `suppliers.status_code` | SUPPLIER_STATUS |
| `supplier_invoices.status_code` | INVOICE_STATUS |
| `carrier_invoices.status_code` | INVOICE_STATUS |
| `stock_transfers.status_code` | TRANSFER_STATUS |
| `cycle_counts.status_code` | CYCLE_COUNT_STATUS |

Notice that the terminal ("done") integer is not consistent: orders finish at `4`,
shipments at `5`, replenishment orders at `4`, legs at `3`, transfers at `3`, picks at
`4`, returns at `4`. The lifecycle narrative behind each of these — which states are
entry states, which are terminal, and how a row moves between them — lives in
the **Lifecycle and Statuses** section. This dictionary gives you the *values*; that section gives
you the *flow*.

Other cross-references you will want:

- **Keys and identifier vocabularies** (the SKU vs. `item_code` split, and every PK/FK):
  the **Identifiers and Keys** section.
- **The `internal_test` exclusion** and other data-quality carve-outs:
  the **Exclusions, Reporting Conventions, and Data Quality** section.
- **Metric definitions** built on these codes (delivered-late, below-reorder-point,
  recognized revenue, and so on): the **Metrics and Definitions** section.

---

### Domain 1 — Order Management code sets

#### Code: CUSTOMER_SEGMENT

Classifies a customer by the kind of buyer they are. Segment drives pricing tiers,
payment terms eligibility (for example, net-terms billing is typically offered to
business and government segments, not consumers), and how the account is serviced.

| Value | Label | Meaning |
|---|---|---|
| 1 | consumer | An individual retail shopper buying for personal use. The default and highest-volume segment. |
| 2 | small_business | A small commercial buyer — a sole proprietor or small company — purchasing for business use, often in modestly larger quantities than a consumer. |
| 3 | enterprise | A large corporate account, usually with negotiated pricing, dedicated account handling, and higher order values. |
| 4 | government | A public-sector buyer (agency, municipality, or similar). Often carries specific procurement, invoicing, and net-terms requirements. |

**Used by:** `customers.segment_code`.

#### Code: ADDRESS_TYPE

Describes the role an address plays on a customer's account. A single customer can hold
several addresses of different types.

| Value | Label | Meaning |
|---|---|---|
| 1 | billing | Address used for billing and payment/invoice correspondence. |
| 2 | shipping | Address goods are physically delivered to. Referenced by `orders.ship_to_address_id`. |
| 3 | both | A single address that serves as both the billing and shipping address. |

**Used by:** `customer_addresses.address_type_code`.

**Note:** `orders.ship_to_address_id` points at a specific `customer_addresses` row; when
resolving where an order shipped, a valid ship-to address will be of type `shipping (2)`
or `both (3)`.

#### Code: ORDER_STATUS

The lifecycle state of a sales order. This is the canonical order-fulfillment progression
from creation through to a terminal outcome.

| Value | Label | Meaning |
|---|---|---|
| 1 | draft | Order has been started but not yet submitted — a shopping cart or unconfirmed order. No commitment has been made and no fulfillment happens. |
| 2 | placed | The customer has submitted the order. It is recorded but not yet validated/accepted by the business (e.g. payment authorization or stock check may still be pending). |
| 3 | confirmed | The order has been accepted and committed to — payment authorized and inventory earmarked — and is cleared to be picked and shipped. |
| 4 | fulfilled | The order has been completely shipped. This is the normal terminal success state; a fulfilled order has at least one shipment. |
| 5 | cancelled | The order was terminated before fulfillment. No goods ship. A cancelled order has no shipments. |
| 6 | returned | Goods that were fulfilled have been sent back by the customer (in whole or in part). This state reflects a post-fulfillment reversal and connects to the `returns` records. |

**Used by:** `orders.status`, and `order_status_history.status` (the timestamped audit
trail of every state an order passed through).

**Ordering / terminal notes:** The natural progression is `1 → 2 → 3 → 4`. `fulfilled (4)`
is the success terminal; `cancelled (5)` is an early terminal (reachable from draft/placed/
confirmed before shipment); `returned (6)` is a post-fulfillment terminal. Only
`fulfilled (4)` guarantees one or more shipments exist; `draft (1)` and `cancelled (5)`
never have shipments. See the **Lifecycle and Statuses** section for the full state machine.

#### Code: ORDER_PRIORITY

The handling tier assigned to an order. Priority governs how urgently the order is
processed and shipped, and it also carries one non-production tier used for internal
tagging.

| Value | Label | Meaning |
|---|---|---|
| 1 | standard | Normal handling and shipping speed. The default tier for most orders. |
| 2 | expedited | Faster-than-standard handling, prioritized ahead of standard work in the queue. |
| 3 | rush | Highest customer-facing urgency; processed and shipped as fast as possible. |
| 7 | internal_test | The tier used to tag internal, QA, and test orders rather than real customer demand. |

**Used by:** `orders.priority_code`.

**Note on `internal_test (7)`:** These are orders created for internal, QA, or test
purposes rather than genuine customer purchases. They otherwise look like ordinary orders
— they carry normal customers, amounts, channels, and can even have shipments — so there
is no other column that distinguishes them; the `priority_code = 7` tag is the only
signal. **Standard reporting excludes `internal_test` orders** (revenue, order counts, and
any customer-facing metric). Treat them as out of scope for business reporting unless a
question is explicitly about the test tier itself. The exact exclusion rule and its
rationale are documented in the **Exclusions, Reporting Conventions, and Data Quality** section; downstream metric
definitions in the **Metrics and Definitions** section apply this exclusion by default.

The real customer-facing tiers are `1 standard`, `2 expedited`, and `3 rush`. Note the
gap between `3` and `7` is intentional — `internal_test` is deliberately numbered apart
from the real tiers so it is never mistaken for the "most urgent" tier.

#### Code: ORDER_CHANNEL

The sales channel through which an order originated. Channel supports omnichannel
reporting — comparing web against app against store and marketplace performance.

| Value | Label | Meaning |
|---|---|---|
| 1 | web | Placed on the company's own desktop/browser storefront. |
| 2 | mobile_app | Placed through the company's native mobile application. |
| 3 | phone | Taken by a call-center or sales agent over the phone. |
| 4 | marketplace | Placed on a third-party marketplace (e.g. a large online marketplace) and routed to us for fulfillment. |
| 5 | in_store | Placed at a physical retail location — a point-of-sale or in-store order. |

**Used by:** `orders.channel_code`.

#### Code: PROMO_TYPE

The mechanic of a promotion — how the discount is calculated. The `promotions.value`
column is interpreted according to this type.

| Value | Label | Meaning |
|---|---|---|
| 1 | percent_off | A percentage discount off the order or item price; `value` is the percentage. |
| 2 | amount_off | A fixed dollar amount off; `value` is the dollar amount deducted. |
| 3 | bogo | Buy-one-get-one style promotion; a qualifying purchase unlocks a free or discounted additional unit. |
| 4 | free_shipping | Shipping charges are waived; the merchandise price is unchanged. |

**Used by:** `promotions.promo_type_code`.

**Note:** The actual dollar discount applied to a given order is recorded on
`order_promotions.discount_amount`, not derived from `value` at read time — so use the
booked `discount_amount` for realized-discount reporting and `promo_type_code` to
categorize the promotion.

#### Code: PAYMENT_METHOD

How a payment against an order was tendered. Each non-draft order has a single
payment row (one tender; there is no split tender in this dataset).

| Value | Label | Meaning |
|---|---|---|
| 1 | credit_card | Paid by credit card. |
| 2 | debit_card | Paid by debit card. |
| 3 | paypal | Paid through a PayPal-style third-party wallet. |
| 4 | gift_card | Paid using a stored-value gift card (see the gift-card code sets below). |
| 5 | net_terms | Invoiced on credit terms (e.g. net-30), typically for business/enterprise/government accounts rather than consumers. |
| 6 | wire | Paid by bank wire transfer, typically for large or business transactions. |

**Used by:** `payments.method_code`.

#### Code: PAYMENT_STATUS

The state of an individual payment transaction. This tracks the money movement for a
payment, which is distinct from the order's own fulfillment status.

| Value | Label | Meaning |
|---|---|---|
| 1 | authorized | Funds have been authorized/held but not yet captured (charged). Common right after order placement. |
| 2 | captured | Funds have been captured — the charge has settled and the money is collected. This is the normal "paid" state. |
| 3 | refunded | A previously captured amount has been returned to the customer, in whole or in part. |
| 4 | voided | An authorization was cancelled before capture; no money changed hands. |
| 5 | failed | The payment attempt was declined or errored and did not succeed. |

**Used by:** `payments.status_code`.

**Ordering / terminal notes:** `authorized (1) → captured (2)` is the successful path;
`captured (2) → refunded (3)` is the reversal path. `voided (4)` and `failed (5)` are
unsuccessful terminals in which no funds are ultimately collected. For "money actually
collected," `captured (2)` is the anchor state.

#### Code: GIFTCARD_STATUS

The state of a stored-value gift card, tracking whether it can still be spent.

| Value | Label | Meaning |
|---|---|---|
| 1 | active | The card is live and has a spendable balance. |
| 2 | redeemed | The card has been partially spent down but still carries a positive remaining balance. |
| 3 | expired | The card has passed its validity period and can no longer be used. |
| 4 | void | The card has been cancelled/invalidated administratively (e.g. issued in error or fraud). |

**Used by:** `gift_cards.status_code`.

**Note:** `active (1)` and `redeemed (2)` both carry a spendable `current_balance`
(a `redeemed` card has been spent against but still holds a positive balance);
`expired (3)` and `void (4)` are non-spendable terminals with a zero balance.

#### Code: GIFTCARD_TXN_TYPE

The kind of movement recorded on a gift card's transaction ledger
(`gift_card_transactions`). Each row raises or lowers the card's balance.

| Value | Label | Meaning |
|---|---|---|
| 1 | issue | Initial issuance of the card — establishes the opening balance. |
| 2 | redeem | Value spent down from the card, reducing its balance. `order_id` is NULL on these rows in this dataset — a redeem is not linked to a specific order. |
| 3 | reload | Additional value added to an existing card. Increases the balance. |
| 4 | refund | Value credited back onto the card, e.g. from a returned order. Increases the balance. |

**Used by:** `gift_card_transactions.txn_type_code`.

**Note:** `issue`, `reload`, and `refund` add value; `redeem` removes value.
`order_id` is NULL on every `gift_card_transactions` row in this dataset (all
types), so a `redeem` is not tied to a specific order via `order_id`.

---

### Domain 2 — Fulfillment code sets

#### Code: SERVICE_LEVEL

The shipping service tier of a carrier service (`carrier_services`), describing the
speed/mode class the customer or business selected.

| Value | Label | Meaning |
|---|---|---|
| 1 | ground | Standard ground delivery — the slowest and least expensive parcel tier. |
| 2 | two_day | Guaranteed two-day delivery. |
| 3 | overnight | Next-day / overnight delivery — the fastest parcel tier. |
| 4 | economy | A slower, cost-optimized service below ground (e.g. deferred/economy delivery). |
| 5 | freight | Heavy or palletized freight service, used for large/bulk shipments rather than parcels. |

**Used by:** `carrier_services.service_level_code`.

#### Code: FACILITY_TYPE

The role a facility plays in the transportation network. Facilities are the nodes that
shipment legs move between (`shipment_legs.from_facility_id` / `to_facility_id`) and that
route lanes connect.

| Value | Label | Meaning |
|---|---|---|
| 1 | origin_dc | An origin distribution center — a facility where shipments originate and orders are fulfilled from stock. |
| 2 | hub | A consolidation/sortation hub where freight from many origins is aggregated and re-sorted onward. |
| 3 | cross_dock | A cross-dock facility where inbound freight is transferred directly to outbound transport with little or no storage — goods flow through rather than being warehoused. |
| 4 | last_mile_depot | A local delivery depot from which final last-mile delivery to the customer is performed. |
| 5 | port | A sea/air port node used for international or long-haul ocean/air movements and customs handling. |

**Used by:** `facilities.facility_type_code`.

**Note:** A `cross_dock (3)` is specifically about flow-through — inbound is matched to
outbound and moved across the dock without being put away into storage — which is why it
differs from a `hub (2)` (which sorts) and from an `origin_dc (1)` (which holds inventory
and picks orders).

#### Code: SHIP_STATUS

The delivery state of a shipment. This is the customer-facing shipment lifecycle from
label creation to a terminal outcome.

| Value | Label | Meaning |
|---|---|---|
| 1 | label_created | A shipping label has been generated but the carrier has not yet taken possession. The shipment exists on paper. |
| 2 | picked_up | The carrier has collected the shipment; it has entered the carrier network. |
| 3 | in_transit | The shipment is moving through the carrier network between facilities. |
| 4 | out_for_delivery | The shipment is on the final delivery vehicle and expected to be delivered that day. |
| 5 | delivered | The shipment has been successfully delivered to the destination. Normal terminal success state. |
| 6 | exception | The shipment hit a problem (delay, damage, address issue, etc.) that interrupted normal delivery. Details are captured in `delivery_exceptions`. |
| 7 | lost | The shipment is confirmed lost in the network and will not be delivered. Terminal failure. |

**Used by:** `shipments.status`.

**Ordering / terminal notes:** The happy path is `1 → 2 → 3 → 4 → 5`. `delivered (5)` is
the terminal success; `lost (7)` is a terminal failure. `exception (6)` is not necessarily
terminal — a shipment can recover from an exception back into transit and go on to
deliver. **A delivered-late shipment is `status = 5 (delivered)` AND
`delivered_date > promised_date`** — see the **Metrics and Definitions** section. Note the
terminal integer here is `5`, unlike orders (`4`); do not carry one over to the other.

#### Code: PACKAGING_TYPE

The physical packaging of a package within a shipment (`packages`). Drives dimensional
and handling considerations.

| Value | Label | Meaning |
|---|---|---|
| 1 | box | A standard corrugated box. |
| 2 | envelope | A flat envelope/mailer for small, light items. |
| 3 | pallet | A palletized unit load, used for bulk or freight shipments. |
| 4 | tube | A tube for long, rolled items. |
| 5 | crate | A rigid crate for heavy, fragile, or oversized goods. |

**Used by:** `packages.packaging_type_code`.

#### Code: TRANSPORT_MODE

The mode of transport for a movement. Applies both to individual shipment legs and to the
standing route lanes between facilities.

| Value | Label | Meaning |
|---|---|---|
| 1 | truck | Road/trucking movement. The workhorse mode for domestic legs. |
| 2 | rail | Rail freight, typically for long-haul bulk movements. |
| 3 | air | Air freight, for fast or long-distance movements. |
| 4 | ocean | Ocean freight, for international/long-haul bulk sea movements. |
| 5 | parcel | Small-parcel carrier movement (the final delivery mode for most consumer orders). |

**Used by:** `shipment_legs.mode_code`, `route_lanes.mode_code`.

#### Code: LEG_STATUS

The state of a single leg of a shipment's journey (`shipment_legs`). A shipment can have
multiple sequential legs (`leg_seq`), each moving between two facilities.

| Value | Label | Meaning |
|---|---|---|
| 1 | pending | The leg is planned but has not yet started; `departed_ts` is scheduled but the movement has not begun. |
| 2 | in_progress | The leg is currently underway — the freight has departed the origin facility and not yet arrived at the destination. |
| 3 | completed | The leg has finished; the freight arrived at the destination facility (`arrived_ts` populated). Terminal success. |
| 4 | failed | The leg did not complete successfully (e.g. aborted or disrupted). Terminal failure. |

**Used by:** `shipment_legs.status`.

**Ordering / terminal notes:** `pending (1) → in_progress (2) → completed (3)` is the
normal path. `completed (3)` is the terminal success state for a leg — note again this is
`3`, distinct from the shipment's own `delivered (5)`. `failed (4)` is a terminal failure.

#### Code: TRACK_EVENT

The type of a tracking event recorded against a shipment (`tracking_events`). These are
the discrete scan/status milestones that accumulate over a shipment's life; a shipment
has many event rows over time.

| Value | Label | Meaning |
|---|---|---|
| 1 | created | The shipment/tracking record was created (label generated). |
| 2 | departed | The shipment departed a facility. |
| 3 | arrived | The shipment arrived at a facility. |
| 4 | customs_hold | The shipment was held at customs (typical on international movements). |
| 5 | delivered | The shipment was delivered to the destination — the successful final event. |
| 6 | delivery_failed | A delivery attempt failed (e.g. recipient unavailable, access problem). |
| 7 | return_to_sender | The shipment is being returned to the sender after failed delivery or refusal. |

**Used by:** `tracking_events.event_code`.

**Note:** Tracking events are a *time series* of milestones, not a single status —
`departed (2)` and `arrived (3)` can each occur multiple times as a shipment passes
through successive facilities. To read a shipment's current overall state use
`shipments.status` (SHIP_STATUS); use `tracking_events` for the granular history and to
detect events like `customs_hold (4)` or `delivery_failed (6)`.

#### Code: EXCEPTION_TYPE

The category of a delivery exception (`delivery_exceptions`) — why a shipment was
disrupted. Exceptions are logged with a `reported_ts` and, once handled, a `resolved_ts`.

| Value | Label | Meaning |
|---|---|---|
| 1 | weather_delay | Delivery delayed by weather conditions. |
| 2 | address_issue | A problem with the delivery address (incomplete, incorrect, or unlocatable). |
| 3 | damaged | The shipment was found damaged in the network. |
| 4 | missed_delivery | A delivery attempt was made but not completed (recipient unavailable, no safe drop, etc.). |
| 5 | customs | A customs-related holdup on an international shipment. |
| 6 | mechanical | A mechanical/equipment failure in transport caused the disruption. |

**Used by:** `delivery_exceptions.exception_type_code`.

**Note:** An open exception has a null `resolved_ts`; a resolved one is timestamped.
Exceptions relate to (but are not the same as) the shipment being in `SHIP_STATUS =
exception (6)`.

#### Code: PICK_STATUS

The state of a warehouse pick task (`pick_tasks`) — the job of physically picking an
order's items from bins. One pick task belongs to one order and one warehouse.

| Value | Label | Meaning |
|---|---|---|
| 1 | queued | The pick task has been created and is waiting to be worked. |
| 2 | assigned | The task has been assigned to a picker but picking has not started. |
| 3 | picking | The picker is actively pulling items from bins. |
| 4 | completed | All required items were picked successfully. Terminal success (`completed_ts` populated). |
| 5 | short | Picking finished but could not fully satisfy the demand — some quantity was unavailable (a "short pick"). Terminal, but incomplete. |

**Used by:** `pick_tasks.status_code`.

**Ordering / terminal notes:** `queued (1) → assigned (2) → picking (3) → completed (4)`
is the normal flow. `completed (4)` is the success terminal (again `4`, matching orders
but not shipments/legs). `short (5)` is a terminal outcome where the pick could not be
fully filled — useful for identifying stock/availability problems.

#### Code: RETURN_REASON

Why a customer initiated a return (`returns`). Captured at the return-header level.

| Value | Label | Meaning |
|---|---|---|
| 1 | defective | The item was faulty / did not work as intended. |
| 2 | wrong_item | The customer received the wrong product. |
| 3 | no_longer_needed | The customer changed their mind or no longer wants the item (a non-fault return). |
| 4 | damaged_in_transit | The item arrived damaged due to shipping. |
| 5 | late_delivery | The item arrived too late and was returned for that reason. |

**Used by:** `returns.reason_code`.

#### Code: RETURN_STATUS

The processing state of a return (`returns`), from customer request through to a terminal
resolution.

| Value | Label | Meaning |
|---|---|---|
| 1 | requested | The customer has requested a return; it is not yet approved. |
| 2 | authorized | The return has been approved and an RMA issued; the customer may send the goods back. |
| 3 | received | The returned goods have physically arrived back at a facility (`received_date` populated). |
| 4 | refunded | The return is complete and the customer has been refunded. Normal terminal success. |
| 5 | rejected | The return was denied (e.g. outside policy, not eligible). Terminal, no refund. |

**Used by:** `returns.status`.

**Ordering / terminal notes:** `requested (1) → authorized (2) → received (3) →
refunded (4)` is the normal flow. `refunded (4)` is the success terminal (note `4`, not
matching the shipment terminal). `rejected (5)` is a terminal denial. A return typically
gets a `disposition_code` (see below) once the goods are received.

#### Code: RETURN_DISPOSITION

What is done with the physical goods after a return is received (`returns.disposition_code`).
This column is nullable — a disposition is only decided once goods are in hand, so
early-stage returns may have none.

| Value | Label | Meaning |
|---|---|---|
| 1 | restock | The item is in sellable condition and is returned to inventory to be sold again. |
| 2 | refurbish | The item needs repair/refurbishment before it can be resold. |
| 3 | scrap | The item cannot be recovered and is discarded/written off. |
| 4 | return_to_supplier | The item is sent back to the supplier/vendor (e.g. defective stock returned to source). |

**Used by:** `returns.disposition_code` (nullable).

#### Code: ITEM_CONDITION

The physical condition grade of a returned or received item. Used both on return lines
(assessing what came back) and on receipt lines (grading inbound supplier stock).

| Value | Label | Meaning |
|---|---|---|
| 1 | new | Unused, sellable-as-new condition. |
| 2 | opened | Opened or used but otherwise intact — typically not sellable as new. |
| 3 | damaged | Physically damaged. |
| 4 | defective | Functionally faulty / does not work. |

**Used by:** `return_lines.condition_code` (nullable), `receipt_lines.condition_code`.

**Note:** Condition and return-disposition are related but distinct — condition describes
the state the item is *in*, while disposition records the decision about *what to do* with
it. Typically only `new (1)` return goods are candidates for `restock`.

---

### Domain 3 — Warehouse & Inventory code sets

#### Code: ZONE_TYPE

The functional type of a zone within a warehouse (`warehouse_zones`). Zones organize a
warehouse into areas dedicated to different operations, and bins live inside zones.

| Value | Label | Meaning |
|---|---|---|
| 1 | receiving | The inbound area where incoming freight is received and checked in. |
| 2 | storage | The bulk/reserve storage area where inventory is held. |
| 3 | picking | The forward/active area organized for efficient order picking. |
| 4 | shipping | The outbound area where picked orders are packed and staged for carrier pickup. |
| 5 | cold_storage | A temperature-controlled area for goods requiring refrigeration/freezing. |

**Used by:** `warehouse_zones.zone_type_code`.

#### Code: SUPPLIER_STATUS

The relationship state of a supplier (`suppliers`) — whether the company is currently
buying from them.

| Value | Label | Meaning |
|---|---|---|
| 1 | active | An approved supplier in good standing; purchase orders may be placed. |
| 2 | on_hold | Temporarily suspended (e.g. quality or commercial issue); no new orders while on hold. |
| 3 | terminated | The relationship has been ended; the supplier is no longer used. Terminal. |
| 4 | pending_approval | A prospective supplier being onboarded/vetted; not yet cleared to order from. |

**Used by:** `suppliers.status_code`.

**Note:** Only `active (1)` suppliers are normally orderable. `pending_approval (4)` is a
pre-active onboarding state, and `terminated (3)` is the end-of-relationship terminal.

#### Code: PO_STATUS

The state of a replenishment/purchase order (`replenishment_orders`) — a purchase order
placed on a supplier to restock a warehouse. Named PO_STATUS because these are the
company's inbound purchase orders.

| Value | Label | Meaning |
|---|---|---|
| 1 | draft | The PO is being prepared and has not been issued to the supplier. |
| 2 | open | The PO has been issued to the supplier and is awaiting fulfillment; nothing received yet. |
| 3 | partial | Some but not all of the ordered quantity has been received. |
| 4 | received | The PO has been fully received. Normal terminal success (`received_date` populated). |
| 5 | cancelled | The PO was cancelled before completion. Terminal, no (further) receipt. |

**Used by:** `replenishment_orders.status`.

**Ordering / terminal notes:** `draft (1) → open (2) → partial (3) → received (4)` is the
normal flow. `received (4)` is the success terminal (`4`, matching orders/picks but not
shipments). `cancelled (5)` is an early terminal. Receipts against a PO post to
`receipts`/`receipt_lines`, and the goods movement lands in `inventory_transactions`.

#### Code: INV_TXN_TYPE

The type of movement in the inventory ledger (`inventory_transactions`). This ledger is
the single running record of every quantity change at a warehouse; each row carries a
signed `quantity_delta` (positive = stock in, negative = stock out) and a
`reference_type`/`reference_id` pointing back to the source event.

| Value | Label | Meaning |
|---|---|---|
| 1 | receipt | Stock received in from a supplier PO. Increases on-hand (positive delta). |
| 2 | shipment | Stock shipped out to fulfill a customer order. Decreases on-hand (negative delta). |
| 3 | transfer_out | Stock leaving *this* warehouse on a stock transfer to another warehouse. Decreases on-hand at the origin (negative delta). |
| 4 | transfer_in | Stock arriving *at this* warehouse from a stock transfer out of another warehouse. Increases on-hand at the destination (positive delta). |
| 5 | adjustment | A manual inventory adjustment (correction, damage, theft, found stock, etc.). Delta can be positive or negative. |
| 6 | return_restock | Stock added back to inventory from a customer return that was dispositioned to restock. Increases on-hand (positive delta). |

**Used by:** `inventory_transactions.txn_type_code`.

**Note on `transfer_out (3)` vs `transfer_in (4)`:** A single stock transfer between two
warehouses generates *two* ledger rows — a `transfer_out (3)` at the sending warehouse and
a matching `transfer_in (4)` at the receiving warehouse. They are two halves of one
physical move; net company-wide inventory is unchanged, but each warehouse's on-hand
shifts. This is why summing `quantity_delta` for a single warehouse and summing it across
all warehouses give different (and both correct) answers. The header/line detail of the
transfer itself lives in `stock_transfers` / `stock_transfer_lines`; adjustments have
their own detail in `inventory_adjustments`; receipts in `receipts`/`receipt_lines`. The
`inventory_transactions` ledger is where all of them post their quantity effect.

#### Code: INVOICE_STATUS

The state of an accounts-payable invoice. Shared by two invoice tables — invoices we
receive from suppliers for goods, and invoices we receive from carriers for freight.

| Value | Label | Meaning |
|---|---|---|
| 1 | draft | The invoice record exists but has not been formally submitted/entered into AP. |
| 2 | submitted | The invoice has been submitted and is awaiting internal review/approval. |
| 3 | approved | The invoice has been approved for payment but not yet paid. |
| 4 | paid | The invoice has been paid (`paid_date` populated). Normal terminal success. |
| 5 | disputed | The invoice is under dispute (amount or validity in question) and is not being paid pending resolution. |

**Used by:** `supplier_invoices.status_code`, `carrier_invoices.status_code`.

**Ordering / terminal notes:** `draft (1) → submitted (2) → approved (3) → paid (4)` is
the normal flow. `paid (4)` is the success terminal. `disputed (5)` is an off-path state
that a submitted/approved invoice can enter; it may later resolve back toward payment or
be written off. For "outstanding payables," count invoices not yet `paid (4)`.

#### Code: TRANSFER_STATUS

The state of a stock transfer between two warehouses (`stock_transfers`) — an internal
inventory move, not a customer shipment.

| Value | Label | Meaning |
|---|---|---|
| 1 | requested | A transfer has been requested/created but goods have not yet shipped from the origin. |
| 2 | in_transit | Goods have shipped from the origin warehouse and are moving to the destination (`shipped_date` populated). |
| 3 | received | Goods have arrived and been received at the destination warehouse. Normal terminal success (`received_date` populated). |
| 4 | cancelled | The transfer was cancelled before completion. Terminal. |

**Used by:** `stock_transfers.status_code`.

**Ordering / terminal notes:** `requested (1) → in_transit (2) → received (3)` is the
normal flow. `received (3)` is the success terminal — note this is `3`, matching
shipment legs but **not** the shipment, order, pick, PO, or return terminals. `cancelled
(4)` is an early terminal. A completed transfer posts a `transfer_out (3)` at the origin
and a `transfer_in (4)` at the destination in `inventory_transactions` (see INV_TXN_TYPE).

#### Code: ADJ_REASON

Why a manual inventory adjustment was made (`inventory_adjustments`). Explains the
`quantity_delta` on each adjustment row.

| Value | Label | Meaning |
|---|---|---|
| 1 | cycle_count | The adjustment corrects on-hand to match a physical cycle count. |
| 2 | damage | Stock was written down because it was damaged and is no longer sellable. |
| 3 | theft | Stock was written down due to theft/shrinkage. |
| 4 | found | Previously unaccounted-for stock was found and added back to on-hand (positive delta). |
| 5 | correction | A general bookkeeping correction of the recorded quantity. |

**Used by:** `inventory_adjustments.reason_code`.

**Note:** `found (4)` typically carries a positive `quantity_delta`; `damage (2)` and
`theft (3)` typically carry negative deltas; `cycle_count (1)` and `correction (5)` can go
either way depending on whether the count/recheck was over or under. Every adjustment also
posts an `adjustment (5)` row to `inventory_transactions`.

#### Code: CYCLE_COUNT_STATUS

The state of a cycle-count task (`cycle_counts`) — a scheduled physical recount of a
specific item (and optionally bin) at a warehouse, used to keep recorded inventory honest.

| Value | Label | Meaning |
|---|---|---|
| 1 | scheduled | The count has been planned but not yet performed. |
| 2 | counted | The physical count has been taken (`counted_qty` recorded, `variance` = counted − system) but not yet reconciled into the books. |
| 3 | reconciled | The count is complete and any variance has been posted/adjusted into inventory. Terminal. |

**Used by:** `cycle_counts.status_code`.

**Ordering / terminal notes:** `scheduled (1) → counted (2) → reconciled (3)` is the
progression; `reconciled (3)` is the terminal state. When a count is reconciled with a
non-zero `variance`, the correcting movement appears in `inventory_adjustments` with
`reason_code = cycle_count (1)`, which in turn posts to the `inventory_transactions`
ledger.

---

### Quick index of every code set

For fast navigation, every code set defined in this dictionary and where it is consumed:

| Code set | Column(s) that use it |
|---|---|
| CUSTOMER_SEGMENT | `customers.segment_code` |
| ADDRESS_TYPE | `customer_addresses.address_type_code` |
| ORDER_STATUS | `orders.status`, `order_status_history.status` |
| ORDER_PRIORITY | `orders.priority_code` |
| ORDER_CHANNEL | `orders.channel_code` |
| PROMO_TYPE | `promotions.promo_type_code` |
| PAYMENT_METHOD | `payments.method_code` |
| PAYMENT_STATUS | `payments.status_code` |
| GIFTCARD_STATUS | `gift_cards.status_code` |
| GIFTCARD_TXN_TYPE | `gift_card_transactions.txn_type_code` |
| SERVICE_LEVEL | `carrier_services.service_level_code` |
| FACILITY_TYPE | `facilities.facility_type_code` |
| SHIP_STATUS | `shipments.status` |
| PACKAGING_TYPE | `packages.packaging_type_code` |
| TRANSPORT_MODE | `shipment_legs.mode_code`, `route_lanes.mode_code` |
| LEG_STATUS | `shipment_legs.status` |
| TRACK_EVENT | `tracking_events.event_code` |
| EXCEPTION_TYPE | `delivery_exceptions.exception_type_code` |
| PICK_STATUS | `pick_tasks.status_code` |
| RETURN_REASON | `returns.reason_code` |
| RETURN_STATUS | `returns.status` |
| RETURN_DISPOSITION | `returns.disposition_code` |
| ITEM_CONDITION | `return_lines.condition_code`, `receipt_lines.condition_code` |
| ZONE_TYPE | `warehouse_zones.zone_type_code` |
| SUPPLIER_STATUS | `suppliers.status_code` |
| PO_STATUS | `replenishment_orders.status` |
| INV_TXN_TYPE | `inventory_transactions.txn_type_code` |
| INVOICE_STATUS | `supplier_invoices.status_code`, `carrier_invoices.status_code` |
| TRANSFER_STATUS | `stock_transfers.status_code` |
| ADJ_REASON | `inventory_adjustments.reason_code` |
| CYCLE_COUNT_STATUS | `cycle_counts.status_code` |

When in doubt about which set a column uses, start from the topic/domain doc for that
column's subject area, confirm the code-set name, and return here for the integer values.
The lifecycle flows and terminal-state reasoning behind the status sets are in
the **Lifecycle and Statuses** section; the `internal_test` and other reporting exclusions are in
the **Exclusions, Reporting Conventions, and Data Quality** section.

---

## Lifecycle and Statuses

This document describes the lifecycle of every stateful entity in the warehouse:
the ordered states it moves through, which state means "done," which transitions
are allowed, and what each state means for the business. It is the reference you
reach for when a question involves "open," "completed," "still in progress,"
"delivered," "received," "in flight," "overdue," or any other status-driven
condition.

Everything here refers to coded states by their **symbolic label** (for example
`fulfilled`, `delivered`, `received`). The integer stored in the column and its
mapping to a label live in a single place — the **Code Dictionary** section. When you
write a filter you will use the integer from that dictionary; when you read and
reason, use the label. Each subsection names the **code set** that governs the
column so you can look it up.

### The one rule that prevents most status mistakes

Many tables have a column literally named `status` or `status_code`. **These are
not the same code set.** Each stateful table has its *own* code set, with its
own list of states and — critically — its own terminal "done" value. The
`status` on `orders` is decoded by ORDER_STATUS; the `status` on `shipments` is
decoded by SHIP_STATUS; the `status_code` on `pick_tasks` is decoded by
PICK_STATUS; and so on. There is no universal status decode.

Practically this means two things:

1. **Resolve the code set for the specific table before you filter.** The
   subsections below name the correct code set for each column, and
   the **Code Dictionary** section gives the integer values. Never reuse an integer you
   memorized for one table on another.

2. **The terminal ("complete") state differs by table.** An order is complete at
   `fulfilled`; a shipment is complete at `delivered`; a shipment leg at
   `completed`; a pick task at `completed`; a replenishment order at `received`;
   a stock transfer at `received`; a return at `refunded` (or the closed
   `rejected` branch). "Done" is not a single number you can carry from one table
   to another — a filter that means "delivered" on shipments means something
   entirely different if applied to orders or transfers.

A quick way to stay safe: treat every `status`/`status_code` filter as a
per-table lookup, exactly the way you already treat product identifiers as
`sku`-side vs `item_code`-side (see the **Identifiers and Keys** section).

A concrete illustration of why this matters: "delivered" and "received" and
"completed" and "fulfilled" all mean "the happy-path end of the process," but
they belong to different code sets and sit on different tables. If you write one
query for delivered shipments and then reuse the same integer to filter orders,
transfers, or picks, you will get a plausible-looking result set that is
answering the wrong question — the integer that means "delivered" under
SHIP_STATUS decodes to something entirely unrelated under ORDER_STATUS or
TRANSFER_STATUS. There is no shortcut around resolving the code set for the exact
column you are filtering.

A summary mapping of every status column to its code set is at the end of this
document.

---

### Lifecycle: Order

**Column:** `orders.status`  **Code set:** ORDER_STATUS
**History:** `order_status_history`

An order progresses through the following states, in label terms:

`draft` → `placed` → `confirmed` → `fulfilled`

with two off-ramps that can terminate an order:

- `cancelled` — the order was stopped before (or instead of) fulfillment.
- `returned` — a previously fulfilled order that has been fully returned.

**Meaning of each state.**

- `draft` — the order exists but has not been submitted by (or on behalf of) the
  customer. It is not yet a committed sale. Draft orders have no shipments.
- `placed` — the customer has submitted the order; it is a real demand signal but
  not yet validated/accepted by operations.
- `confirmed` — the order has been accepted and is eligible for fulfillment
  (payment authorized, stock allocated). It is in the pipeline but not yet
  shipped and completed.
- `fulfilled` — **the terminal "complete" state for the normal happy path.** A
  fulfilled order has been picked, shipped, and considered delivered/closed from
  the order's point of view. A fulfilled order has at least one shipment.
- `cancelled` — a terminal state reached instead of fulfillment. A cancelled
  order has no shipments.
- `returned` — a terminal state reached after fulfillment, indicating the order
  was returned. The return process itself is tracked separately in the `returns`
  tables (see the Return lifecycle below); this status is the order header's
  reflection of that outcome.

**What "complete" means.** For order-volume, revenue, and throughput reporting,
`fulfilled` is the completed-sale state. `cancelled` orders should generally be
excluded from revenue; `draft` orders are not yet real sales. Whether a
`returned` order counts toward gross vs net revenue is a metric-definition choice
covered in the **Metrics and Definitions** section. Note that the order status is the
header-level rollup; a partially-shipped or partially-returned situation is
described by the shipment and return records, not by a special order status.

**Allowed transitions.**

- `draft` → `placed` → `confirmed` → `fulfilled` is the standard forward path.
- Any pre-fulfillment state (`draft`, `placed`, `confirmed`) can move to
  `cancelled`.
- `fulfilled` → `returned` when a fulfilled order is returned.
- Terminal states (`fulfilled` once returned aside, `cancelled`, `returned`) are
  not expected to move forward again.

Orders are not required to have passed through every intermediate state
explicitly, but the ordering above is the business sequence.

In SQL, always filter the coded column against the integer value from
the **Code Dictionary** section for the ORDER_STATUS code set. The examples in this
document use a named placeholder (e.g. `:fulfilled`) to stand for that integer so
the label stays readable; substitute the dictionary value when you run the query.

```sql
-- Orders currently in the fulfilled (completed) state
SELECT COUNT(*) AS fulfilled_orders
FROM orders
WHERE status = :fulfilled;          -- ORDER_STATUS 'fulfilled' — see the Code Dictionary section

-- Orders that were cancelled after having been confirmed,
-- using the history trail to prove the earlier state existed
SELECT o.order_id
FROM orders o
WHERE o.status = :cancelled          -- ORDER_STATUS 'cancelled'
  AND EXISTS (
        SELECT 1 FROM order_status_history h
        WHERE h.order_id = o.order_id
          AND h.status = :confirmed  -- ORDER_STATUS 'confirmed'
  );
```

**How `order_status_history` records transitions.** Every meaningful status
change is appended to `order_status_history` as a row carrying the `order_id`,
the new `status` (decoded by ORDER_STATUS, same code set as the header), a
`changed_ts` timestamp, and an optional free-text `note` explaining the change.
This table is the audit trail: the `orders.status` column holds the *current*
state, while `order_status_history` holds the *sequence* of states with their
timestamps. Use it to answer "when was this order confirmed," "how long did it
sit in placed before confirmation," or "which orders were cancelled after being
confirmed." To get the current state from history, take the row with the latest
`changed_ts` per order — it should agree with `orders.status`. Example: time from
placement to fulfillment for an order is the gap between the `changed_ts` of its
`placed` row and its `fulfilled` row.

```sql
-- Days from placement to fulfillment per order (history-driven)
SELECT p.order_id,
       julianday(f.changed_ts) - julianday(p.changed_ts) AS days_to_fulfill
FROM order_status_history p
JOIN order_status_history f
  ON f.order_id = p.order_id
WHERE p.status = :placed              -- ORDER_STATUS 'placed'
  AND f.status = :fulfilled;          -- ORDER_STATUS 'fulfilled'
```

If an order legitimately revisited a state (rare, but possible via a correction
noted in `note`), pick the appropriate occurrence with `MIN`/`MAX` on
`changed_ts` rather than assuming exactly one row per state.

---

### Lifecycle: Payment

**Column:** `payments.status_code`  **Code set:** PAYMENT_STATUS

A payment attached to an order moves through these states (label terms):

- `authorized` — funds have been reserved on the payment instrument but not yet
  taken. This is the pre-capture hold.
- `captured` — the funds have actually been collected. This is the state that
  represents money received.
- `refunded` — a previously captured payment has been returned to the customer,
  in whole or in part.
- `voided` — an authorization that was released before capture; no money changed
  hands.
- `failed` — the payment attempt did not succeed (declined, error).

**Meaning and "complete."** There is no single "done" state; a payment is
resolved when it is `captured` (money in), `refunded` (money returned), `voided`
(hold released), or `failed` (no money). For "revenue actually collected"
questions, `captured` is the relevant state; `authorized` is only a hold and
should not be counted as collected. Each non-draft order has exactly one payment
row (no split tender in this dataset), and its `amount` equals the `order_total`,
so be explicit about which statuses you include. `paid_date` is populated once
funds have moved; it may be NULL for an `authorized`/`voided`/`failed` row.

**Typical transitions.** `authorized` → `captured` → `refunded` is the common
path for a completed-then-returned sale; `authorized` → `voided` for an order
that was cancelled before capture; a standalone `failed` for a declined attempt
that is then retried with a new payment row. See the **Pricing, Costs & Billing** section
for how payments relate to order totals, gift cards, and refunds.

```sql
-- Net collected per order: captured amounts less refunds
SELECT order_id,
       SUM(CASE WHEN status_code = :captured THEN amount ELSE 0 END)   -- PAYMENT_STATUS 'captured'
     - SUM(CASE WHEN status_code = :refunded THEN amount ELSE 0 END)   -- PAYMENT_STATUS 'refunded'
         AS net_collected
FROM payments
GROUP BY order_id;
```

Two cautions: do not treat `authorized` as collected money (it is only a hold),
and note that each non-draft order carries exactly one payment row (no split
tender in this dataset), so no per-order aggregation of payments is needed. Whether a refund reduces recognized
revenue is a definitional choice — follow the **Metrics and Definitions** section so the
number matches the company standard.

---

### Lifecycle: Gift card

**Column:** `gift_cards.status_code`  **Code set:** GIFTCARD_STATUS
**Ledger:** `gift_card_transactions` (**code set:** GIFTCARD_TXN_TYPE)

A gift card moves through these states (label terms):

- `active` — issued and usable; `current_balance` may be spent.
- `redeemed` — partially spent down; the card still carries a positive remaining balance.
- `expired` — passed its validity window without being fully used.
- `void` — cancelled/invalidated (for example, issued in error or reversed).

**Meaning and "complete."** `active` and `redeemed` cards can still be used to
pay — a `redeemed` card is one that has been spent against but still holds a
positive balance. `expired` and `void` are non-spendable terminal states (zero
balance), each with a different reason (lapsed, cancelled). `current_balance` vs
`initial_balance` tells you how much of the card has been consumed.

**The transaction ledger.** `gift_card_transactions` is an append-only ledger of
every movement on a card, typed by GIFTCARD_TXN_TYPE:

- `issue` — the card was created and its initial balance loaded.
- `redeem` — value was spent down from the card. `gift_card_transactions.order_id`
  is nullable and, in this dataset, is NULL on every row — a redeem is not linked
  to a specific order via `order_id`.
- `reload` — additional value was added to the card.
- `refund` — value was returned to the card (for example when an order paid by
  gift card is refunded).

Each transaction carries an `amount` and a `txn_ts`. The `gift_cards` row holds
the current rolled-up balance and status; the ledger holds the detailed history.
To reconcile a card, walk its ledger: `issue` and `reload` add, `redeem`
subtracts, `refund` adds back. See the **Pricing, Costs & Billing** section for gift-card
accounting against orders.

```sql
-- Rebuild a card's net balance from its ledger and compare to the header
SELECT gc.gift_card_id,
       gc.current_balance,
       SUM(CASE WHEN t.txn_type_code IN (:issue, :reload, :refund)
                THEN t.amount
                WHEN t.txn_type_code = :redeem
                THEN -t.amount
                ELSE 0 END) AS ledger_balance   -- GIFTCARD_TXN_TYPE labels
FROM gift_cards gc
JOIN gift_card_transactions t ON t.gift_card_id = gc.gift_card_id
GROUP BY gc.gift_card_id, gc.current_balance;
```

---

### Lifecycle: Shipment

**Column:** `shipments.status`  **Code set:** SHIP_STATUS

A shipment moves through these states (label terms):

`label_created` → `picked_up` → `in_transit` → `out_for_delivery` → `delivered`

with two off-path outcomes:

- `exception` — the shipment hit a problem in transit (see delivery exceptions
  below); it may recover or be resolved.
- `lost` — the shipment was lost and will not be delivered.

**Meaning of each state.**

- `label_created` — a shipping label exists and the shipment is registered, but
  the carrier has not yet taken possession.
- `picked_up` — the carrier has collected the shipment from origin.
- `in_transit` — the shipment is moving through the carrier network.
- `out_for_delivery` — the shipment is on the final vehicle to the customer.
- `delivered` — **the terminal "complete" state.** The shipment reached the
  customer. `delivered_date` is populated for delivered shipments.
- `exception` — a problem occurred (weather, address, damage, missed delivery,
  customs, mechanical). This is not necessarily terminal; the underlying issue is
  tracked in `delivery_exceptions`.
- `lost` — terminal failure; the shipment will not arrive.

**What "complete" means and the on-time rule.** `delivered` is the completed
state for a shipment. This is a different terminal value from the order's
`fulfilled` and from every other table's "done" — do not carry it across. A
shipment is **delivered late** when it is in the `delivered` state **and**
`delivered_date > promised_date`. On-time delivery counts a `delivered` shipment
where `delivered_date <= promised_date`. Shipments that are not yet `delivered`
have a NULL `delivered_date` and should not be counted as on-time or late; they
are simply still in flight (or in `exception`/`lost`). See
the **Metrics and Definitions** section for the exact on-time definition and
`fulfillment_and_shipping.md` for transit-time semantics.

```sql
-- Late deliveries: delivered AND arrived after the promise
SELECT COUNT(*) AS late_deliveries
FROM shipments
WHERE status = :delivered            -- SHIP_STATUS 'delivered'
  AND delivered_date > promised_date;

-- On-time rate over delivered shipments only
SELECT AVG(CASE WHEN delivered_date <= promised_date THEN 1.0 ELSE 0.0 END)
         AS on_time_rate
FROM shipments
WHERE status = :delivered;           -- SHIP_STATUS 'delivered'
```

Because `delivered_date` is NULL until a shipment is delivered, restricting to
the `delivered` state is what keeps in-flight shipments out of the on-time
denominator. Do not compute on-time over all shipments — the NULL comparison
would silently drop the undelivered ones and leave a denominator that is not what
you intended.

**Relationship to the order.** A `fulfilled` order has at least one shipment; a
`cancelled` or `draft` order has none. An order can in principle have more than
one shipment, so shipment-level and order-level counts are not interchangeable —
if a question asks "how many orders shipped," count distinct `order_id`, and if
it asks "how many shipments went out," count shipment rows. The two numbers can
legitimately differ.

**Edge cases in the shipment states.** The `exception` state is not part of the
linear forward path and is not by itself terminal: a shipment can enter
`exception` (for example after a weather delay or a missed delivery) and later
recover to `delivered`, or degrade to `lost`. Because of this, "problem
shipments" are better identified through the `delivery_exceptions` table (open
vs resolved) than by the SHIP_STATUS `exception` value alone, since a shipment
that had a problem and recovered will show `delivered` now but still carry a
resolved exception row. The `lost` state is genuinely terminal and, like an
undelivered shipment, has a NULL `delivered_date`; never count a `lost` shipment
as either on-time or late.

---

### Lifecycle: Shipment leg

**Column:** `shipment_legs.status`  **Code set:** LEG_STATUS

A shipment's journey is broken into ordered legs (`leg_seq`), each moving between
two facilities on a transport mode. A leg moves through these states (label
terms):

- `pending` — the leg is planned but has not started.
- `in_progress` — the leg is underway (departed, not yet arrived).
- `completed` — **the terminal "complete" state for a leg.** The leg finished;
  `arrived_ts` is populated.
- `failed` — the leg did not complete successfully.

**Meaning and "complete."** `completed` is the leg's done state — note this is a
*different* terminal label from the shipment's `delivered`. A shipment is
composed of multiple legs; the shipment is delivered when the physical journey
ends, but each individual leg has its own `completed`/`failed` outcome. A leg in
`pending` or `in_progress` has a NULL `arrived_ts`. To measure leg transit time,
use `arrived_ts - departed_ts` on `completed` legs; a NULL `arrived_ts` means the
leg has not finished and should be excluded from a transit-duration measure. Legs
are ordered by `leg_seq` within a shipment, so the first leg departs origin and
the last leg ends at the delivery-side facility. See
`fulfillment_and_shipping.md` for multi-leg routing and how legs relate to
`route_lanes` and `facilities`.

```sql
-- Average completed-leg transit time by transport mode
SELECT mode_code,
       AVG(julianday(arrived_ts) - julianday(departed_ts)) AS avg_leg_days
FROM shipment_legs
WHERE status = :completed             -- LEG_STATUS 'completed'
  AND arrived_ts IS NOT NULL
GROUP BY mode_code;

-- Shipments with at least one failed leg (a routing problem signal)
SELECT DISTINCT shipment_id
FROM shipment_legs
WHERE status = :failed;               -- LEG_STATUS 'failed'
```

Be careful not to confuse leg completion with shipment delivery: a shipment can
have every leg `completed` and still not be in the SHIP_STATUS `delivered` state
if the final hand-off has not been scanned, and conversely a `delivered` shipment
should have its legs `completed`. When a question asks about "the journey,"
decide whether it means the shipment (SHIP_STATUS) or the individual movements
(LEG_STATUS) before you pick a table.

---

### Lifecycle: Tracking events (append-only stream)

**Column:** `tracking_events.event_code`  **Code set:** TRACK_EVENT

Tracking events are **not a status column** — they are an append-only event
stream. A shipment accumulates a series of tracking event rows over time, each
with an `event_ts`, an optional `facility_id` where the scan occurred, and a
`message`. The event types (label terms) are:

- `created` — a tracking record/label was created.
- `departed` — the shipment left a facility.
- `arrived` — the shipment reached a facility.
- `customs_hold` — the shipment is held in customs.
- `delivered` — a delivery scan.
- `delivery_failed` — a delivery attempt failed.
- `return_to_sender` — the shipment is being returned to origin.

**How to use it.** Because this is an event log, do not treat a single event as
"the status." A shipment's *current* status lives in `shipments.status`
(SHIP_STATUS); the tracking stream is the detailed history behind it. Use
tracking events to reconstruct a timeline ("when did it clear customs," "how many
delivery attempts were made," "which facility last scanned it"). Multiple events
of the same type can exist (several `arrived`/`departed` scans across the
journey). To get the latest event for a shipment, take the row with the maximum
`event_ts`. A `delivered` tracking event corresponds to the shipment reaching the
`delivered` state, but for delivery-date math prefer `shipments.delivered_date`
as the authoritative field. Note the TRACK_EVENT `delivered` label is a
*tracking event*, distinct from the SHIP_STATUS `delivered` shipment state even
though they describe the same real-world moment.

---

### Lifecycle: Delivery exceptions (open vs resolved)

**Column:** `delivery_exceptions.exception_type_code`  **Code set:** EXCEPTION_TYPE

A delivery exception is a problem reported against a shipment. It is **not a
status-machine entity**; instead its lifecycle is captured by two timestamps:

- `reported_ts` — always present; when the problem was raised.
- `resolved_ts` — nullable; when the problem was resolved. **NULL means the
  exception is still open.**

The exception *types* (label terms, from EXCEPTION_TYPE) describe the nature of
the problem: `weather_delay`, `address_issue`, `damaged`, `missed_delivery`,
`customs`, `mechanical`.

**Open vs resolved.** An exception is **open** when `resolved_ts IS NULL` and
**resolved** when `resolved_ts IS NOT NULL`. Time-to-resolve is
`resolved_ts - reported_ts` for resolved exceptions. A single shipment can have
more than one exception, and having any open exception often coincides with the
shipment being in the SHIP_STATUS `exception` state, but the two are recorded
independently — the shipment status is the current state, the exception rows are
the detailed problem log. When counting "shipments with open exceptions," dedupe
to the shipment level, since a shipment may have several exception rows.

```sql
-- Distinct shipments with at least one currently-open exception
SELECT COUNT(DISTINCT shipment_id) AS shipments_with_open_exceptions
FROM delivery_exceptions
WHERE resolved_ts IS NULL;

-- Median-ish view: average resolution time in days by exception type
SELECT exception_type_code,
       AVG(julianday(resolved_ts) - julianday(reported_ts)) AS avg_days_to_resolve
FROM delivery_exceptions
WHERE resolved_ts IS NOT NULL
GROUP BY exception_type_code;
```

Note the second query filters to resolved rows before the date math; including
open rows would feed a NULL `resolved_ts` into `julianday`, producing NULL
durations that quietly distort the average.

---

### Lifecycle: Pick task

**Column:** `pick_tasks.status_code`  **Code set:** PICK_STATUS
**Detail:** `pick_lines` (references product by `item_code`)

A pick task is the warehouse work of assembling an order's items for shipment. It
moves through these states (label terms):

- `queued` — the pick task has been created and is waiting to be assigned.
- `assigned` — a picker has been assigned but has not started.
- `picking` — the picker is actively pulling items.
- `completed` — **the terminal "complete" state.** The pick finished; all
  required items were pulled. `completed_ts` is populated.
- `short` — the pick could not be fully satisfied (a shortage occurred); this is
  a terminal outcome distinct from `completed`.

**Meaning and "complete."** `completed` is the pick's done state — again a
*different* terminal label from the order's `fulfilled` or the shipment's
`delivered`. A `short` pick indicates the warehouse could not find all the units,
which is an operational signal (often correlated with low inventory or an
inventory accuracy issue — see cycle counts below). `completed_ts` is NULL until
the task reaches a finished state. `pick_lines` holds the item-level detail of a
pick, referencing the product by `item_code` (the inventory-side identifier, not
`sku`) and an optional `bin_id` for where the item was pulled from. See
`warehouse_and_inventory.md` for how picks draw down inventory.

```sql
-- Short-pick rate by warehouse (an inventory-accuracy warning sign)
SELECT warehouse_id,
       AVG(CASE WHEN status_code = :short THEN 1.0 ELSE 0.0 END) AS short_rate
FROM pick_tasks                       -- PICK_STATUS 'short'
GROUP BY warehouse_id
ORDER BY short_rate DESC;
```

---

### Lifecycle: Return

**Columns:** `returns.status`  **Code set:** RETURN_STATUS
**Reason:** `returns.reason_code` — **code set:** RETURN_REASON
**Disposition:** `returns.disposition_code` (nullable) — **code set:** RETURN_DISPOSITION
**Detail:** `return_lines` (references product by `sku`; item condition —
**code set:** ITEM_CONDITION)

A return (RMA) is opened against an order and moves through these states (label
terms):

`requested` → `authorized` → `received` → `refunded`

with a rejection off-ramp:

- `rejected` — the return was not accepted.

**Meaning of each state.**

- `requested` — the customer has asked to return items; the RMA exists but is not
  yet approved.
- `authorized` — the return has been approved; the customer may send the goods
  back.
- `received` — the returned goods have physically arrived. `received_date` is
  populated at this point (it is NULL before receipt).
- `refunded` — **the terminal "complete" state for an accepted return.** The
  customer has been refunded and the return is closed.
- `rejected` — a terminal state where the return was declined (out of policy,
  ineligible, etc.); no refund is issued.

**What "complete" means.** `refunded` is the successful terminal state;
`rejected` is the unsuccessful terminal state. Note this differs again from every
other table's "done." A return that is `requested` or `authorized` but not yet
`received` has a NULL `received_date`. When the order is fully returned, the
order header may show the ORDER_STATUS `returned` state (see the Order lifecycle
above), but the return's own progress is tracked here.

```sql
-- Open returns: authorized but the goods have not yet been received
SELECT COUNT(*) AS returns_awaiting_goods
FROM returns
WHERE status = :authorized           -- RETURN_STATUS 'authorized'
  AND received_date IS NULL;

-- Refund throughput: returns that completed the full happy path
SELECT COUNT(*) AS completed_returns
FROM returns
WHERE status = :refunded;            -- RETURN_STATUS 'refunded'
```

**Reason, disposition, and condition.**

- `reason_code` (RETURN_REASON) records *why* the customer returned:
  `defective`, `wrong_item`, `no_longer_needed`, `damaged_in_transit`,
  `late_delivery`. This is always present.
- `disposition_code` (RETURN_DISPOSITION) records *what we did with the goods*:
  `restock`, `refurbish`, `scrap`, `return_to_supplier`. It is **nullable**
  because disposition is decided only after the goods are received/inspected — a
  return that has not yet been received will have a NULL disposition.
- On each `return_lines` row, `condition_code` (ITEM_CONDITION) records the state
  of the returned unit: `new`, `opened`, `damaged`, `defective`. It is nullable
  (condition may be unknown until inspection). `return_lines` references the
  product by `sku` (order-side identifier). A `restock` disposition typically
  applies to `new`/`opened` condition, while `damaged`/`defective` items tend to
  be `scrap`, `refurbish`, or `return_to_supplier`; the disposition column is
  authoritative for what actually happened.

See `fulfillment_and_shipping.md` for the returns flow end to end and
`warehouse_and_inventory.md` for how a `restock` disposition relates to
inventory. Note that in this dataset a restocked return does not post a
`return_restock` inventory movement — no such row is generated.

---

### Lifecycle: Replenishment / purchase order (PO)

**Column:** `replenishment_orders.status`  **Code set:** PO_STATUS
**Detail:** `replenishment_lines`; receiving via `receipts` / `receipt_lines`

A replenishment order (a purchase order to a supplier to restock a warehouse)
moves through these states (label terms):

`draft` → `open` → `partial` → `received`

with a cancellation off-ramp:

- `cancelled` — the PO was cancelled before completion.

**Meaning of each state.**

- `draft` — the PO is being prepared and has not been sent to the supplier.
- `open` — the PO has been placed with the supplier and is awaiting delivery;
  nothing has been received yet.
- `partial` — some but not all of the ordered quantity has been received. This is
  where `qty_received < qty_ordered` on the lines.
- `received` — **the terminal "complete" state.** All ordered goods have been
  received. `received_date` on the header is populated.
- `cancelled` — a terminal state; the PO was cancelled.

**What "complete" means.** `received` is the done state for a PO. This is the
*same label* as a stock transfer's terminal state (below) but a *different code
set* — do not assume the underlying integers match, and do not carry a decode
between the two tables. A PO that is `open` or `partial` is still outstanding
(inbound stock not fully arrived); `expected_date` is the promised arrival and,
compared against TODAY (2024-12-31), tells you which open POs are overdue. The
header `received_date` is NULL until the PO reaches `received`.

**Line detail and receiving.** `replenishment_lines` carries `qty_ordered` and
`qty_received` per `item_code`, plus the `unit_cost`. Physical arrivals are
recorded as `receipts` against the PO (`repl_id`), and each receipt's
`receipt_lines` records `qty_received` per `item_code` with a `condition_code`
(ITEM_CONDITION — `new`/`opened`/`damaged`/`defective`). A single PO can generate
multiple receipts over time, which is exactly what drives the `partial` state.
Summing receipt-line quantities reconciles to the line-level `qty_received`. See
`warehouse_and_inventory.md` and the **Pricing, Costs & Billing** section (for supplier
invoicing against the PO).

```sql
-- Outstanding inbound POs that are overdue as of TODAY (2024-12-31)
SELECT repl_id, warehouse_id, expected_date
FROM replenishment_orders
WHERE status IN (:open, :partial)     -- PO_STATUS 'open' / 'partial'
  AND expected_date < '2024-12-31'
ORDER BY expected_date;

-- Reconcile a PO's line receipts against physical receipt lines
SELECT rl.repl_id,
       SUM(rl.qty_received)                        AS line_level_received,
       (SELECT SUM(rcl.qty_received)
          FROM receipts rc
          JOIN receipt_lines rcl ON rcl.receipt_id = rc.receipt_id
         WHERE rc.repl_id = rl.repl_id)            AS receipt_level_received
FROM replenishment_lines rl
GROUP BY rl.repl_id;
```

---

### Lifecycle: Stock transfer

**Column:** `stock_transfers.status_code`  **Code set:** TRANSFER_STATUS
**Detail:** `stock_transfer_lines`

A stock transfer moves inventory between two warehouses (`from_warehouse_id` →
`to_warehouse_id`). It moves through these states (label terms):

`requested` → `in_transit` → `received`

with a cancellation off-ramp:

- `cancelled` — the transfer was cancelled.

**Meaning of each state.**

- `requested` — the transfer has been requested but goods have not shipped from
  the source warehouse.
- `in_transit` — goods have left the source and are moving to the destination.
  `shipped_date` is populated.
- `received` — **the terminal "complete" state.** Goods arrived at the
  destination warehouse; `received_date` is populated.
- `cancelled` — terminal; the transfer did not proceed.

**What "complete" means.** `received` is the done state. As noted above, the
label matches the PO's terminal label but the code set (TRANSFER_STATUS) is
distinct from PO_STATUS — resolve each table's own code set. `shipped_date` is
NULL before `in_transit`; `received_date` is NULL before `received`. The line
detail (`stock_transfer_lines`) tracks `qty_requested`, `qty_shipped`, and
`qty_received` per `item_code`, so partial shipment/receipt is visible at the
line level even though the header carries a single status. A completed transfer
posts movements to the inventory ledger at both warehouses (a transfer-out at the
source and a transfer-in at the destination — see the inventory transaction types
in `warehouse_and_inventory.md`).

```sql
-- Transfers still on the road (shipped but not yet received) as of TODAY
SELECT transfer_id, from_warehouse_id, to_warehouse_id, shipped_date
FROM stock_transfers
WHERE status_code = :in_transit       -- TRANSFER_STATUS 'in_transit'
  AND received_date IS NULL
ORDER BY shipped_date;

-- Transfer lines where less was received than shipped (loss/shrink in transit)
SELECT transfer_id, item_code, qty_shipped, qty_received
FROM stock_transfer_lines
WHERE qty_received < qty_shipped;
```

The header status and the line quantities can disagree in the informative sense
that a `received` transfer may still show `qty_received < qty_requested` on some
lines — the transfer is closed, but not everything requested made it. Trust the
line quantities for "how much actually moved" and the header status for "is the
transfer closed."

---

### Lifecycle: Supplier status

**Column:** `suppliers.status_code`  **Code set:** SUPPLIER_STATUS

A supplier record carries a status describing our sourcing relationship (label
terms):

- `active` — an approved, in-use supplier we can place POs with.
- `on_hold` — temporarily suspended (quality, commercial, or compliance reasons);
  should not receive new POs while on hold.
- `terminated` — the relationship has ended; no new business.
- `pending_approval` — a prospective supplier not yet approved for use.

This is a *state of the relationship*, not a workflow with a single "complete"
value: `active` is the usable state, and the others are non-usable for new
sourcing. When analyzing current sourcing options, filter to `active`; historical
POs and invoices from a supplier that is now `on_hold`/`terminated` still exist
and should not be dropped just because the supplier's current status changed. See
`warehouse_and_inventory.md` for supplier/product sourcing and
the **Pricing, Costs & Billing** section for supplier invoicing.

Two common analyst mistakes with supplier status are worth calling out. First,
`pending_approval` suppliers are *prospective*: they may already exist in
`supplier_products` as a catalog of what they could sell us, but they should not
appear in "who do we currently buy from" analysis. Second, `on_hold` is
temporary and reversible, so a supplier that shows `on_hold` today may have a long
run of legitimate historical POs — do not read the current status as evidence
about past performance. The correct pattern is to filter suppliers by status only
when the question is about the *current* sourcing footprint, and to leave the
status filter off (or scope it by date) when the question is about historical
spend, receipts, or lead-time performance.

```sql
-- Currently usable suppliers only
SELECT supplier_id, name, default_lead_time_days
FROM suppliers
WHERE status_code = :active;          -- SUPPLIER_STATUS 'active'
```

---

### Lifecycle: Invoice status (supplier and carrier invoices)

**Columns:** `supplier_invoices.status_code` and `carrier_invoices.status_code`
**Code set:** INVOICE_STATUS (the **same** code set for both tables)

Both supplier invoices (what suppliers bill us for goods) and carrier invoices
(what carriers bill us for freight) use the INVOICE_STATUS code set. States
(label terms):

- `draft` — the invoice record exists but has not been formally submitted into
  our AP process.
- `submitted` — the invoice has been submitted and is awaiting review.
- `approved` — the invoice has been reviewed and approved for payment.
- `paid` — **the terminal "complete" state.** The invoice has been paid;
  `paid_date` is populated.
- `disputed` — the invoice is contested (amount or validity in question) and is
  not proceeding to payment until resolved.

**What "complete" means.** `paid` is the done state; `disputed` is an off-path
state that must be resolved before payment. `paid_date` is NULL for any invoice
not yet in `paid`. `due_date` compared against TODAY (2024-12-31) identifies
overdue unpaid invoices (any invoice that is not `paid` and whose `due_date` has
passed). This is the one case where two different tables genuinely share a code
set — but they are still separate tables: a supplier invoice and a carrier
invoice are different documents against different counterparties, even though
their status decode is identical. `supplier_invoices` optionally links to a
replenishment order (`repl_id`, nullable); `carrier_invoices` links to a carrier.
See the **Pricing, Costs & Billing** section.

```sql
-- Overdue unpaid carrier invoices as of TODAY (2024-12-31)
SELECT carrier_invoice_id, carrier_id, amount, due_date
FROM carrier_invoices
WHERE status_code <> :paid            -- INVOICE_STATUS 'paid'
  AND due_date < '2024-12-31'
ORDER BY due_date;
```

The identical query shape works against `supplier_invoices` because both tables
share the INVOICE_STATUS code set — one of the few times a decode is portable,
and only because it is literally the same code set, not because "status means the
same thing everywhere."

---

### Lifecycle: Cycle count status

**Column:** `cycle_counts.status_code`  **Code set:** CYCLE_COUNT_STATUS

A cycle count is a scheduled physical count of a product at a warehouse (and
optionally a specific bin) to verify inventory accuracy. It moves through these
states (label terms):

- `scheduled` — the count has been planned but not yet performed.
- `counted` — the physical count has been performed; `counted_qty` is recorded
  and `variance` (= `counted_qty - system_qty`) is known.
- `reconciled` — **the terminal "complete" state.** The count has been reviewed
  and any variance has been reconciled (an inventory adjustment posted if
  needed).

```sql
-- Counts that revealed a discrepancy and are awaiting reconciliation
SELECT warehouse_id, item_code, system_qty, counted_qty, variance
FROM cycle_counts
WHERE status_code = :counted          -- CYCLE_COUNT_STATUS 'counted'
  AND variance <> 0
ORDER BY ABS(variance) DESC;
```

**What "complete" means.** `reconciled` is the done state. A `counted` but not
yet `reconciled` count has a measured variance that has not yet been actioned. A
non-zero `variance` is the accuracy signal: positive means more units were found
than the book showed, negative means fewer. Reconciliation typically results in
an `inventory_adjustments` row (reason `cycle_count`) that corrects on-hand and
posts to the inventory ledger. See `warehouse_and_inventory.md` for how
adjustments and counts feed inventory accuracy.

---

### Reading state as of a point in time

Every `status`/`status_code` column holds the entity's **current** state — the
state as of the TODAY snapshot (2024-12-31). Most reporting questions want the
current state and can filter the column directly. But some questions are
historical ("how many orders were in `confirmed` at the end of November," "how
many shipments were still in transit on a given date"), and for those the current
column is not enough on its own.

- **Orders** are the one entity with a full timestamped state trail
  (`order_status_history`). To reconstruct an order's state as of a date, take the
  latest `order_status_history` row for that order whose `changed_ts` is on or
  before the date, and decode its `status`. This lets you build point-in-time and
  aging views without relying on the current header value.

  ```sql
  -- Each order's state as of 2024-11-30 (latest history row up to that date)
  SELECT h.order_id, h.status
  FROM order_status_history h
  JOIN (
        SELECT order_id, MAX(changed_ts) AS as_of_ts
        FROM order_status_history
        WHERE changed_ts <= '2024-11-30T23:59:59'
        GROUP BY order_id
  ) latest
    ON latest.order_id = h.order_id
   AND latest.as_of_ts = h.changed_ts;
  ```

- **Shipments, returns, POs, transfers** do not have a per-status history table.
  Instead they expose their key transition timestamps as dated columns —
  `ship_date` / `delivered_date`, `requested_date` / `received_date`,
  `order_date` / `expected_date` / `received_date`, `created_date` /
  `shipped_date` / `received_date`. Use those dates for aging and point-in-time
  reasoning. For example, a shipment was "in transit as of date D" when
  `ship_date <= D` and (`delivered_date IS NULL` or `delivered_date > D`); a PO
  was "outstanding as of D" when `order_date <= D` and (`received_date IS NULL`
  or `received_date > D`). Because these NULLable date columns *are* the state
  signal, use `IS NULL` explicitly rather than relying on inequality comparisons,
  which drop NULL rows.

- **Tracking events and inventory transactions** are true event logs, so a
  point-in-time reconstruction there means filtering the stream to `event_ts` /
  `txn_ts` on or before the date and taking the latest (for tracking) or summing
  the deltas (for the inventory ledger).

The practical rule: current-state questions read the status column; historical
and aging questions read the transition timestamps (or the order history table),
and always compare against the 2024-12-31 snapshot date, not the real-world date.

### A cross-domain lifecycle walkthrough

It helps to see how the separate lifecycles line up along one order's journey,
because a single business event touches several state machines at once — each
advancing on its own code set.

1. A customer places an order. `orders.status` moves `draft` → `placed` →
   `confirmed` (ORDER_STATUS), and each step is stamped into
   `order_status_history`. A `payments` row is `authorized` and then `captured`
   (PAYMENT_STATUS) as money is taken. If a gift card was used, a
   `gift_card_transactions` `redeem` row (GIFTCARD_TXN_TYPE) draws down the card,
   possibly moving it to `redeemed` (GIFTCARD_STATUS).

2. The warehouse assembles the order. A `pick_tasks` row runs `queued` →
   `assigned` → `picking` → `completed` (PICK_STATUS), drawing units out of
   `inventory` and posting a `shipment`-type movement to the inventory ledger. A
   shortage would end the pick at `short` instead.

3. The order ships. A `shipments` row runs `label_created` → `picked_up` →
   `in_transit` → `out_for_delivery` → `delivered` (SHIP_STATUS), while its
   `shipment_legs` each run `pending` → `in_progress` → `completed` (LEG_STATUS)
   and `tracking_events` (TRACK_EVENT) accumulate as an append-only log. A snag
   in transit opens a `delivery_exceptions` row (open until `resolved_ts` is set).
   Once `delivered_date` is populated, the order's header reaches ORDER_STATUS
   `fulfilled`.

4. The customer returns an item. A `returns` row runs `requested` → `authorized`
   → `received` → `refunded` (RETURN_STATUS); a `payments` `refunded` row and/or
   a gift-card `refund` transaction reverse the money; the order header may move
   to ORDER_STATUS `returned`; and a `restock` disposition marks the goods as
   sellable again (in this dataset it does not post a `return_restock` inventory
   movement — no such row is generated).

5. Meanwhile, supply keeps flowing. A `replenishment_orders` PO runs `open` →
   `partial` → `received` (PO_STATUS) with `receipts` posting stock in; a
   `stock_transfers` row runs `requested` → `in_transit` → `received`
   (TRANSFER_STATUS) to rebalance between warehouses; `cycle_counts` run
   `scheduled` → `counted` → `reconciled` (CYCLE_COUNT_STATUS) to keep the book
   honest; and `supplier_invoices` / `carrier_invoices` run `submitted` →
   `approved` → `paid` (INVOICE_STATUS) to settle the bills.

Notice that at every step the word for "done" is different — `fulfilled`,
`captured`, `completed`, `delivered`, `refunded`, `received`, `reconciled`,
`paid` — and each belongs to a different code set on a different table. That is
exactly why the decode is never portable, and why the summary table below is
organized around each column's own code set.

### Related coded fields that are not lifecycles

A few coded columns describe a *type* or *classification* rather than a state
that progresses over time. They are decoded like any other code (label via
the **Code Dictionary** section) but they do not have a terminal state or transitions:

- **Inventory transactions** — `inventory_transactions.txn_type_code` (code set
  INV_TXN_TYPE): `receipt`, `shipment`, `transfer_out`, `transfer_in`,
  `adjustment`, `return_restock`. This is the *type* of a movement on the
  inventory ledger, not a status. The ledger is append-only; each row is a
  signed `quantity_delta`. See `warehouse_and_inventory.md`.
- **Inventory adjustments** — `inventory_adjustments.reason_code` (code set
  ADJ_REASON): `cycle_count`, `damage`, `theft`, `found`, `correction`. The
  reason for a manual stock change.
- **Order priority / channel** — `orders.priority_code` (ORDER_PRIORITY) and
  `orders.channel_code` (ORDER_CHANNEL) classify an order but are not lifecycle
  states. Note the ORDER_PRIORITY `internal_test` tier marks internal/test orders
  that are excluded from reporting — see the **Exclusions, Reporting Conventions, and Data Quality** section.

These are listed here so you do not mistake a type/reason code for a status when
scanning a table.

---

### Summary: status column → code set

Every `status`/`status_code` column and the code set that decodes it. Labels
only; integer values are in the **Code Dictionary** section. Each code set has its own
terminal "complete" label as noted throughout this document — do not carry a
decode from one table to another.

| Table | Status column | Code set | Terminal / "complete" label |
|---|---|---|---|
| orders | status | ORDER_STATUS | fulfilled (plus cancelled / returned end states) |
| payments | status_code | PAYMENT_STATUS | captured (resolved: refunded / voided / failed) |
| gift_cards | status_code | GIFTCARD_STATUS | redeemed (end states: expired / void) |
| shipments | status | SHIP_STATUS | delivered |
| shipment_legs | status | LEG_STATUS | completed |
| pick_tasks | status_code | PICK_STATUS | completed (short = shortage end state) |
| returns | status | RETURN_STATUS | refunded (rejected = declined end state) |
| replenishment_orders | status | PO_STATUS | received (cancelled = end state) |
| stock_transfers | status_code | TRANSFER_STATUS | received (cancelled = end state) |
| suppliers | status_code | SUPPLIER_STATUS | active is the usable state (no single "done") |
| supplier_invoices | status_code | INVOICE_STATUS | paid |
| carrier_invoices | status_code | INVOICE_STATUS | paid |
| cycle_counts | status_code | CYCLE_COUNT_STATUS | reconciled |

Event-stream and open/resolved columns that are not status machines but are
covered above:

| Table | Column(s) | Code set | "Done" signal |
|---|---|---|---|
| tracking_events | event_code | TRACK_EVENT | append-only stream; no status |
| delivery_exceptions | exception_type_code; resolved_ts | EXCEPTION_TYPE | resolved when `resolved_ts IS NOT NULL` |

For the integer decode of any code set named above, and for the type/reason code
sets (INV_TXN_TYPE, ADJ_REASON, ORDER_PRIORITY, ORDER_CHANNEL, RETURN_REASON,
RETURN_DISPOSITION, ITEM_CONDITION, and the rest), see the **Code Dictionary** section.
For the business metrics that build on these states (on-time delivery, revenue
recognition, fill rate, overdue POs and invoices), see
the **Metrics and Definitions** section.

---

## Exclusions, Reporting Conventions, and Data Quality

This document is the authoritative reference for **which records belong in a
report and which do not**, plus the handful of data-quality realities every
analyst has to keep in mind. If the **Metrics and Definitions** section tells you *how*
to compute a metric, this document tells you *what population* to compute it
over. The two are meant to be read together: every metric definition in the
**Metrics and Definitions** section
inherits the exclusion rules stated here, and where a metric touches orders or
revenue it applies the internal-test exclusion below without further comment.

Read this once end to end. The rules are few, but they are load-bearing: the
difference between a defensible number and a wrong one is almost always a
population question, not a formula question.

A note on the SQL in this corpus: coded columns are compared against
**named bind parameters** written like `:internal_test_priority` or
`:order_status_cancelled`. Every integer code value lives in exactly one place,
the **Code Dictionary** section; you look the value up there and bind it. We never write
the raw integer next to its label in narrative docs, because the same integer
means different things in different code sets (see
the **Code Dictionary** section), and a stray literal is exactly how a decode
leaks from one table to another. The queries are otherwise ordinary, runnable
SQLite.

---

### 1. The internal-test order exclusion (the headline convention)

**This is the single most important reporting rule in the warehouse. Learn it
before you write your first revenue query.**

We place a small number of **internal / QA / staging orders** through the live
order system. They are how operations, engineering, and finance smoke-test the
end-to-end flow — order capture, payment authorization, pick, pack, ship, track,
even the occasional return — against the real production stack rather than a toy
environment. They exercise real code paths on purpose, and as a direct
consequence **they look exactly like ordinary customer orders in the data.**

Read that again, because it is the whole pitfall. An internal-test order:

- is attached to a **real customer** row (often a normal-looking consumer or
  small-business account),
- carries a **normal `order_total`** and normal `order_lines` with real SKUs,
  real quantities, and real unit prices,
- moves through the **normal status lifecycle** (it can be placed, confirmed,
  fulfilled, even returned),
- generates **real shipments**, packages, tracking events, pick tasks, and
  sometimes delivery exceptions,
- has **nothing** anomalous about its amounts, dates, channel, or addresses.

There is **no dedicated flag**, no `is_test` column, no special customer type,
no sentinel amount, no reserved SKU. The **only** thing that distinguishes an
internal-test order from a genuine one is its **priority**: the order's
`priority_code` is the **`internal_test`** value of the **ORDER_PRIORITY** code
set. The real, customer-facing priority tiers are `standard`, `expedited`, and
`rush`; `internal_test` is a fourth value that never corresponds to real demand.

Because there is no other signal, if you do not filter on the priority you will
silently fold QA traffic into every number you publish. These orders are roughly
**3% of all orders** — small enough that nobody notices them in a spot check,
large enough to move a revenue total, an order count, an average order value, an
on-time rate, or a return rate by a visible amount. They inflate demand, they
distort per-segment and per-channel splits (QA does not order like a real
customer base), and they contaminate fulfillment metrics with shipments that
were never meant to represent service to a paying customer.

#### The rule

> **Internal-test orders (ORDER_PRIORITY = `internal_test`) must be excluded
> from ALL standard reporting.** Revenue, order counts, average order value,
> fulfillment and on-time metrics, return and exception rates, margin — every
> metric that touches an order, directly or through a shipment, return, or pick
> task, excludes them. There is no report in which they belong except an
> explicit QA/system-health diagnostic that is *about* the test traffic itself.

The exclusion propagates. Anything that joins back to `orders` inherits it:

- **Shipments** — a shipment fulfilling an internal-test order is itself test
  traffic; join `shipments` → `orders` and exclude on the order's priority.
- **Returns** — a return against an internal-test order is a test return.
- **Pick tasks** — a pick for an internal-test order is test work.
- **Payments, order lines, order promotions, gift-card transactions tied to an
  order** — all inherit the exclusion through the order.

#### The canonical filter

The value of the `internal_test` priority in the ORDER_PRIORITY code set is
defined in the **Code Dictionary** section; look it up and bind it. The filter is always
the same shape:

```sql
-- Bind :internal_test_priority to the ORDER_PRIORITY 'internal_test' value
-- (see the Code Dictionary section). Applied to the orders table itself:
WHERE o.priority_code <> :internal_test_priority
```

When you are on a table that reaches orders through a foreign key, join first,
then apply the same predicate to the order row:

```sql
-- On shipments, returns, pick_tasks, payments, order_lines, etc.
FROM shipments s
JOIN orders o ON o.order_id = s.order_id
WHERE o.priority_code <> :internal_test_priority
```

A defensive habit worth adopting: write the exclusion as a reusable CTE at the
top of any multi-step query so it cannot be forgotten downstream.

```sql
WITH reportable_orders AS (
    SELECT *
    FROM orders
    WHERE priority_code <> :internal_test_priority   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
)
SELECT ...
FROM reportable_orders o
...
```

#### Correct vs incorrect: a revenue example

**Incorrect** — total order revenue with no exclusion. This number is wrong; it
includes QA traffic and will not reconcile with finance:

```sql
-- WRONG: includes internal-test (and cancelled) orders
SELECT ROUND(SUM(order_total), 2) AS revenue
FROM orders;
```

**Correct** — the internal-test priority is excluded (and, per Section 2 below,
so are cancelled orders):

```sql
-- RIGHT: exclude internal-test priority and cancelled orders
SELECT ROUND(SUM(o.order_total), 2) AS revenue
FROM orders o
WHERE o.priority_code <> :internal_test_priority   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status        <> :order_status_cancelled;  -- ORDER_STATUS cancelled; see the Code Dictionary section
```

The gap between those two queries is the entire point of this section. Neither
raises an error; neither looks suspicious in isolation. The second is the
company number.

The same pitfall applies well beyond revenue. An **order count** that forgets the
exclusion overstates demand by the ~3% QA share; a per-channel count skews toward
whatever channel QA tests through. An **on-time delivery rate** computed over all
delivered shipments includes test shipments whose promise dates were set for
convenience, not for a customer — so the published service level is measuring
partly against fake promises:

```sql
-- WRONG: on-time rate over ALL delivered shipments, test traffic included
SELECT ROUND(100.0 * AVG(CASE WHEN delivered_date <= promised_date THEN 1 ELSE 0 END), 1)
FROM shipments
WHERE status = :ship_status_delivered;   -- SHIP_STATUS delivered; see the Code Dictionary section

-- RIGHT: exclude shipments belonging to internal-test orders
SELECT ROUND(100.0 * AVG(CASE WHEN s.delivered_date <= s.promised_date THEN 1 ELSE 0 END), 1)
FROM shipments s
JOIN orders o ON o.order_id = s.order_id
WHERE s.status = :ship_status_delivered
  AND s.promised_date IS NOT NULL
  AND o.priority_code <> :internal_test_priority;   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
```

The exclusion is the *first* predicate you write on any order-touching query, not
an afterthought bolted on at the end.

If you ever *do* need to see the test traffic — for example, to confirm QA ran a
smoke test last week — invert the predicate explicitly and label the output as a
diagnostic, never as business reporting:

```sql
-- Diagnostic ONLY: the internal-test population itself
SELECT COUNT(*) AS internal_test_orders
FROM orders
WHERE priority_code = :internal_test_priority;   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
```

---

### 2. Other standard exclusions and conventions

The internal-test rule is the headline, but a correct report usually applies two
or three exclusions at once. Decide, for every question, which of the following
apply.

#### Convention 2.1: Cancelled orders are not revenue

A cancelled order (ORDER_STATUS `cancelled`) never shipped and was never
recognized. Exclude cancelled orders from **revenue, realized order counts,
average order value, fill rate, and any fulfillment metric**. A cancelled order
produces no shipments, so it will not appear in shipment-based metrics anyway,
but it *does* still carry an `order_total`, so it will corrupt a naive revenue
sum off the `orders` header. Always pair the cancelled-status exclusion with the
internal-test exclusion on any revenue query, as shown above.

Note the code set: cancellation is a value of **ORDER_STATUS**, the code set for
`orders.status`. Do not reuse a "cancelled" decode from any other table's status
column — there is no cancelled state in SHIP_STATUS, for instance, and the
integer that means cancelled for orders means something entirely different
elsewhere (see the **Code Dictionary** section).

#### Convention 2.2: Draft orders are not yet real demand

A draft order (ORDER_STATUS `draft`) is a started-but-not-committed order: a
cart, a quote, a work-in-progress that the customer or a rep has not placed.
Drafts are **not demand**. Exclude them from revenue, order counts, and demand
analysis. They are legitimately included only when the question is explicitly
about the drafting funnel ("how many orders are stuck in draft").

For most demand and revenue reporting the clean population is: **orders that are
neither draft nor cancelled, and not internal-test priority.** That leaves the
"real, committed" states — placed, confirmed, fulfilled, returned — which is the
population the **Metrics and Definitions** section treats as reportable demand.

```sql
-- Reportable demand: real customer orders that represent committed demand
FROM orders o
WHERE o.priority_code <> :internal_test_priority   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status NOT IN (:order_status_draft,        -- ORDER_STATUS draft;     see the Code Dictionary section
                       :order_status_cancelled)     -- ORDER_STATUS cancelled; see the Code Dictionary section
```

#### Convention 2.3: Returned orders — keep them in most reporting

A returned order (ORDER_STATUS `returned`) was placed, paid for, fulfilled, and
shipped — real demand and real revenue — and then some or all of it came back.
For **revenue and demand reporting, keep returned orders in the population**:
the sale happened, and the return is measured separately as a return metric (see
the **Metrics and Definitions** section, return rate). Netting returns out of gross
revenue is a *net-revenue* calculation you do explicitly, by subtracting return
value, not by dropping the order from the count. Do not confuse a `returned`
order with a `cancelled` one: a cancellation means the sale never completed and
is excluded; a return means it completed and then reversed and is included in
gross figures. This is a common decode slip because both feel like "the order
went away" — they do not mean the same thing, and they live at different values
of the same ORDER_STATUS code set (see the **Code Dictionary** section).

#### Convention 2.4: Multiple shipments, partial fulfillment, and the order grain

An order is not always one shipment. A single order can be split across several
shipments (partial releases, multi-warehouse sourcing, back-ordered lines that
ship later), so when you reason about "the order's delivery" you have to decide
whether you mean the *first* shipment, the *last* shipment, or *all* shipments.
Metric definitions in the **Metrics and Definitions** section state this per metric — order cycle time uses the
first shipment, on-time-in-full considers every shipment — but the general rule
is: **pick the shipment grain deliberately and aggregate to the order before
you count orders.** Counting `shipments` when the business asked about `orders`,
or vice versa, is a grain error that silently multiplies or divides your number
by the average shipments-per-order.

#### Convention 2.5: De-duplication and fan-out

Two different concerns share the word "double-count," keep them separate:

- **Genuine duplicates.** The warehouse's primary keys are clean and unique, so
  you will not find literal duplicate rows in a base table. Duplication in your
  *result* comes from joins, not from the source (see fan-out below).
- **Fan-out from one-to-many joins.** This is the real hazard. An order has many
  order lines; a shipment has many packages, items, legs, and tracking events; a
  return has many return lines. The moment you join a header to its children and
  then aggregate a **header-level** column, that header value is repeated once
  per child and your sum is inflated.

The classic mistake is summing `orders.order_total` after joining to
`order_lines` or `shipments`:

```sql
-- WRONG: order_total is repeated once per order line -> inflated
SELECT SUM(o.order_total)
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
WHERE o.priority_code <> :internal_test_priority;
```

Fix it by aggregating at the level the measure lives on. Sum a **line-level**
measure (`order_lines.line_total`) across lines, or sum a **header-level**
measure (`orders.order_total`) across distinct orders — never a header measure
across a child-fanned join. Detailed patterns are in
the **Query Recipes and Pitfalls** section; the metric definitions in the **Metrics and Definitions** section are each
written to aggregate at the correct grain.

#### Convention 2.6: Use `is_active` for the *current* set, not for history

`products`, `customers`, `carriers`, and `warehouses` carry an `is_active` flag.
It marks whether the record is part of the **currently usable** master data — an
active product is one we still sell, an active carrier one we still tender to.
It does **not** mean the record has no history: an inactive product can have
years of historical orders, and an inactive carrier can have delivered
thousands of past shipments.

The rule:

- Filter on `is_active = 1` when the question is about the **current
  operational set** — "which products are *currently* below reorder point,"
  "which carriers are we *currently* using," "the active warehouse footprint."
- Do **not** filter on `is_active` when the question is **historical** — "revenue
  by product last year" must include products that are now inactive but sold in
  the period.

Applying `is_active` to a historical metric quietly drops legitimate history;
omitting it from a "current state" question quietly includes retired records.
Neither errors. Choose deliberately.

#### Convention 2.7: Pick the reporting date deliberately

`TODAY` is **2024-12-31**. Every "as of now," "currently open," "overdue,"
"aging," or "days since" calculation is measured against `2024-12-31`, not the
real-world date. Use the literal `'2024-12-31'` (or `julianday('2024-12-31')`)
rather than `date('now')`, which would return a real current date and produce
nonsense against a fixed 2024 snapshot.

---

### 3. Data-quality notes

The dataset is deliberately clean in the ways that usually cause trouble — one
currency, one unit system, one calendar, unique keys — so the data-quality work
here is almost entirely about **two identifier vocabularies** and **the meaning
of NULL**. Neither of these will ever raise an error; both will silently give
you a wrong answer if you ignore them.

#### Convention 3.1: The two product-identifier systems

The same product is referenced by two different identifiers depending on which
side of the business you are on:

- **Order / returns / shipment side** references a product by **`sku`**, a
  `TEXT` value formatted `SKU-00042`. You see it on `order_lines`,
  `return_lines`, and `shipment_items`.
- **Inventory / supplier / warehouse side** references the same product by
  **`item_code`**, an `INTEGER` equal to `products.product_id` (e.g. `42`). You
  see it on `supplier_products`, `inventory`, `inventory_lots`,
  `inventory_transactions`, `replenishment_lines`, `receipt_lines`,
  `stock_transfer_lines`, `inventory_adjustments`, `cycle_counts`, and
  `pick_lines`.

These are two encodings of one product. **The `products` table is the only
bridge** — it carries both `product_id` and `sku`. A join that treats the two
identifiers as directly equal returns **zero rows and no error**, because a text
value never equals an integer:

```sql
-- WRONG: text sku compared to integer item_code -> silently zero rows
SELECT ...
FROM order_lines ol
JOIN inventory i ON ol.sku = i.item_code;   -- never true
```

Always route the join through `products`:

```sql
-- RIGHT: bridge sku <-> item_code through products
SELECT ...
FROM order_lines ol
JOIN products  p ON p.sku       = ol.sku
JOIN inventory i ON i.item_code = p.product_id;
```

If you must convert without joining, the arithmetic identities are
`item_code = CAST(SUBSTR(sku, 5) AS INTEGER)` and
`sku = 'SKU-' || printf('%05d', item_code)`, but the `products` join is the
maintainable choice. Full mechanics and worked examples live in
the **Identifiers and Keys** section. Any cross-domain metric that spans the sell side
and the stock side (margin, days of supply, fill vs on-hand) touches this
bridge — do not shortcut it.

#### Convention 3.2: What a NULL means, column by column

NULL is used deliberately as a **lifecycle signal**: it means "not applicable
yet" or "hasn't happened." Because a NULL is meaningful, the *presence* or
*absence* of a value is often exactly what a metric is measuring. The important
ones:

- **`shipments.delivered_date` NULL** → the shipment has **not been delivered**.
  A delivered-shipment metric must require `delivered_date IS NOT NULL` (and the
  delivered SHIP_STATUS state); an in-transit or undelivered metric keys off the
  NULL.
- **`shipments.promised_date` NULL** → no delivery promise was recorded for that
  shipment, so it **cannot** be classified on-time or late. Exclude it from the
  on-time *denominator* rather than silently counting it as on-time.
- **`orders.promised_date` NULL** → the order carried no promised delivery date;
  handle the same way for any order-level SLA calculation.
- **`delivery_exceptions.resolved_ts` NULL** → the exception is **still open**.
  Open-exception counts key off the NULL; resolution-time metrics require it to
  be present.
- **`returns.received_date` NULL** → the returned goods have **not physically
  arrived** yet (the RMA may be requested or authorized but not received).
- **`returns.disposition_code` NULL** → **disposition not yet decided** (not yet
  restock/refurbish/scrap/return-to-supplier). Do not read a NULL disposition as
  any particular outcome.
- **`shipment_legs.arrived_ts` NULL** → the leg has **not completed**; the
  shipment is mid-journey on that leg.
- **`replenishment_orders.received_date` NULL** → the PO has not been fully
  received (it may be open or partially received; confirm against its PO_STATUS).
- **`supplier_invoices.paid_date` / `carrier_invoices.paid_date` NULL** → the
  invoice is **unpaid**. Aging and open-payables metrics key off the NULL.
- **`pick_tasks.completed_ts` NULL** → the pick task has not completed.
- **`return_lines.condition_code` NULL** → item condition not yet assessed.
- **`inventory_lots.expiry_date` NULL** → the lot is non-perishable / no expiry
  tracked; it does **not** mean expired.
- **Contact/customer `email`, `phone`** NULL → simply missing contact detail; no
  lifecycle meaning.

The operational hazard: SQL comparison operators (`=`, `<>`, `<`, `>`) evaluate
to *unknown*, not true, when either side is NULL, so a row with a NULL silently
drops out of a `WHERE` clause and is silently excluded from `COUNT(column)` and
`AVG(column)`. Two consequences:

1. When a NULL is part of what you are measuring, test it explicitly with
   `IS NULL` / `IS NOT NULL`. `WHERE delivered_date <> ''` or
   `WHERE promised_date > something` will drop the NULL rows without telling you.
2. When you compute a rate, decide consciously whether NULL rows belong in the
   denominator. A shipment with a NULL `promised_date` cannot be graded on-time;
   leaving it in the denominator understates the on-time rate, counting it as
   on-time overstates it. The **Metrics and Definitions** section handles each rate's denominator explicitly.

#### Convention 3.3: One currency, one unit, one calendar — nothing to convert

Unlike many warehouses, this one has **no unit or timezone traps**:

- **Money** is US dollars everywhere, stored as `REAL` with two decimals. No
  multi-currency, no FX, no minor-unit scaling. Round only at presentation.
- **Weight** is kilograms in every `weight_kg` column (products, shipments,
  packages). No pounds, no grams, no conversion.
- **Time** is a single calendar. Dates are `YYYY-MM-DD`, timestamps are
  ISO-8601, both stored as `TEXT`; they sort and compare correctly as strings
  and work with SQLite date functions. There is **no timezone offset** to
  reconcile — do not apply one.

So the only conversions you ever perform are the **product-identifier bridge**
(Section 3.1) and code-value decodes (via the **Code Dictionary** section). If you find
yourself writing an FX rate or a unit conversion, stop — there isn't one here.

#### Convention 3.4: Status decodes do not travel between tables

Restating a rule from the **Lifecycle and Statuses** section because it is a data-quality
issue too: `status` and `status_code` name **different code sets on different
tables**. `orders.status` is ORDER_STATUS; `shipments.status` is SHIP_STATUS;
`returns.status` is RETURN_STATUS; `replenishment_orders.status` is PO_STATUS;
`pick_tasks.status_code` is PICK_STATUS; `shipment_legs.status` is LEG_STATUS;
`stock_transfers.status_code` is TRANSFER_STATUS; the invoice tables use
INVOICE_STATUS; `cycle_counts.status_code` is CYCLE_COUNT_STATUS; and so on. The
**terminal "done" integer is different in each**. Never carry a decode from one
table to another — always re-derive the code-set name for the table you are on
and look the value up in the **Code Dictionary** section. This is the most common source of a
plausible-but-wrong filter.

#### Convention 3.5: The inventory movement ledger — read the sign of `quantity_delta`

`inventory_transactions` is a **movement ledger**: one row per stock movement,
carrying a signed `quantity_delta` and a `txn_type_code` from the **INV_TXN_TYPE**
code set (receipt, shipment, transfer-out, transfer-in, adjustment,
return-restock). Receipts, receipts-back, and transfers-in add stock (positive
delta); shipments and transfers-out remove it (negative delta); adjustments can
be either. Two cautions when you use the ledger:

- **Do not double-count against the operational tables.** The ledger is the
  *posting* of movements that also exist as receipts, shipments, transfers, and
  adjustments in their own tables. Sum outbound units **either** from the ledger
  (shipment transaction type) **or** from `shipment_items`, not both. Pick one
  source per metric and say which; the metric definitions in the **Metrics and Definitions** section name the source
  they use.
- **Use `ABS()` when you want a magnitude.** Outbound deltas are negative, so a
  raw `SUM(quantity_delta)` gives you a *net* position change, not gross throughput.
  For "units shipped" or "units received" take `SUM(ABS(quantity_delta))` filtered
  to the relevant transaction type; for a net on-hand reconciliation, keep the
  sign.

`inventory.quantity_on_hand` is the current standing balance and is the right
source for a point-in-time position (Section 7 metrics); the ledger is the right
source for *flow* over a period (throughput, turnover, days of supply). Do not
substitute one for the other.

#### Convention 3.6: Nullable foreign keys and optional relationships

A handful of foreign keys are deliberately **optional** (nullable), and a NULL
there means "no related record," not a broken join:

- **`orders.ship_to_address_id`** can be NULL (e.g. an in-store or
  not-yet-addressed order). An **inner** join to `customer_addresses` silently
  drops those orders; use a `LEFT JOIN` when address is incidental, and reserve
  the inner join for when a ship-to address is genuinely required.
- **`gift_cards.customer_id`** is nullable — an unregistered / unassigned card.
- **`gift_card_transactions.order_id`** is nullable — issue/reload/refund activity
  that is not tied to an order (only redemptions attach to an order).
- **`tracking_events.facility_id`**, **`pick_lines.bin_id`**, **`cycle_counts.bin_id`**,
  and **`supplier_invoices.repl_id`** are all nullable — the related node/location
  is simply not recorded on that row.

The rule of thumb: when the relationship is **optional**, prefer a `LEFT JOIN` so
you keep the parent rows, and test the joined key with `IS NULL` when its absence
is meaningful. An accidental inner join on a nullable FK is another silent
row-dropper that never raises an error.

---

### 4. "Always ask before reporting" checklist

Run through this before you publish any number. It takes thirty seconds and
catches the errors that matter.

1. **Does this touch orders, revenue, or anything downstream of an order
   (shipments, returns, picks, payments)?** If yes, **exclude the internal-test
   priority** (ORDER_PRIORITY `internal_test`; see the **Code Dictionary** section). Non-negotiable.
2. **Is this a revenue / demand / order-count metric?** Then also **exclude
   cancelled orders**, and usually **draft orders**, via ORDER_STATUS. Confirm
   whether returned orders belong in your population.
3. **Which code set is each status column?** Name it explicitly for *every*
   coded filter. Confirm you did not carry a decode across tables. Bind the value
   from the **Code Dictionary** section, don't hardcode a remembered integer.
4. **Which identifier system?** If the query spans the sell side (`sku`) and the
   stock side (`item_code`), route the product join through `products`
   (see the **Identifiers and Keys** section). Never equate `sku` to `item_code` directly.
5. **What do the NULLs mean here?** Decide whether NULL rows (undelivered,
   unpromised, unresolved, unreceived, unpaid, undisposed) belong in your
   population and, for a rate, in the denominator. Use `IS NULL` / `IS NOT NULL`
   explicitly.
6. **Is there fan-out?** If you joined a header to its children, confirm you are
   aggregating a measure at its own grain, not summing a header value across a
   one-to-many join. Use `COUNT(DISTINCT ...)` or aggregate before joining
   (see the **Query Recipes and Pitfalls** section).
7. **Is `is_active` relevant?** Filter it for *current-state* questions; leave it
   off for *historical* questions.
8. **Is the clock right?** Measure "as of," "overdue," and "aging" against
   `TODAY = 2024-12-31`, never `date('now')`.
9. **Does the metric already have a canonical definition?** Check
   the **Metrics and Definitions** section and use it, so your number reconciles with
   everyone else's.

If you can answer all nine, the number is defensible. If any answer is "I'm not
sure," resolve it before the report leaves your hands — the exclusions and code
sets are where reporting goes wrong, and they never announce themselves with an
error.

---

## Metrics and Definitions — the Canonical Catalog

This is the authoritative catalog of business metrics for the warehouse. Its
purpose is that **two analysts computing the same metric get the same number.**
For each metric you will find: a precise business definition, the exact tables
and columns it is built from, the exact filters — including which exclusions
apply and the **correct status code set per table** — and a worked, runnable
SQLite query you can adapt.

Every metric here inherits the reporting conventions in
the **Exclusions, Reporting Conventions, and Data Quality** section. In particular, **any metric that touches
orders or revenue excludes internal-test orders** (ORDER_PRIORITY
`internal_test`) and, where it is a revenue or demand metric, **excludes
cancelled (and usually draft) orders** (ORDER_STATUS). These exclusions are
written into every query below; they are not optional.

**Reading the SQL.** Coded columns are compared against **named bind
parameters** like `:internal_test_priority` or `:ship_status_delivered`. The
integer value for each lives in the **Code Dictionary** section; look it up, bind it,
and note the comment naming the code set and label. We do not write raw integers
next to labels because the same integer means different things across code sets
(the **Code Dictionary** section), and the "done" state differs per table. `TODAY`
is **2024-12-31**; all "as of" math uses that literal. Money is USD (2dp),
weight is kilograms, dates/timestamps are a single calendar — nothing to convert
(**Exclusions, Reporting Conventions, and Data Quality**, §3.3). Where a metric spans the sell side (`sku`) and the stock side
(`item_code`), the product join is routed through `products` (the **Identifiers and Keys** section).

A recurring building block, used throughout, is the reportable-order population:

```sql
-- The reportable-order CTE reused across revenue and demand metrics.
WITH reportable_orders AS (
    SELECT *
    FROM orders
    WHERE priority_code <> :internal_test_priority   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
      AND status        <> :order_status_cancelled    -- ORDER_STATUS cancelled;      see the Code Dictionary section
)
SELECT ... FROM reportable_orders o ...
```

---

### Metric: Recognized revenue

**Definition.** The dollar value of sales we recognize: the sum of order value
over **real, non-cancelled** customer orders. Internal-test orders and cancelled
orders are excluded. There are two equally valid grains to sum at, and they are
designed to reconcile:

- **Header grain** — `SUM(orders.order_total)` over distinct reportable orders.
- **Line grain** — `SUM(order_lines.line_total)` over the lines of those orders.

Use the header when you only need order-level totals; use lines when you need to
split revenue by product, category, or SKU. Do **not** sum `order_total` after
joining to `order_lines` — that fans the header value out once per line and
inflates it (**Exclusions, Reporting Conventions, and Data Quality**, §2.5).

**Tables / columns.** `orders(order_total, status, priority_code, order_date,
customer_id, channel_code)`; for the line grain `order_lines(line_total,
order_id, sku)`.

**Filters.** Exclude ORDER_PRIORITY `internal_test`; exclude ORDER_STATUS
`cancelled`. (Draft orders carry an `order_total` too but represent uncommitted
demand; the standard revenue population also excludes ORDER_STATUS `draft`.)

**Worked query — total recognized revenue (header grain):**

```sql
SELECT ROUND(SUM(o.order_total), 2) AS recognized_revenue
FROM orders o
WHERE o.priority_code <> :internal_test_priority     -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status NOT IN (:order_status_draft,          -- ORDER_STATUS draft;     see the Code Dictionary section
                       :order_status_cancelled);      -- ORDER_STATUS cancelled; see the Code Dictionary section
```

**Worked query — revenue by month:**

```sql
SELECT strftime('%Y-%m', o.order_date) AS month,
       ROUND(SUM(o.order_total), 2)    AS recognized_revenue
FROM orders o
WHERE o.priority_code <> :internal_test_priority
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled)
GROUP BY strftime('%Y-%m', o.order_date)
ORDER BY month;
```

**Worked query — revenue by customer segment (CUSTOMER_SEGMENT):**

```sql
SELECT c.segment_code                  AS segment,   -- decode via CUSTOMER_SEGMENT; see the Code Dictionary section
       ROUND(SUM(o.order_total), 2)    AS recognized_revenue,
       COUNT(*)                        AS orders
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
WHERE o.priority_code <> :internal_test_priority
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled)
GROUP BY c.segment_code
ORDER BY recognized_revenue DESC;
```

**Worked query — revenue by channel (ORDER_CHANNEL):**

```sql
SELECT o.channel_code                  AS channel,   -- decode via ORDER_CHANNEL; see the Code Dictionary section
       ROUND(SUM(o.order_total), 2)    AS recognized_revenue
FROM orders o
WHERE o.priority_code <> :internal_test_priority
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled)
GROUP BY o.channel_code
ORDER BY recognized_revenue DESC;
```

**Worked query — revenue by product category (line grain, spans the SKU
bridge):**

```sql
SELECT pc.name                          AS category,
       ROUND(SUM(ol.line_total), 2)     AS revenue
FROM orders o
JOIN order_lines ol       ON ol.order_id    = o.order_id
JOIN products p           ON p.sku          = ol.sku          -- SKU side
JOIN product_categories pc ON pc.category_id = p.category_id
WHERE o.priority_code <> :internal_test_priority
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled)
GROUP BY pc.name
ORDER BY revenue DESC;
```

Note that the header and line grains are separate queries; never mix them in one
`SUM`.

---

### Metric: Order count and average order value (AOV)

**Definition.** *Order count* is the number of distinct reportable orders in the
period. *Average order value* is recognized revenue divided by order count —
the mean dollar value of a reportable order.

**Tables / columns.** `orders(order_id, order_total, status, priority_code,
order_date)`.

**Filters.** Same as revenue: exclude ORDER_PRIORITY `internal_test`; exclude
ORDER_STATUS `cancelled` and `draft`. Order count and AOV **must** use the same
population as the revenue they explain, or the average will not reconcile.

**Worked query — order count and AOV, overall and by month:**

```sql
SELECT strftime('%Y-%m', o.order_date)                    AS month,
       COUNT(*)                                            AS order_count,
       ROUND(SUM(o.order_total), 2)                        AS revenue,
       ROUND(SUM(o.order_total) * 1.0 / COUNT(*), 2)       AS avg_order_value
FROM orders o
WHERE o.priority_code <> :internal_test_priority           -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status NOT IN (:order_status_draft,                -- ORDER_STATUS draft;     see the Code Dictionary section
                       :order_status_cancelled)             -- ORDER_STATUS cancelled; see the Code Dictionary section
GROUP BY strftime('%Y-%m', o.order_date)
ORDER BY month;
```

Because `orders` is already one row per order, `COUNT(*)` is safe here. If you
have joined to a child table for any reason, switch to
`COUNT(DISTINCT o.order_id)` to avoid fan-out (**Exclusions, Reporting Conventions, and Data Quality**, §2.5). `* 1.0` forces float
division; integer division in SQLite would truncate the average.

---

### Metric: On-time delivery rate and late delivery rate

**Definition.** Among **delivered** shipments, the share that arrived on or
before their promised date. A shipment is **delivered** when its status is the
**SHIP_STATUS `delivered`** state. A delivered shipment is **late** when
`delivered_date > promised_date`, and **on-time** otherwise. On-time rate =
on-time delivered / all delivered (with a promise); late rate = late delivered /
all delivered (with a promise). The two sum to 100% of the graded population.

**Tables / columns.** `shipments(status, delivered_date, promised_date,
order_id)`; join `orders` for the internal-test exclusion.

**Filters.**

- Delivered only: `shipments.status = :ship_status_delivered` (**SHIP_STATUS**,
  not ORDER_STATUS — this is the classic cross-table decode error; the delivered
  state's integer here is *not* the fulfilled integer for orders).
- Both dates present: `delivered_date IS NOT NULL AND promised_date IS NOT NULL`.
  A delivered shipment with a NULL `promised_date` cannot be graded and is
  **excluded from the denominator** (**Exclusions, Reporting Conventions, and Data Quality**, §3.2), not counted as on-time.
- Exclude internal-test orders (join to `orders`).

**Worked query — on-time and late delivery rates:**

```sql
WITH delivered AS (
    SELECT s.shipment_id,
           s.delivered_date,
           s.promised_date
    FROM shipments s
    JOIN orders   o ON o.order_id = s.order_id
    WHERE s.status = :ship_status_delivered              -- SHIP_STATUS delivered; see the Code Dictionary section
      AND s.delivered_date IS NOT NULL
      AND s.promised_date  IS NOT NULL
      AND o.priority_code  <> :internal_test_priority     -- ORDER_PRIORITY internal_test; see the Code Dictionary section
)
SELECT COUNT(*)                                                          AS delivered_shipments,
       SUM(CASE WHEN delivered_date <= promised_date THEN 1 ELSE 0 END)  AS on_time,
       SUM(CASE WHEN delivered_date >  promised_date THEN 1 ELSE 0 END)  AS late,
       ROUND(100.0 * SUM(CASE WHEN delivered_date <= promised_date THEN 1 ELSE 0 END)
                   / COUNT(*), 1)                                        AS on_time_pct,
       ROUND(100.0 * SUM(CASE WHEN delivered_date >  promised_date THEN 1 ELSE 0 END)
                   / COUNT(*), 1)                                        AS late_pct
FROM delivered;
```

Date strings compare correctly lexicographically (`YYYY-MM-DD`), so
`delivered_date <= promised_date` is a valid on-time test without any conversion.
To split by carrier, join `carriers` and group by `carrier_id`; to split by
service level, join `carrier_services` and group by `service_level_code`
(**SERVICE_LEVEL**).

---

### Metric: Average transit time

**Definition.** For delivered shipments, the average number of days from ship to
delivery: `delivered_date − ship_date`. Reported in days.

**Tables / columns.** `shipments(status, ship_date, delivered_date, order_id)`;
join `orders` for the exclusion.

**Filters.** Delivered only (`status = :ship_status_delivered`, SHIP_STATUS);
`delivered_date IS NOT NULL`; exclude internal-test orders. Undelivered
shipments have a NULL `delivered_date` and are naturally excluded, but assert it
so a partial pipeline does not sneak in negative or NULL spans.

**Worked query — average transit time in days:**

```sql
SELECT ROUND(AVG(julianday(s.delivered_date) - julianday(s.ship_date)), 2)
           AS avg_transit_days,
       COUNT(*) AS delivered_shipments
FROM shipments s
JOIN orders o ON o.order_id = s.order_id
WHERE s.status = :ship_status_delivered                  -- SHIP_STATUS delivered; see the Code Dictionary section
  AND s.delivered_date IS NOT NULL
  AND o.priority_code  <> :internal_test_priority;        -- ORDER_PRIORITY internal_test; see the Code Dictionary section
```

`julianday()` returns a fractional day number; the difference is elapsed days.
For a per-carrier or per-service-level breakdown, join and group as in Section 3.
For median rather than mean transit time, compute it with a windowed ordering
(see the **Query Recipes and Pitfalls** section); the mean is the standard headline.

---

### Metric: Order cycle time (order to shipment / delivery)

**Definition.** How long from order placement to the order leaving (or arriving).
Two variants:

- **Order-to-ship** — `order_date` to the **first** shipment's `ship_date`. This
  is the operational fulfillment latency.
- **Order-to-deliver** — `order_date` to the **first** shipment's
  `delivered_date`. This is total time to the customer.

Because an order can have multiple shipments, take the **earliest** ship /
delivered date per order with `MIN(...)`.

**Tables / columns.** `orders(order_id, order_date, priority_code, status)`;
`shipments(order_id, ship_date, delivered_date, status)`.

**Filters.** Exclude internal-test orders. For order-to-deliver, require a
delivered shipment (`delivered_date IS NOT NULL`); for order-to-ship, any
shipment with a `ship_date` qualifies. Restricting to fulfilled orders
(ORDER_STATUS `fulfilled`) is reasonable when you want only completed orders —
state your choice.

**Worked query — average order-to-ship and order-to-deliver, in days:**

```sql
WITH first_ship AS (
    SELECT s.order_id,
           MIN(s.ship_date)                                          AS first_ship_date,
           MIN(CASE WHEN s.delivered_date IS NOT NULL
                    THEN s.delivered_date END)                       AS first_delivered_date
    FROM shipments s
    GROUP BY s.order_id
)
SELECT ROUND(AVG(julianday(fs.first_ship_date)
                 - julianday(o.order_date)), 2)                      AS avg_order_to_ship_days,
       ROUND(AVG(julianday(fs.first_delivered_date)
                 - julianday(o.order_date)), 2)                      AS avg_order_to_deliver_days
FROM orders o
JOIN first_ship fs ON fs.order_id = o.order_id
WHERE o.priority_code <> :internal_test_priority;         -- ORDER_PRIORITY internal_test; see the Code Dictionary section
```

`AVG` ignores the NULL `first_delivered_date` rows (orders with no delivered
shipment yet), so the order-to-deliver average is over delivered orders while
order-to-ship covers all shipped orders — a deliberate difference in
denominators worth calling out when you present both.

---

### Metric: Fill rate / order fulfillment rate

**Definition.** The share of **eligible** orders that we successfully fulfilled.
An order is **fulfilled** when its status is ORDER_STATUS `fulfilled`. The
eligible population is **real committed demand**: orders that are not draft, not
cancelled, and not internal-test priority. Fill rate = fulfilled orders /
eligible orders.

**Tables / columns.** `orders(order_id, status, priority_code)`.

**Filters.** Denominator: exclude ORDER_PRIORITY `internal_test`, exclude
ORDER_STATUS `draft` and `cancelled` (drafts are not yet demand; cancellations
were withdrawn — neither is "eligible to be filled"). Numerator: of that
population, those with `status = :order_status_fulfilled`. Returned orders
(ORDER_STATUS `returned`) were fulfilled first and then returned; whether you
count them as fulfilled depends on the question — the query below counts only
the current `fulfilled` state and notes the choice.

**Worked query — order fulfillment (fill) rate:**

```sql
SELECT COUNT(*)                                                             AS eligible_orders,
       SUM(CASE WHEN status = :order_status_fulfilled THEN 1 ELSE 0 END)    AS fulfilled_orders,
       ROUND(100.0 * SUM(CASE WHEN status = :order_status_fulfilled THEN 1 ELSE 0 END)
                   / COUNT(*), 1)                                           AS fill_rate_pct
FROM orders
WHERE priority_code <> :internal_test_priority             -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND status NOT IN (:order_status_draft,                  -- ORDER_STATUS draft;     see the Code Dictionary section
                     :order_status_cancelled);              -- ORDER_STATUS cancelled; see the Code Dictionary section
```

A stricter, unit-level **fill rate** — units shipped divided by units ordered —
is defined together with OTIF in Section 15, since both need the ordered-vs-
shipped quantity comparison.

---

### Metric: Below reorder point / stockout risk

**Definition.** Inventory positions where physical stock has fallen to or below
the reorder trigger: `quantity_on_hand < reorder_point`. These are the
replenishment-risk lines. Related: **available quantity** =
`quantity_on_hand − quantity_allocated` — the stock free to promise to new
orders after commitments. A position can be above its reorder point yet have
little *available* stock if much of it is allocated.

**Tables / columns.** `inventory(warehouse_id, item_code, quantity_on_hand,
quantity_allocated, reorder_point, reorder_qty)`; join `products` (via
`item_code = product_id`) for names and `is_active`; optionally `warehouses` for
the active-warehouse set.

**Filters.** No order-side exclusion applies (this is pure inventory). For a
*current* operational view, restrict to active products and active warehouses
(**Exclusions, Reporting Conventions, and Data Quality**, §2.6) since retired items/sites are not actionable replenishment targets.

**Worked query — positions below reorder point, current operational set:**

```sql
SELECT w.code                                          AS warehouse,
       p.sku                                           AS sku,
       p.name                                          AS product,
       i.quantity_on_hand,
       i.reorder_point,
       i.quantity_on_hand - i.quantity_allocated       AS available_qty,
       i.reorder_qty                                   AS suggested_reorder_qty
FROM inventory  i
JOIN products   p ON p.product_id = i.item_code         -- item_code = product_id
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
WHERE i.quantity_on_hand < i.reorder_point
  AND p.is_active = 1
  AND w.is_active = 1
ORDER BY (i.reorder_point - i.quantity_on_hand) DESC;
```

**Worked query — hard stockout (nothing available to promise):**

```sql
SELECT w.code AS warehouse, p.sku, p.name,
       i.quantity_on_hand, i.quantity_allocated
FROM inventory  i
JOIN products   p ON p.product_id  = i.item_code
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
WHERE (i.quantity_on_hand - i.quantity_allocated) <= 0
  AND p.is_active = 1 AND w.is_active = 1;
```

`inventory` is unique per `(warehouse_id, item_code)`, so these rows are already
one-per-position — no fan-out. To count *distinct products* at risk across the
network rather than positions, use `COUNT(DISTINCT i.item_code)`.

---

### Metric: Days of supply / inventory coverage

**Definition (conceptual).** How many days the current on-hand stock would last
at the recent outbound rate: `days_of_supply = quantity_on_hand ÷ average daily
outbound units`. It converts a static stock level into a time horizon and is the
demand-aware companion to the reorder-point view in Section 7.

**Tables / columns.** `inventory(item_code, warehouse_id, quantity_on_hand)` for
the numerator; **outbound** from `inventory_transactions(item_code,
warehouse_id, txn_type_code, quantity_delta, txn_ts)` — the shipment movements
(INV_TXN_TYPE `shipment`) over a recent window. `inventory_transactions` is a
movement ledger where outbound shipment deltas are negative; take the absolute
value for units shipped.

**Filters.** Choose a trailing window relative to `TODAY = 2024-12-31` (e.g. the
last 90 days). Restrict outbound to the shipment transaction type
(**INV_TXN_TYPE**, *not* a status code set). Divide the window's total outbound
by the number of days to get a daily rate; guard against divide-by-zero for
items with no recent movement.

**Worked query — days of supply per warehouse/product over a 90-day window:**

```sql
WITH outbound AS (
    SELECT it.warehouse_id,
           it.item_code,
           SUM(ABS(it.quantity_delta)) AS units_out_90d
    FROM inventory_transactions it
    WHERE it.txn_type_code = :inv_txn_shipment            -- INV_TXN_TYPE shipment; see the Code Dictionary section
      AND it.txn_ts >= date('2024-12-31', '-90 days')     -- window relative to TODAY
      AND it.txn_ts <  date('2024-12-31', '+1 day')
    GROUP BY it.warehouse_id, it.item_code
)
SELECT w.code                                             AS warehouse,
       p.sku,
       i.quantity_on_hand,
       o.units_out_90d,
       ROUND(o.units_out_90d / 90.0, 3)                   AS avg_daily_out,
       CASE WHEN o.units_out_90d > 0
            THEN ROUND(i.quantity_on_hand / (o.units_out_90d / 90.0), 1)
            ELSE NULL END                                 AS days_of_supply
FROM inventory  i
JOIN products   p ON p.product_id  = i.item_code
JOIN warehouses w ON w.warehouse_id = i.warehouse_id
LEFT JOIN outbound o ON o.warehouse_id = i.warehouse_id
                    AND o.item_code    = i.item_code
WHERE p.is_active = 1 AND w.is_active = 1
ORDER BY days_of_supply ASC;   -- NULLs (no recent outbound) sort first in SQLite
```

A NULL `days_of_supply` means no outbound in the window — either a dead item or a
data gap, not "infinite coverage"; treat it as a review flag, not a pass.

---

### Metric: Inventory accuracy (cycle counts)

**Definition.** How well the system's book quantity matches the physical count,
measured from `cycle_counts`. The per-count **variance** =
`counted_qty − system_qty` (positive = more on the shelf than the book;
negative = shrink). Two headline measures:

- **Absolute variance rate** = `SUM(ABS(variance)) ÷ SUM(system_qty)` — the
  fraction of book units that were miscounted, in either direction. Lower is
  better.
- **Count accuracy** = share of counts with **zero** variance (a perfect
  location). Higher is better.

**Tables / columns.** `cycle_counts(item_code, warehouse_id, system_qty,
counted_qty, variance, count_date, status_code)`. The stored `variance` column
already equals `counted_qty − system_qty`; you can use it directly or recompute.

**Filters.** No order exclusion (inventory audit data). Consider restricting to
completed counts — `status_code` is the **CYCLE_COUNT_STATUS** code set; a
`reconciled` (or at least `counted`) state means the count actually happened, so
`scheduled`-but-not-yet-counted rows do not dilute the metric. Optionally window
by `count_date` relative to `TODAY`.

**Worked query — absolute variance rate and count accuracy by warehouse:**

```sql
SELECT w.code                                                          AS warehouse,
       COUNT(*)                                                        AS counts,
       SUM(ABS(cc.variance))                                           AS abs_variance_units,
       SUM(cc.system_qty)                                              AS system_units,
       ROUND(100.0 * SUM(ABS(cc.variance)) / NULLIF(SUM(cc.system_qty), 0), 2)
                                                                       AS abs_variance_rate_pct,
       ROUND(100.0 * SUM(CASE WHEN cc.variance = 0 THEN 1 ELSE 0 END)
                   / COUNT(*), 1)                                      AS count_accuracy_pct
FROM cycle_counts cc
JOIN warehouses   w ON w.warehouse_id = cc.warehouse_id
WHERE cc.status_code = :cycle_count_status_reconciled     -- CYCLE_COUNT_STATUS reconciled; see the Code Dictionary section
GROUP BY w.code
ORDER BY abs_variance_rate_pct DESC;
```

`NULLIF(SUM(cc.system_qty), 0)` protects against divide-by-zero. Note that this
`status_code` is CYCLE_COUNT_STATUS — do not reuse a "done" integer from
PICK_STATUS or PO_STATUS here (the **Lifecycle and Statuses** section).

---

### Metric: Return rate

**Definition.** How much of what we sell comes back. Two standard denominators:

- **Returns per order** = distinct returned orders / reportable orders. A simple
  order-level rate.
- **Return rate per unit shipped** = returned units / shipped units. A
  volume-weighted rate that is more precise for product-level analysis.

Both can be split by **RETURN_REASON** (`returns.reason_code`) to see *why*
things come back.

**Tables / columns.** `returns(return_id, order_id, reason_code, status,
received_date)`, `return_lines(return_id, sku, quantity)` for units returned;
`orders` for the reportable population; `shipment_items(quantity)` for units
shipped.

**Filters.** Exclude internal-test orders on both sides (a return against a
test order is test traffic). Decide which return statuses count: for a
*realized* return rate, restrict to received/refunded returns
(`returns.status` is the **RETURN_STATUS** code set) so mere requests that were
rejected or never arrived are not counted; for a *requested* return rate, count
all RMAs. State which.

**Worked query — order-level return rate, overall:**

```sql
WITH reportable AS (
    SELECT order_id
    FROM orders
    WHERE priority_code <> :internal_test_priority         -- ORDER_PRIORITY internal_test; see the Code Dictionary section
      AND status NOT IN (:order_status_draft, :order_status_cancelled)
),
returned AS (
    SELECT DISTINCT r.order_id
    FROM returns r
    JOIN reportable rp ON rp.order_id = r.order_id
    WHERE r.status IN (:return_status_received,            -- RETURN_STATUS received; see the Code Dictionary section
                       :return_status_refunded)             -- RETURN_STATUS refunded; see the Code Dictionary section
)
SELECT (SELECT COUNT(*) FROM reportable)                          AS reportable_orders,
       (SELECT COUNT(*) FROM returned)                            AS returned_orders,
       ROUND(100.0 * (SELECT COUNT(*) FROM returned)
                   / (SELECT COUNT(*) FROM reportable), 2)        AS return_rate_pct;
```

**Worked query — returned units per reason (RETURN_REASON):**

```sql
SELECT r.reason_code                       AS return_reason,   -- decode via RETURN_REASON; see the Code Dictionary section
       SUM(rl.quantity)                     AS units_returned,
       COUNT(DISTINCT r.return_id)          AS return_count
FROM returns      r
JOIN return_lines rl ON rl.return_id = r.return_id
JOIN orders       o  ON o.order_id   = r.order_id
WHERE o.priority_code <> :internal_test_priority
  AND r.status IN (:return_status_received, :return_status_refunded)
GROUP BY r.reason_code
ORDER BY units_returned DESC;
```

For a true per-unit rate, divide `SUM(return_lines.quantity)` by
`SUM(shipment_items.quantity)` over the same reportable, non-test population,
computing each sum separately (they are different grains — combining them in one
join fans out).

---

### Metric: Delivery exception rate

**Definition.** How often shipments hit a delivery problem. Exception rate =
shipments with at least one delivery exception / total shipments. Can be split by
**EXCEPTION_TYPE** (`delivery_exceptions.exception_type_code`) or by carrier.
A related operational measure is the **open-exception count**: exceptions with a
NULL `resolved_ts` (**Exclusions, Reporting Conventions, and Data Quality**, §3.2).

**Tables / columns.** `delivery_exceptions(shipment_id, exception_type_code,
resolved_ts)`, `shipments(shipment_id, carrier_id, order_id)`; `orders` for the
exclusion; optionally `carriers`.

**Filters.** Exclude internal-test orders (join shipment → order). Count a
shipment as "with exception" if it has one or more exception rows; use
`COUNT(DISTINCT shipment_id)` so a shipment with several exceptions is not
counted multiple times (fan-out, **Exclusions, Reporting Conventions, and Data Quality**, §2.5).

**Worked query — exception rate by carrier:**

```sql
WITH ship AS (
    SELECT s.shipment_id, s.carrier_id
    FROM shipments s
    JOIN orders   o ON o.order_id = s.order_id
    WHERE o.priority_code <> :internal_test_priority        -- ORDER_PRIORITY internal_test; see the Code Dictionary section
),
exc AS (
    SELECT DISTINCT shipment_id
    FROM delivery_exceptions
)
SELECT c.name                                                      AS carrier,
       COUNT(*)                                                    AS shipments,
       SUM(CASE WHEN e.shipment_id IS NOT NULL THEN 1 ELSE 0 END)  AS shipments_with_exception,
       ROUND(100.0 * SUM(CASE WHEN e.shipment_id IS NOT NULL THEN 1 ELSE 0 END)
                   / COUNT(*), 2)                                  AS exception_rate_pct
FROM ship s
JOIN carriers c ON c.carrier_id = s.carrier_id
LEFT JOIN exc e ON e.shipment_id = s.shipment_id
GROUP BY c.name
ORDER BY exception_rate_pct DESC;
```

**Worked query — exception mix by type (EXCEPTION_TYPE):**

```sql
SELECT de.exception_type_code             AS exception_type,   -- decode via EXCEPTION_TYPE; see the Code Dictionary section
       COUNT(*)                            AS exception_count,
       SUM(CASE WHEN de.resolved_ts IS NULL THEN 1 ELSE 0 END) AS still_open
FROM delivery_exceptions de
JOIN shipments s ON s.shipment_id = de.shipment_id
JOIN orders    o ON o.order_id    = s.order_id
WHERE o.priority_code <> :internal_test_priority
GROUP BY de.exception_type_code
ORDER BY exception_count DESC;
```

---

### Metric: Gross margin

**Definition.** Revenue minus cost of goods sold: `gross_margin = revenue −
COGS`, and `gross_margin_pct = gross_margin ÷ revenue`. Revenue is the
line-grain recognized revenue from Section 1. COGS is the product cost of the
units sold, taken from supplier cost. See the **Pricing, Costs & Billing** section for the
full treatment of price vs cost; the essentials:

- **Revenue per line** = `order_lines.line_total` (already net of line
  discounts).
- **Unit cost** comes from `supplier_products.unit_cost`. A product can have more
  than one supplier, so pick a single cost per product — the standard choice is
  the **preferred** supplier (`supplier_products.is_preferred = 1`). Where no
  preferred row exists, fall back to the minimum or average supplier cost and say
  so.

**Tables / columns.** `order_lines(order_id, sku, quantity, line_total)`,
`orders(order_id, status, priority_code)`, `products(product_id, sku)`,
`supplier_products(item_code, unit_cost, is_preferred)`. This metric **spans the
identifier bridge**: order lines carry `sku`, supplier cost carries `item_code`;
join through `products` (the **Identifiers and Keys** section, **Exclusions, Reporting Conventions, and Data Quality** §3.1).

**Filters.** Exclude internal-test orders; exclude cancelled and draft orders
(same population as revenue). Use one cost per product to avoid multiplying the
line by every supplier that sells it (fan-out).

**Worked query — gross margin by product category:**

```sql
WITH pref_cost AS (
    -- One cost per product: the preferred supplier's unit_cost
    SELECT sp.item_code,
           MIN(sp.unit_cost) AS unit_cost      -- MIN guards against >1 preferred row
    FROM supplier_products sp
    WHERE sp.is_preferred = 1
    GROUP BY sp.item_code
)
SELECT pc.name                                                     AS category,
       ROUND(SUM(ol.line_total), 2)                                AS revenue,
       ROUND(SUM(ol.quantity * pcst.unit_cost), 2)                 AS cogs,
       ROUND(SUM(ol.line_total) - SUM(ol.quantity * pcst.unit_cost), 2)
                                                                   AS gross_margin,
       ROUND(100.0 * (SUM(ol.line_total) - SUM(ol.quantity * pcst.unit_cost))
                   / NULLIF(SUM(ol.line_total), 0), 1)             AS gross_margin_pct
FROM orders o
JOIN order_lines ol        ON ol.order_id    = o.order_id
JOIN products    p         ON p.sku          = ol.sku              -- SKU side
JOIN product_categories pc ON pc.category_id = p.category_id
LEFT JOIN pref_cost pcst   ON pcst.item_code = p.product_id        -- item_code side
WHERE o.priority_code <> :internal_test_priority                   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled)
GROUP BY pc.name
ORDER BY gross_margin DESC;
```

The `LEFT JOIN` to `pref_cost` keeps revenue intact even for products with no
preferred supplier cost; those lines contribute revenue but NULL cost, so their
margin is understated — surface the count of costless lines when precision
matters. This is a **product** cost margin; it does not net freight (carrier
invoices) or returns. A fully loaded margin subtracts those too — see the **Pricing, Costs & Billing** section.

---

### Metric: Invoice aging and DSO for accounts payable

**Definition.** These are **payables** (money we owe), from two invoice tables:
`supplier_invoices` (what suppliers bill us for goods) and `carrier_invoices`
(what carriers bill us for freight). Both use the **INVOICE_STATUS** code set on
their `status_code` column, and both carry `invoice_date`, `due_date`, and a
nullable `paid_date`.

- **Open payables** — invoices not yet paid: `paid_date IS NULL` (equivalently,
  status is not the `paid` INVOICE_STATUS value). A NULL `paid_date` is the
  authoritative "unpaid" signal (**Exclusions, Reporting Conventions, and Data Quality**, §3.2).
- **Invoice aging** — for open invoices, days past due as of `TODAY`:
  `julianday('2024-12-31') − julianday(due_date)`, bucketed (current /
  1–30 / 31–60 / 60+).
- **Days payable / DSO-style figure (conceptual)** — for *paid* invoices, the
  average days from invoice to payment: `AVG(paid_date − invoice_date)`. (Strict
  DSO is a receivables metric; the payables analogue here is days-to-pay. Name it
  as payables so it is not confused with sales DSO.)

**Tables / columns.** `supplier_invoices` / `carrier_invoices`(`amount`,
`status_code`, `invoice_date`, `due_date`, `paid_date`).

**Filters.** No order exclusion — invoices are supplier/carrier-side. For aging,
open invoices only (`paid_date IS NULL`); for days-to-pay, paid invoices only
(`paid_date IS NOT NULL`).

**Worked query — supplier-invoice aging buckets, open payables as of TODAY:**

```sql
SELECT CASE
         WHEN julianday('2024-12-31') <= julianday(due_date)      THEN 'current'
         WHEN julianday('2024-12-31') -  julianday(due_date) <= 30 THEN '1-30'
         WHEN julianday('2024-12-31') -  julianday(due_date) <= 60 THEN '31-60'
         ELSE '60+'
       END                                       AS aging_bucket,
       COUNT(*)                                   AS open_invoices,
       ROUND(SUM(amount), 2)                      AS open_amount
FROM supplier_invoices
WHERE paid_date IS NULL                           -- unpaid; NULL paid_date is authoritative (see the Exclusions, Reporting Conventions, and Data Quality section)
GROUP BY aging_bucket
ORDER BY open_amount DESC;
```

**Worked query — average days-to-pay (payables), carrier invoices:**

```sql
SELECT ROUND(AVG(julianday(paid_date) - julianday(invoice_date)), 1)
           AS avg_days_to_pay,
       COUNT(*) AS paid_invoices
FROM carrier_invoices
WHERE paid_date IS NOT NULL
  AND status_code = :invoice_status_paid;         -- INVOICE_STATUS paid; see the Code Dictionary section
```

The two invoice tables are structurally identical and both use INVOICE_STATUS,
so the same aging logic applies to each; report them separately (supplier COGS
payables vs carrier freight payables) or `UNION ALL` them for a total open-
payables view. Disputed invoices (INVOICE_STATUS `disputed`) are worth breaking
out separately when reporting collectible/payable balances.

---

### Metric: Perfect order / OTIF (on-time, in-full)

**Definition.** OTIF — **on-time in full** — is the gold-standard service metric:
the share of orders delivered **both** on time **and** complete. It combines two
independent conditions at the **order** level:

- **On-time** — the order's delivery met its promise. Using the shipment view
  from Section 3: the order's shipments are delivered (SHIP_STATUS `delivered`)
  and the (last) delivery date is on or before the promise. A common, strict
  rule is that **every** shipment for the order delivered on time.
- **In-full** — the order shipped complete: the units shipped equal the units
  ordered. Compare `SUM(order_lines.quantity)` for the order against
  `SUM(shipment_items.quantity)` for the order.

OTIF = orders that are both on-time and in-full / eligible orders.

**Tables / columns.** `orders`, `order_lines(order_id, quantity)`,
`shipments(order_id, status, delivered_date, promised_date)`,
`shipment_items(shipment_id, quantity)`.

**Filters.** Exclude internal-test orders; take the eligible/fulfilled
population. Grade only orders that have both an ordered quantity and shipment
activity; an order with no shipment cannot be OTIF.

**Worked query — in-full flag (units shipped vs ordered) per order:**

```sql
WITH ordered AS (
    SELECT ol.order_id, SUM(ol.quantity) AS units_ordered
    FROM order_lines ol
    GROUP BY ol.order_id
),
shipped AS (
    SELECT s.order_id, SUM(si.quantity) AS units_shipped
    FROM shipments      s
    JOIN shipment_items si ON si.shipment_id = s.shipment_id
    GROUP BY s.order_id
)
SELECT o.order_id,
       od.units_ordered,
       COALESCE(sh.units_shipped, 0)                                  AS units_shipped,
       CASE WHEN COALESCE(sh.units_shipped, 0) >= od.units_ordered
            THEN 1 ELSE 0 END                                         AS in_full
FROM orders o
JOIN ordered od ON od.order_id = o.order_id
LEFT JOIN shipped sh ON sh.order_id = o.order_id
WHERE o.priority_code <> :internal_test_priority                      -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled);
```

**Worked query — full OTIF rate:**

```sql
WITH ordered AS (
    SELECT order_id, SUM(quantity) AS units_ordered
    FROM order_lines GROUP BY order_id
),
shipped AS (
    SELECT s.order_id, SUM(si.quantity) AS units_shipped
    FROM shipments s
    JOIN shipment_items si ON si.shipment_id = s.shipment_id
    GROUP BY s.order_id
),
on_time AS (
    -- An order is on-time if it has delivered shipments and NONE delivered late
    SELECT s.order_id,
           SUM(CASE WHEN s.status = :ship_status_delivered
                     AND s.delivered_date IS NOT NULL THEN 1 ELSE 0 END)          AS delivered_ships,
           SUM(CASE WHEN s.status = :ship_status_delivered
                     AND s.delivered_date IS NOT NULL
                     AND s.promised_date IS NOT NULL
                     AND s.delivered_date > s.promised_date THEN 1 ELSE 0 END)     AS late_ships
    FROM shipments s
    GROUP BY s.order_id
)
SELECT COUNT(*)                                                                    AS eligible_orders,
       SUM(CASE WHEN COALESCE(sh.units_shipped,0) >= od.units_ordered
                 AND ot.delivered_ships > 0
                 AND ot.late_ships = 0
                THEN 1 ELSE 0 END)                                                 AS otif_orders,
       ROUND(100.0 * SUM(CASE WHEN COALESCE(sh.units_shipped,0) >= od.units_ordered
                               AND ot.delivered_ships > 0
                               AND ot.late_ships = 0
                              THEN 1 ELSE 0 END) / COUNT(*), 1)                     AS otif_pct
FROM orders o
JOIN ordered od  ON od.order_id = o.order_id
LEFT JOIN shipped sh ON sh.order_id = o.order_id
LEFT JOIN on_time ot ON ot.order_id = o.order_id
WHERE o.priority_code <> :internal_test_priority                                   -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled);
```

The on-time and in-full pieces are aggregated **before** joining back to orders,
so the header row is not fanned out by lines, shipments, or items (**Exclusions, Reporting Conventions, and Data Quality**, §2.5).
OTIF is deliberately strict: an order that is on-time but short-shipped, or
complete but late, is not OTIF. Report the two components alongside the combined
figure so a low OTIF can be attributed to timeliness vs completeness.

---

### Metric: Inventory turnover

**Definition.** How many times stock cycles through a location over a period:
`turnover = units (or cost) shipped in the period ÷ average units (or cost) on
hand`. It is the demand-throughput companion to days-of-supply (Section 8): high
turnover means stock moves quickly, low turnover flags slow-movers and dead
stock. Reported unitless (times per period). A simple, defensible form uses the
recent outbound units from the movement ledger as the numerator and current
on-hand as a stand-in for average on-hand.

**Tables / columns.** `inventory_transactions(item_code, warehouse_id,
txn_type_code, quantity_delta, txn_ts)` for outbound; `inventory(item_code,
warehouse_id, quantity_on_hand)` for the on-hand base; `products` for names and
`is_active`.

**Filters.** No order exclusion (inventory throughput). Outbound is the shipment
movement type — **INV_TXN_TYPE `shipment`** (a transaction-type code set, not a
status). Window relative to `TODAY = 2024-12-31`. Guard against a zero on-hand
denominator.

**Worked query — 90-day unit turnover by product across the network:**

```sql
WITH outbound AS (
    SELECT it.item_code,
           SUM(ABS(it.quantity_delta)) AS units_out
    FROM inventory_transactions it
    WHERE it.txn_type_code = :inv_txn_shipment            -- INV_TXN_TYPE shipment; see the Code Dictionary section
      AND it.txn_ts >= date('2024-12-31', '-90 days')
      AND it.txn_ts <  date('2024-12-31', '+1 day')
    GROUP BY it.item_code
),
on_hand AS (
    SELECT item_code, SUM(quantity_on_hand) AS units_on_hand
    FROM inventory
    GROUP BY item_code
)
SELECT p.sku,
       p.name,
       COALESCE(ob.units_out, 0)                           AS units_out_90d,
       oh.units_on_hand,
       CASE WHEN oh.units_on_hand > 0
            THEN ROUND(COALESCE(ob.units_out, 0) * 1.0 / oh.units_on_hand, 2)
            ELSE NULL END                                  AS turnover_90d
FROM products p
JOIN on_hand oh   ON oh.item_code = p.product_id
LEFT JOIN outbound ob ON ob.item_code = p.product_id
WHERE p.is_active = 1
ORDER BY turnover_90d DESC NULLS LAST;
```

A very low or NULL turnover with meaningful on-hand is a slow-mover / dead-stock
flag; a very high turnover with low on-hand is a stockout-risk flag that pairs
with Section 7. Annualize by scaling the window (× 365/90) if you need a
per-year figure, and say you did.

---

### Metric: Freight cost per delivered shipment

**Definition.** What transportation costs us per unit of service delivered:
`freight cost per shipment = carrier freight billed ÷ delivered shipments`.
Freight is billed on `carrier_invoices`; the service delivered is counted from
`shipments`. Because carrier invoices are billed at the carrier level (not tied
to an individual shipment in this model), the standard form is a **ratio of two
carrier-level aggregates** over the same period — total freight billed by a
carrier divided by that carrier's delivered shipments — rather than a per-row
join.

**Tables / columns.** `carrier_invoices(carrier_id, amount, invoice_date,
status_code)`; `shipments(carrier_id, status, delivered_date, order_id)`;
`orders` for the exclusion; `carriers` for names.

**Filters.** Exclude internal-test orders from the shipment count (test shipments
are not billable service we want in the denominator). Count delivered shipments
via SHIP_STATUS `delivered`. Choose whether to use all carrier invoices or only
approved/paid ones (INVOICE_STATUS) for the freight numerator — state which; a
cost-accrual view uses all non-draft invoices, a cash view uses paid.

**Worked query — freight cost per delivered shipment, by carrier:**

```sql
WITH freight AS (
    SELECT carrier_id, SUM(amount) AS freight_billed
    FROM carrier_invoices
    WHERE status_code <> :invoice_status_draft            -- INVOICE_STATUS draft; see the Code Dictionary section
    GROUP BY carrier_id
),
delivered AS (
    SELECT s.carrier_id, COUNT(*) AS delivered_shipments
    FROM shipments s
    JOIN orders   o ON o.order_id = s.order_id
    WHERE s.status = :ship_status_delivered               -- SHIP_STATUS delivered; see the Code Dictionary section
      AND o.priority_code <> :internal_test_priority        -- ORDER_PRIORITY internal_test; see the Code Dictionary section
    GROUP BY s.carrier_id
)
SELECT c.name                                                     AS carrier,
       ROUND(f.freight_billed, 2)                                 AS freight_billed,
       d.delivered_shipments,
       ROUND(f.freight_billed / NULLIF(d.delivered_shipments, 0), 2)
                                                                  AS cost_per_delivered_shipment
FROM carriers c
LEFT JOIN freight   f ON f.carrier_id = c.carrier_id
LEFT JOIN delivered d ON d.carrier_id = c.carrier_id
WHERE f.freight_billed IS NOT NULL
ORDER BY cost_per_delivered_shipment DESC;
```

The two aggregates are computed separately and joined at carrier grain, so
neither fans the other out. Pair this with the on-time and exception rates
(Sections 3, 11) for a full carrier scorecard: cost, timeliness, and reliability
together.

---

### Metric: Supplier lead time and on-time PO receipt

**Definition.** How dependable our inbound supply is. Two measures:

- **Actual receipt lead time** — days from PO placement to receipt:
  `replenishment_orders.received_date − order_date`, for received POs.
- **On-time receipt rate** — share of received POs received on or before their
  `expected_date`. On-time when `received_date <= expected_date`.

These are the inbound analogue of transit time (Section 4) and on-time delivery
(Section 3), on the supply side.

**Tables / columns.** `replenishment_orders(repl_id, supplier_id, status,
order_date, expected_date, received_date)`; `suppliers(supplier_id, name,
default_lead_time_days, status_code)`.

**Filters.** No order (customer) exclusion — this is procurement. Received POs
only: `received_date IS NOT NULL`. The PO's own status is the **PO_STATUS** code
set (`replenishment_orders.status`); a fully received PO is the `received`
PO_STATUS value — do **not** reuse the ORDER_STATUS `fulfilled` integer or the
SHIP_STATUS `delivered` integer here (the **Lifecycle and Statuses** section, **Exclusions, Reporting Conventions, and Data Quality** §3.4). Consider restricting to
active suppliers (SUPPLIER_STATUS `active`) for a current-vendor view.

**Worked query — lead time and on-time receipt by supplier:**

```sql
SELECT s.name                                                              AS supplier,
       s.default_lead_time_days,
       COUNT(*)                                                            AS received_pos,
       ROUND(AVG(julianday(ro.received_date) - julianday(ro.order_date)), 1)
                                                                           AS avg_actual_lead_days,
       ROUND(100.0 * SUM(CASE WHEN ro.received_date <= ro.expected_date
                              THEN 1 ELSE 0 END) / COUNT(*), 1)            AS on_time_receipt_pct
FROM replenishment_orders ro
JOIN suppliers s ON s.supplier_id = ro.supplier_id
WHERE ro.received_date IS NOT NULL
  AND ro.status = :po_status_received                     -- PO_STATUS received; see the Code Dictionary section
GROUP BY s.name, s.default_lead_time_days
ORDER BY on_time_receipt_pct ASC;
```

Comparing `avg_actual_lead_days` against `default_lead_time_days` shows which
suppliers systematically run longer than their quoted lead time — a direct input
to reorder-point and safety-stock decisions (Section 7).

---

### Metric: Pick productivity and pick cycle time

**Definition.** How efficiently the warehouse assembles orders. Two useful cuts:

- **Pick cycle time** — hours from a pick task being created to completion:
  `pick_tasks.completed_ts − created_ts`, for completed tasks.
- **Pick completion / short rate** — share of pick tasks that completed cleanly
  vs those that came up short. A **completed** task is the PICK_STATUS
  `completed` state; a **short** task is the PICK_STATUS `short` state.

**Tables / columns.** `pick_tasks(pick_id, warehouse_id, order_id, status_code,
created_ts, completed_ts)`; join `orders` for the exclusion; `warehouses` for
names.

**Filters.** Exclude internal-test orders (a pick for a test order is test
work). The status column here is `status_code` on the **PICK_STATUS** code set —
its `completed` integer is distinct from every other table's "done" value
(the **Lifecycle and Statuses** section). Cycle time needs `completed_ts IS NOT NULL`.

**Worked query — pick cycle time and short rate by warehouse:**

```sql
SELECT w.code                                                              AS warehouse,
       COUNT(*)                                                            AS pick_tasks,
       ROUND(AVG(CASE WHEN pt.completed_ts IS NOT NULL
                      THEN (julianday(pt.completed_ts) - julianday(pt.created_ts)) * 24.0
                 END), 2)                                                  AS avg_pick_hours,
       ROUND(100.0 * SUM(CASE WHEN pt.status_code = :pick_status_completed
                              THEN 1 ELSE 0 END) / COUNT(*), 1)            AS completed_pct,
       ROUND(100.0 * SUM(CASE WHEN pt.status_code = :pick_status_short
                              THEN 1 ELSE 0 END) / COUNT(*), 1)            AS short_pct
FROM pick_tasks pt
JOIN orders     o ON o.order_id     = pt.order_id
JOIN warehouses w ON w.warehouse_id = pt.warehouse_id
WHERE o.priority_code <> :internal_test_priority          -- ORDER_PRIORITY internal_test; see the Code Dictionary section
GROUP BY w.code
ORDER BY short_pct DESC;
```

The `× 24.0` converts the fractional-day `julianday` difference into hours. A
rising short rate at a warehouse usually correlates with below-reorder-point
positions there (Section 7) — a pick goes short because the stock was not on the
shelf.

---

### Metric: Payment capture / realization rate

**Definition.** The share of reportable order value that has been actually
**captured** (collected), versus merely authorized, refunded, voided, or failed.
Captured payments are the `captured` state of the **PAYMENT_STATUS** code set on
`payments.status_code`. Useful as a cash-realization check against recognized
revenue.

**Tables / columns.** `payments(order_id, status_code, amount)`; `orders` for the
reportable population.

**Filters.** Exclude internal-test orders (their payments are test captures);
exclude cancelled orders. Captured amount uses PAYMENT_STATUS `captured`;
refunds/voids/fails are separate states in the same set. Because there is one
payment row per non-draft order (its `amount` equals the `order_total`), sum
`payments.amount` at the payment grain — do not join payments to order lines
(which would fan out).

**Worked query — captured amount vs recognized revenue:**

```sql
WITH reportable AS (
    SELECT order_id, order_total
    FROM orders
    WHERE priority_code <> :internal_test_priority         -- ORDER_PRIORITY internal_test; see the Code Dictionary section
      AND status NOT IN (:order_status_draft, :order_status_cancelled)
)
SELECT ROUND((SELECT SUM(order_total) FROM reportable), 2)                 AS recognized_revenue,
       ROUND(SUM(CASE WHEN p.status_code = :payment_status_captured
                      THEN p.amount ELSE 0 END), 2)                        AS captured_amount,
       ROUND(SUM(CASE WHEN p.status_code = :payment_status_refunded
                      THEN p.amount ELSE 0 END), 2)                        AS refunded_amount
FROM payments p
JOIN reportable r ON r.order_id = p.order_id;
```

Captured materially below recognized revenue is a collections or authorization
gap worth investigating; captured *above* it usually signals refunds netting —
reconcile against the refund column.

---

### Metric: Net revenue after returns

**Definition.** Recognized revenue (Section 1) less the value of what came back:
`net_revenue = gross recognized revenue − returned value`. Gross revenue keeps
returned orders in the population (**Exclusions, Reporting Conventions, and Data Quality**, §2.3); the *net* view subtracts the
dollar value of the returned lines explicitly. This is a deliberate, separate
calculation — never drop returned orders from the gross figure to approximate
net.

**Tables / columns.** Gross from `orders`/`order_lines` (Section 1); returned
value from `return_lines(sku, quantity)` valued at the line's sale price, joined
through `returns` to the reportable order. Because `return_lines` carries no
money column, value the returned units at the product's `order_lines.unit_price`
for that order (or `products.unit_price` as a fallback) — state which basis you
used.

**Filters.** Same reportable population and internal-test exclusion as revenue;
count only realized returns (RETURN_STATUS `received`/`refunded`) so
requested-but-rejected RMAs are not netted out.

**Worked query — gross vs net revenue by month, valuing returns at line price:**

```sql
WITH rev AS (
    SELECT strftime('%Y-%m', o.order_date) AS month,
           SUM(ol.line_total)              AS gross_rev
    FROM orders o
    JOIN order_lines ol ON ol.order_id = o.order_id
    WHERE o.priority_code <> :internal_test_priority       -- ORDER_PRIORITY internal_test; see the Code Dictionary section
      AND o.status NOT IN (:order_status_draft, :order_status_cancelled)
    GROUP BY month
),
ret AS (
    SELECT strftime('%Y-%m', o.order_date) AS month,
           SUM(rl.quantity * ol.unit_price) AS returned_value
    FROM returns      r
    JOIN orders       o  ON o.order_id  = r.order_id
    JOIN return_lines rl ON rl.return_id = r.return_id
    JOIN order_lines  ol ON ol.order_id = o.order_id AND ol.sku = rl.sku
    WHERE o.priority_code <> :internal_test_priority
      AND r.status IN (:return_status_received, :return_status_refunded)
    GROUP BY month
)
SELECT rev.month,
       ROUND(rev.gross_rev, 2)                                    AS gross_revenue,
       ROUND(COALESCE(ret.returned_value, 0), 2)                  AS returned_value,
       ROUND(rev.gross_rev - COALESCE(ret.returned_value, 0), 2)  AS net_revenue
FROM rev
LEFT JOIN ret ON ret.month = rev.month
ORDER BY rev.month;
```

Note the `return_lines`↔`order_lines` join keys on both `order_id` and `sku`, so
each returned line is valued at the price it actually sold for on that order.
Aggregate gross and returned value **separately** (as two CTEs) and subtract at
the end, so the two one-to-many relationships never fan each other out
(**Exclusions, Reporting Conventions, and Data Quality**, §2.5).

---

### Metric: Short-ship / backorder rate

**Definition.** How often we fail to ship an order complete. Short-ship rate =
orders where units shipped fell short of units ordered / eligible orders. It is
the complement of the "in-full" component of OTIF (Section 14) and a leading
indicator of stockout pressure (Section 7) and pick shortfalls (Section 18).

**Tables / columns.** `order_lines(order_id, quantity)` for ordered units;
`shipments`→`shipment_items(quantity)` for shipped units; `orders` for the
population.

**Filters.** Exclude internal-test orders; take the eligible (non-draft,
non-cancelled) population. Compare aggregated ordered vs shipped units per order.

**Worked query — short-ship rate and the shortfall units:**

```sql
WITH ordered AS (
    SELECT order_id, SUM(quantity) AS units_ordered
    FROM order_lines GROUP BY order_id
),
shipped AS (
    SELECT s.order_id, SUM(si.quantity) AS units_shipped
    FROM shipments s
    JOIN shipment_items si ON si.shipment_id = s.shipment_id
    GROUP BY s.order_id
)
SELECT COUNT(*)                                                                 AS eligible_orders,
       SUM(CASE WHEN COALESCE(sh.units_shipped,0) < od.units_ordered
                THEN 1 ELSE 0 END)                                              AS short_orders,
       ROUND(100.0 * SUM(CASE WHEN COALESCE(sh.units_shipped,0) < od.units_ordered
                              THEN 1 ELSE 0 END) / COUNT(*), 1)                 AS short_ship_pct,
       SUM(MAX(od.units_ordered - COALESCE(sh.units_shipped,0), 0))            AS total_shortfall_units
FROM orders o
JOIN ordered od  ON od.order_id = o.order_id
LEFT JOIN shipped sh ON sh.order_id = o.order_id
WHERE o.priority_code <> :internal_test_priority              -- ORDER_PRIORITY internal_test; see the Code Dictionary section
  AND o.status NOT IN (:order_status_draft, :order_status_cancelled);
```

An order with no shipment at all counts as fully short (shipped units default to
zero via `COALESCE`), which is correct for an eligible order that never shipped.
If you want to exclude not-yet-shipped orders and measure only *partial* shorts,
add `AND sh.units_shipped IS NOT NULL`.

---

### Metric: Notes on consistency across metrics

A few cross-cutting reminders so numbers reconcile between reports and analysts:

- **Same population, same denominator.** Revenue, order count, and AOV (Sections
  1–2) must use the identical reportable population, or AOV will not equal
  revenue ÷ count. On-time rate and OTIF share the delivered-shipment logic of
  Section 3; keep the promise-present and delivered-status conditions identical.
- **The internal-test exclusion is everywhere.** Every order-touching metric
  above carries `priority_code <> :internal_test_priority`. If you write a new
  metric, that predicate is the first line you add (**Exclusions, Reporting Conventions, and Data Quality**, §1).
- **Name the code set every time.** On-time uses SHIP_STATUS `delivered`; fill
  rate uses ORDER_STATUS `fulfilled`; cycle-count accuracy uses
  CYCLE_COUNT_STATUS; invoices use INVOICE_STATUS; returns use RETURN_STATUS. The
  "done" integer differs per table — never reuse one (the **Lifecycle and Statuses** section, **Exclusions, Reporting Conventions, and Data Quality** §3.4). Bind the
  value from the **Code Dictionary** section.
- **Bridge the identifiers.** Margin and days-of-supply cross from `sku` to
  `item_code`; always join through `products` (the **Identifiers and Keys** section).
- **Aggregate at grain.** Sum line measures over lines and header measures over
  distinct headers; pre-aggregate children before joining to a header to avoid
  fan-out (**Exclusions, Reporting Conventions, and Data Quality** §2.5, the **Query Recipes and Pitfalls** section).
- **Clock is fixed.** All aging/coverage math is relative to
  `TODAY = 2024-12-31`.

When a stakeholder asks for a number that isn't in this catalog, build it from
these primitives, apply the checklist in the **Exclusions, Reporting Conventions, and Data Quality** section, §4, and — if it will be asked
again — add it here so the next analyst gets the same answer.

---

## Pricing, Costs & Billing

This is the cross-domain guide to money. It pulls together every place a dollar
amount is stored — product prices, order economics, payments and refunds, gift
cards as tender, supplier and replenishment costs, product margin, and
supplier/carrier billing — and explains which figure is authoritative for which
purpose. It sits deliberately across the three domains, so it points back into
`order_management.md` (orders and prices), `fulfillment_and_shipping.md`
(returns and carrier billing), and `warehouse_and_inventory.md` (supplier and
replenishment costs).

For canonical metric definitions (revenue, discount, margin as reported to the
business) use the **Metrics and Definitions** section; this document explains the
underlying columns and mechanics so those metrics can be built correctly.

### Where money lives, at a glance

Money in this warehouse sits in three layers that mirror the three domains:

- **Sell-side (Order Management):** the price a product lists for
  (`products.unit_price`, `price_history`), the price paid on each order line
  (`order_lines`), the order total (`orders.order_total`), promotional discounts
  (`order_promotions`), customer payments and refunds (`payments`), and gift
  cards as tender (`gift_cards`, `gift_card_transactions`).
- **Buy-side (Warehouse & Inventory / Supply):** what we pay suppliers
  (`supplier_products.unit_cost`, `replenishment_lines.unit_cost`,
  `replenishment_orders.total_cost`).
- **Payables (billing):** the bills we owe suppliers (`supplier_invoices`) and
  carriers (`carrier_invoices`), both tracked with the INVOICE_STATUS code set.

Margin is the gap between sell-side price and buy-side cost, computed by bridging
the two through `products`. The rest of this document works through each layer.

### Money conventions

- **Currency is USD, two decimals.** All amount columns are SQLite `REAL`. Round
  at presentation with `ROUND(x, 2)`; do not round intermediate sums.
- **TODAY is `2024-12-31`.** Aging and days-outstanding calculations anchor here.
- **Weights are kilograms**, dates are `YYYY-MM-DD`, timestamps are ISO-8601.
- **Coded columns are a two-hop lookup.** A `status_code` or `method_code` points
  at a named code set; the integer-to-label mapping is in
  the **Code Dictionary** section. This document names the code set and uses the label,
  and never prints the code integer beside the label. SQL examples write coded
  filters as named parameters (e.g. `:paid`) with a comment naming the code set
  and label — bind the integer from the **Code Dictionary** section when you run them.
- **`status_code` differs by table.** INVOICE_STATUS decodes both
  `supplier_invoices.status_code` and `carrier_invoices.status_code`, but
  PAYMENT_STATUS decodes `payments.status_code`, and neither decodes the other.
  Never carry a decode across tables (see the **Lifecycle and Statuses** section).
- **Two product-identifier vocabularies.** Order-side money (order lines,
  returns) references products by `sku` (TEXT, `SKU-00042`); cost-side money
  (supplier products, replenishment lines) references the same product by
  `item_code` (INTEGER, = `products.product_id`). Bridge through `products`;
  never join `sku` to `item_code` directly. See the **Identifiers and Keys** section.
- **Exclude internal_test orders** (the internal_test tier of the ORDER_PRIORITY
  code set on `orders.priority_code`) from all revenue and order economics. See
  the **Exclusions, Reporting Conventions, and Data Quality** section.

---

### Product pricing: three prices, three purposes

There are three distinct "prices" for a product, and using the wrong one is a
common source of subtly wrong revenue numbers:

1. **`products.unit_price` — the current list price.** Authoritative for "what
   does this product list for *right now*". One value per product.
2. **`price_history.unit_price` (with `effective_date`) — the historical list
   price.** Authoritative for "what did this product list for on date X". One to
   four effective-dated rows per product.
3. **`order_lines.unit_price` — the price actually charged.** Authoritative for
   "what did the customer *pay* per unit on this order". Captured on the order
   line at order time and never changes afterward.

#### Current vs historical list price

`products.unit_price` is the single current list price. `price_history` is the
effective-dated log. To get the list price effective on a date, take the most
recent effective row on or before that date:

```sql
-- List price effective on :asof for every product
SELECT ph.product_id, ph.unit_price
FROM price_history ph
WHERE ph.effective_date = (
    SELECT MAX(ph2.effective_date)
    FROM price_history ph2
    WHERE ph2.product_id = ph.product_id
      AND ph2.effective_date <= :asof      -- e.g. '2024-06-30'
);
```

Do not assume the newest `price_history` row equals `products.unit_price` — for
the *current* list price always read `products.unit_price` directly. And do not
use either list price as revenue: revenue is built from what the customer paid,
which is captured on the order line.

#### Price paid (order lines)

`order_lines.unit_price` is the price charged per unit on that order, frozen at
order time. It may differ from both the current and the historical list price.
For anything revenue-related, this is the price to use — and in practice you sum
`line_total` (see below) rather than recomputing from `unit_price`.

**Price realization** compares what a product actually sold for against its
current list price — a useful read on discounting pressure. Bridge the order
line's `sku` to `products` for the list price, and weight by units so
higher-volume lines dominate:

```sql
-- Effective selling price vs current list price, by product
SELECT p.sku, p.name, p.unit_price AS list_price,
       ROUND(SUM(ol.line_total) / SUM(ol.quantity), 2) AS effective_unit_price,
       ROUND(100.0 * (SUM(ol.line_total) / SUM(ol.quantity)) / p.unit_price, 1) AS realization_pct
FROM order_lines ol
JOIN orders   o ON o.order_id = ol.order_id
JOIN products p ON p.sku = ol.sku
WHERE o.priority_code <> :internal_test        -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY p.sku, p.name, p.unit_price
ORDER BY realization_pct ASC;                  -- lowest realization = deepest effective discount
```

The effective unit price here is discount-net line revenue divided by units, so
it already reflects line discounts; realization below 100% is the blended effect
of those discounts (and of any historical price differences captured on the
line). This is a *list-vs-paid* comparison and deliberately does not touch
`price_history` — use `price_history` only when the question is explicitly about
the list price on a past date.

---

### Order economics

The order-value stack, from line to header:

| Column | Grain | Meaning |
|---|---|---|
| `order_lines.unit_price` | line | USD charged per unit at order time. |
| `order_lines.quantity` | line | Units on the line. |
| `order_lines.discount_amount` | line | USD line-level discount already applied (0.00 if none). |
| `order_lines.line_total` | line | USD line value = `quantity * unit_price - discount_amount`. |
| `orders.order_total` | header | USD order value = sum of the order's `line_total` values. |
| `order_promotions.discount_amount` | order/promotion | USD order-level promotional discount, tracked separately. |

#### How order_total composes

`orders.order_total` is exactly the **sum of its lines' `line_total`**, and each
`line_total` is already net of the line's `discount_amount`. So `order_total` is
net of *line-level* discounts. It is **not** net of *order-level promotions*: the
`order_promotions.discount_amount` is recorded separately and is **not**
subtracted from `order_total`.

```sql
-- Verify order_total = sum(line_total) for reporting-eligible orders
SELECT o.order_id, o.order_total,
       ROUND(SUM(ol.line_total), 2) AS lines_total
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
WHERE o.priority_code <> :internal_test          -- exclude internal/QA; see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY o.order_id, o.order_total
HAVING ROUND(o.order_total, 2) <> ROUND(SUM(ol.line_total), 2);
```

Prefer summing `line_total` for gross order value, since it already reflects line
discounts. If you need the *gross-before-line-discount* figure, add the line
discount back:

```sql
-- Gross-before-discount vs net-of-line-discount vs net-of-promotions
SELECT o.order_id,
       ROUND(SUM(ol.quantity * ol.unit_price), 2)                 AS gross_before_discount,
       ROUND(SUM(ol.line_total), 2)                               AS net_of_line_discount,   -- = order_total
       COALESCE((SELECT ROUND(SUM(op.discount_amount), 2)
                 FROM order_promotions op WHERE op.order_id = o.order_id), 0) AS promo_discount,
       ROUND(SUM(ol.line_total)
             - COALESCE((SELECT SUM(op.discount_amount)
                         FROM order_promotions op WHERE op.order_id = o.order_id), 0), 2)     AS net_of_promotions
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
WHERE o.priority_code <> :internal_test          -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY o.order_id;
```

#### Order-level promotions

`order_promotions.discount_amount` is the realized USD discount a promotion gave
an order. The promotion catalog (`promotions`, with `promo_type_code` decoding
against the **PROMO_TYPE** code set: percent_off, amount_off, bogo,
free_shipping) characterizes the campaign; the *realized* discount to use in
money math is always `order_promotions.discount_amount`, never a recomputation
from `promotions.value`. An order may carry more than one promotion row, so sum
per order, and most orders carry none, so LEFT JOIN and coalesce to zero. Full
promotion mechanics are in `order_management.md`.

```sql
-- Total realized promotional discount by month (reporting-eligible orders)
SELECT substr(o.order_date, 1, 7) AS ym,
       ROUND(SUM(op.discount_amount), 2) AS promo_discount
FROM order_promotions op
JOIN orders o ON o.order_id = op.order_id
WHERE o.priority_code <> :internal_test          -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY ym
ORDER BY ym;
```

Revenue and discount as *reported to the business* (which discounts net against
revenue, and how) are defined in the **Metrics and Definitions** section; the columns
above are the raw material.

#### Average order value and discount rate

Two derived figures come up constantly. **Average order value (AOV)** is order
value averaged over orders — compute it at the order-header grain so lines do not
inflate the count:

```sql
-- AOV by month (reporting-eligible, non-draft orders)
SELECT substr(order_date, 1, 7) AS ym,
       COUNT(*) AS orders,
       ROUND(AVG(order_total), 2) AS aov
FROM orders
WHERE priority_code <> :internal_test  -- see the Exclusions, Reporting Conventions, and Data Quality section
  AND status <> :draft                  -- ORDER_STATUS 'draft'
GROUP BY ym
ORDER BY ym;
```

**Discount rate** is discount as a fraction of gross. Line-level discount rate
uses `order_lines`; a promotion-inclusive rate adds `order_promotions`. Keep the
grains separate to avoid fan-out — compute line totals at line grain and add
promotions from a per-order subquery:

```sql
-- Line-discount rate over reporting-eligible orders
SELECT ROUND(100.0 * SUM(ol.discount_amount)
             / SUM(ol.quantity * ol.unit_price), 2) AS line_discount_pct
FROM order_lines ol
JOIN orders o ON o.order_id = ol.order_id
WHERE o.priority_code <> :internal_test;       -- see the Exclusions, Reporting Conventions, and Data Quality section
```

The denominator is gross-before-discount (`quantity * unit_price`); the numerator
is the discount. For a promotion-inclusive discount rate, add the summed
`order_promotions.discount_amount` (from a per-order subquery) to the numerator
and keep the same gross denominator. Which discounts the business folds into its
official discount-rate metric is settled in the **Metrics and Definitions — the Canonical Catalog** section.

---

### Payments and refunds

`payments` is the money-movement record for an order (one payment per non-draft
order; the payment `amount` equals the `order_total`).

| Column | Meaning |
|---|---|
| `method_code` | Tender type. Decodes against the **PAYMENT_METHOD** code set. |
| `status_code` | Payment state. Decodes against the **PAYMENT_STATUS** code set. |
| `amount` | USD amount = order total at payment time. |
| `paid_date` | ISO date funds moved; present on captured/refunded rows (and most authorized), NULL for voided/failed. |

`method_code` decodes against **PAYMENT_METHOD** (credit_card, debit_card,
paypal, gift_card, net_terms, wire). `net_terms` and `wire` skew toward business
and government buyers; `gift_card` connects to the gift-card tables below.

`status_code` decodes against **PAYMENT_STATUS** (authorized, captured, refunded,
voided, failed). **captured** is money collected — the state to filter on for
"payments actually received". **refunded** is money returned to the customer and
corresponds to returned orders. **voided** and **failed** never collected funds
and have no `paid_date`.

Because payment `amount` mirrors `order_total`, captured payments are not an
independent revenue stream — they are the same money seen from the tender side.
Use payments when the question is about *tender* or *cash timing*; use orders /
order lines when the question is about *revenue*.

**Cash-collection timing.** `paid_date` is when funds moved; comparing it
to the order date gives days-to-collect, which differs sharply by tender
(card/paypal capture fast, net_terms and wire slower). `paid_date` is populated
once funds have moved — it is present on every captured and refunded row and on
most authorized rows, and is NULL only for voided/failed. To isolate collected
payments, filter on the `captured` status label rather than on `paid_date`
presence:

```sql
-- Average days from order to payment capture, by tender
SELECT p.method_code,                   -- PAYMENT_METHOD; label via the Code Dictionary section
       ROUND(AVG(julianday(p.paid_date) - julianday(o.order_date)), 1) AS avg_days_to_capture
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE p.status_code = :captured         -- PAYMENT_STATUS 'captured'; the Code Dictionary section
  AND p.paid_date IS NOT NULL
  AND o.priority_code <> :internal_test  -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY p.method_code
ORDER BY avg_days_to_capture DESC;
```

```sql
-- Captured vs refunded amount by month (reporting-eligible orders)
SELECT substr(o.order_date, 1, 7) AS ym,
       ROUND(SUM(CASE WHEN p.status_code = :captured THEN p.amount ELSE 0 END), 2) AS captured,
       ROUND(SUM(CASE WHEN p.status_code = :refunded THEN p.amount ELSE 0 END), 2) AS refunded
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE o.priority_code <> :internal_test          -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY ym                                       -- PAYMENT_STATUS labels via the Code Dictionary section
ORDER BY ym;
```

#### Refunds and returns

A refund is the money side of a return. On the money side, a refund shows up as a
payment in the **refunded** state of PAYMENT_STATUS. On the operational side, the
return itself lives in `returns` / `return_lines` (with `returns.status` decoding
against the RETURN_STATUS code set — a *different* set) and is documented in
`fulfillment_and_shipping.md`. To tie a refund to what came back, join the
order's refunded payment to its return:

```sql
-- Refunded orders with the return that drove them
SELECT o.order_id,
       p.amount AS refunded_amount,
       r.rma_number,
       r.status AS return_status          -- RETURN_STATUS; label via the Code Dictionary section
FROM payments p
JOIN orders  o ON o.order_id = p.order_id
JOIN returns r ON r.order_id = o.order_id
WHERE p.status_code = :refunded            -- PAYMENT_STATUS 'refunded'; the Code Dictionary section
  AND o.priority_code <> :internal_test;   -- see the Exclusions, Reporting Conventions, and Data Quality section
```

Keep the two `status` sets straight: `payments.status_code` uses PAYMENT_STATUS,
`returns.status` uses RETURN_STATUS. The "refunded" concept exists in both, with
different underlying integers, and they must not be cross-decoded.

**Refund rate** is refunded value as a share of collected value. Because refund
`amount` and captured `amount` both mirror the order total, you can express it
from the payments ledger over reporting-eligible orders:

```sql
-- Refund rate by month: refunded / captured
SELECT substr(o.order_date, 1, 7) AS ym,
       ROUND(100.0 *
         SUM(CASE WHEN p.status_code = :refunded THEN p.amount ELSE 0 END) /
         NULLIF(SUM(CASE WHEN p.status_code = :captured THEN p.amount ELSE 0 END), 0),
         2) AS refund_pct                -- PAYMENT_STATUS labels via the Code Dictionary section
FROM payments p
JOIN orders o ON o.order_id = p.order_id
WHERE o.priority_code <> :internal_test  -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY ym
ORDER BY ym;
```

Use `NULLIF(..., 0)` on the denominator to avoid divide-by-zero in periods with
no captures. Note that a refunded payment corresponds to a returned order, so the
refund rate here tracks the return-driven refund flow; the operational return
detail (reasons, dispositions, condition of goods) lives in
`fulfillment_and_shipping.md`, and the payment amount is the money figure to
use for financial refund reporting.

---

### Gift cards as tender

Gift cards are both something we sell and a form of payment. The card master and
its balances live in `gift_cards`; the activity ledger is
`gift_card_transactions`. Both are described in full in `order_management.md`;
here is how they fit the money picture.

- `gift_cards.initial_balance` — USD loaded at issue.
- `gift_cards.current_balance` — USD remaining now. The outstanding gift-card
  liability is the sum of remaining balances on all cards that still hold value —
  **active (1)** cards plus **redeemed (2)** cards, which are only partially spent
  and still carry a positive `current_balance`. Restricting to `status_code = active`
  silently omits the live balance still sitting on redeemed (2) cards; expired (3)
  and void (4) cards have a zero balance and so do not contribute either way.
- `gift_card_transactions.amount` with `txn_type_code` (GIFTCARD_TXN_TYPE:
  issue, redeem, reload, refund) — the movement ledger behind the balance.

A gift card being spent down appears as a **redeem** transaction (the card's
balance is reduced; `order_id` is NULL on `gift_card_transactions` in this
dataset, so a redeem is not linked to a specific order), and the card's use as
tender may also appear as a `gift_card` payment in `payments`.
The authoritative record of card value movement is `gift_card_transactions`; the
authoritative current balance is `gift_cards.current_balance`.

```sql
-- Outstanding gift-card liability and lifetime redemptions
SELECT
  (SELECT ROUND(SUM(current_balance), 2) FROM gift_cards
     WHERE current_balance > 0) AS outstanding_liability,    -- live balance on active + partially-spent redeemed cards
  (SELECT ROUND(SUM(amount), 2) FROM gift_card_transactions
     WHERE txn_type_code = :redeem) AS lifetime_redeemed;      -- GIFTCARD_TXN_TYPE 'redeem'
```

Note `gift_cards.customer_id` is nullable, so any "liability by customer" cut
must decide whether to exclude or bucket unowned cards rather than silently
dropping them via an inner join.

Two more distinctions on gift-card money. First, gift-card issuance is a
*liability*, not revenue — selling a $100 card creates a $100 obligation, and
revenue is only recognized as the card is redeemed against orders. So do not add
`issue` transaction amounts to revenue; the revenue is captured on the orders the
card pays for. Second, redeem rows (the card being spent down) may overlap with
the `gift_card` tender on `payments` — both describe the same money from the
ledger side and the payment side, so do not sum both as if they were separate
cash. Note that `gift_card_transactions.order_id` is NULL in this dataset, so
redeems cannot be joined to specific orders directly.

```sql
-- Gift-card value movement by transaction type
SELECT txn_type_code,                  -- GIFTCARD_TXN_TYPE; label via the Code Dictionary section
       COUNT(*) AS txns,
       ROUND(SUM(amount), 2) AS total_amount
FROM gift_card_transactions
GROUP BY txn_type_code
ORDER BY total_amount DESC;
```

---

### Supplier costs and product margin

The cost side of a product uses the `item_code` vocabulary (= `products.product_id`),
not `sku`. Three cost columns matter:

| Column | Grain | Meaning |
|---|---|---|
| `supplier_products.unit_cost` | supplier × product | USD cost to buy one unit from a given supplier. |
| `replenishment_lines.unit_cost` | replenishment line | USD cost per unit on a specific purchase (captured at PO time). |
| `replenishment_orders.total_cost` | replenishment order | USD total of the replenishment order. |

#### supplier_products

`supplier_products` is the catalog of which suppliers can provide which item and
at what cost. It carries `unit_cost`, `lead_time_days`, and `is_preferred`.

- `unit_cost` — the quoted per-unit purchase cost from that supplier.
- `lead_time_days` — the supplier's quoted lead time for that item (distinct from
  the supplier's default lead time on `suppliers.default_lead_time_days`).
- `is_preferred` — 1 for the preferred source of that item, 0 otherwise. A
  product can be offered by more than one supplier; exactly the preferred one is
  flagged. Use `is_preferred = 1` to pick the primary source.

```sql
-- Preferred-supplier cost per product, joined via the item_code bridge
SELECT p.sku, p.name, sp.unit_cost, sp.lead_time_days, s.name AS supplier
FROM supplier_products sp
JOIN products p  ON p.product_id = sp.item_code   -- bridge: item_code = product_id
JOIN suppliers s ON s.supplier_id = sp.supplier_id
WHERE sp.is_preferred = 1
ORDER BY p.sku;
```

Because a product can have up to three supplier rows, the *preferred* source is
not necessarily the *cheapest* one — the preference reflects the sourcing
relationship, and lead time and reliability factor in alongside cost. A "what
could we save by buying the cheapest source" analysis compares the preferred cost
to the minimum available cost per item:

```sql
-- Preferred vs cheapest available unit cost per item
SELECT sp.item_code,
       MAX(CASE WHEN sp.is_preferred = 1 THEN sp.unit_cost END) AS preferred_cost,
       MIN(sp.unit_cost)                                        AS cheapest_cost
FROM supplier_products sp
GROUP BY sp.item_code
HAVING preferred_cost IS NOT NULL
   AND preferred_cost > MIN(sp.unit_cost)
ORDER BY (preferred_cost - MIN(sp.unit_cost)) DESC;
```

This is a cost-side, `item_code`-keyed analysis and needs no `products` bridge
unless you want to show the SKU or name. The supplier's own status
(`suppliers.status_code`, SUPPLIER_STATUS) matters for sourcing decisions — a
cheaper supplier that is on hold or terminated is not actually available — so
join `suppliers` and check status when the question is about *actionable*
sourcing rather than raw catalog cost. See `warehouse_and_inventory.md`.

#### Product margin (price vs cost)

Margin is list (or paid) price minus cost. There is no stored margin column; you
compute it by joining the price side to the cost side through `products`. For a
current, catalog-level gross margin per unit, use `products.unit_price` against
the preferred supplier's `unit_cost`:

```sql
-- Current unit gross margin per product (list price vs preferred cost)
SELECT p.sku, p.name, p.unit_price, sp.unit_cost,
       ROUND(p.unit_price - sp.unit_cost, 2) AS unit_margin,
       ROUND(100.0 * (p.unit_price - sp.unit_cost) / p.unit_price, 1) AS margin_pct
FROM products p
JOIN supplier_products sp
  ON sp.item_code = p.product_id AND sp.is_preferred = 1   -- item_code bridge
ORDER BY margin_pct DESC;
```

For *realized* margin on actual sales, use the price paid on the order line
(`order_lines.unit_price` / `line_total`) against cost, remembering to bridge the
line's `sku` to `products.product_id` before touching any cost table, and to
exclude internal_test orders. The canonical margin metric (which cost basis the
business uses, and how it is reported) is defined in
the **Metrics and Definitions — the Canonical Catalog** section; keep methodology consistent with that catalog.

A realized-margin query has three moving parts: revenue from the order line, cost
from the preferred supplier, and the identifier bridge between them. Because a
product can have several supplier rows, pin the cost to the preferred source (or
you will fan the line out into one row per supplier and multiply the revenue):

```sql
-- Realized gross margin by product (reporting-eligible, fulfilled orders)
SELECT p.sku, p.name,
       SUM(ol.line_total)                         AS revenue,
       ROUND(SUM(ol.quantity * sp.unit_cost), 2)  AS cost,
       ROUND(SUM(ol.line_total) - SUM(ol.quantity * sp.unit_cost), 2) AS gross_margin
FROM order_lines ol
JOIN orders   o  ON o.order_id = ol.order_id
JOIN products p  ON p.sku = ol.sku                 -- SKU side -> products
JOIN supplier_products sp
  ON sp.item_code = p.product_id AND sp.is_preferred = 1   -- product_id = item_code
WHERE o.status = :fulfilled                        -- ORDER_STATUS 'fulfilled'
  AND o.priority_code <> :internal_test            -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY p.sku, p.name
ORDER BY gross_margin DESC;
```

If a product has no preferred supplier row, that inner join drops it; switch to a
LEFT JOIN and decide how to treat missing cost (exclude, or treat cost as unknown)
rather than silently losing the revenue. Cost is a per-unit figure, so it
multiplies by `quantity`, while `line_total` is already the extended,
discount-net line revenue — do not multiply `line_total` by quantity again.

A word of caution on the identifier bridge: every cost table
(`supplier_products`, `replenishment_lines`, `replenishment_orders` via its
lines) is on the `item_code` side, while order revenue is on the `sku` side.
Margin queries therefore *always* pass through `products`. Joining an order
line's `sku` straight to a cost table's `item_code` returns zero rows with no
error. See the **Identifiers and Keys** section and the recipes in
the **Query Recipes and Pitfalls** section.

#### Replenishment costs

`replenishment_orders` are our purchase orders to suppliers (see
`warehouse_and_inventory.md` for the operational detail); `replenishment_lines`
are their line items.

- `replenishment_lines.unit_cost` — USD cost per unit on that purchase line, with
  `qty_ordered` and `qty_received`.
- `replenishment_orders.total_cost` — USD total of the order. It is built from the
  ordered quantity and unit cost of its lines (i.e. it reflects what was ordered,
  which is not necessarily what was received when a line is only partially
  received). Use `qty_received` when you need received-value rather than
  ordered-value.

```sql
-- Ordered value vs received value on a replenishment order
SELECT ro.repl_id, ro.total_cost AS ordered_total,
       ROUND(SUM(rl.qty_received * rl.unit_cost), 2) AS received_value
FROM replenishment_orders ro
JOIN replenishment_lines rl ON rl.repl_id = ro.repl_id
GROUP BY ro.repl_id, ro.total_cost;
```

The `replenishment_orders.status` decodes against the PO_STATUS code set (a
different set again — draft, open, partial, received, cancelled), which tells you
whether `total_cost` represents a committed-but-open PO, a partially received
one, or a fully received purchase. For "what did we actually buy and take in",
filter to the received state and use `qty_received * unit_cost`; for "what is on
order", use the open/partial states. See `warehouse_and_inventory.md` for the
replenishment lifecycle.

#### Supplier spend and cost trends

Purchase spend is the replenishment side of money and is a routine AP/procurement
report. Received-value spend by supplier, over reporting periods, comes from the
replenishment lines (item_code side; no `products` bridge is needed unless you
want product names):

```sql
-- Received purchase spend by supplier and month
SELECT s.name AS supplier,
       substr(ro.received_date, 1, 7) AS ym,
       ROUND(SUM(rl.qty_received * rl.unit_cost), 2) AS received_spend
FROM replenishment_orders ro
JOIN replenishment_lines  rl ON rl.repl_id = ro.repl_id
JOIN suppliers            s  ON s.supplier_id = ro.supplier_id
WHERE ro.status = :received            -- PO_STATUS 'received'; the Code Dictionary section
  AND ro.received_date IS NOT NULL
GROUP BY s.name, ym
ORDER BY s.name, ym;
```

Unit cost is captured per purchase line, so a product's cost can drift across
POs over time. To trend the cost of an item, read `replenishment_lines.unit_cost`
by receipt/order date rather than assuming the single `supplier_products.unit_cost`
is static history — the latter is the current quoted cost, the former is what was
actually paid on each buy:

```sql
-- Cost trend for one item across its purchases (item_code side)
SELECT substr(ro.order_date, 1, 7) AS ym,
       ROUND(AVG(rl.unit_cost), 2)  AS avg_unit_cost,
       SUM(rl.qty_ordered)          AS qty_ordered
FROM replenishment_lines rl
JOIN replenishment_orders ro ON ro.repl_id = rl.repl_id
WHERE rl.item_code = :item_code        -- integer item_code; e.g. 42 for SKU-00042
GROUP BY ym
ORDER BY ym;
```

---

### Billing and accounts payable

Two payables ledgers exist, and they share one code set. `supplier_invoices` are
bills from suppliers (for replenishment purchases); `carrier_invoices` are bills
from carriers (for freight). **Both** `supplier_invoices.status_code` and
`carrier_invoices.status_code` decode against the **INVOICE_STATUS** code set
(draft, submitted, approved, paid, disputed). This is one of the few code sets
shared by two tables — but it is still not shared with any *other* table, and in
particular INVOICE_STATUS has nothing to do with PAYMENT_STATUS on the customer
side.

#### supplier_invoices

| Column | Meaning |
|---|---|
| `supplier_invoice_id` | Primary key. |
| `supplier_id` | Billing supplier. |
| `repl_id` | The replenishment order billed; nullable. |
| `invoice_number` | Unique invoice number. |
| `amount` | USD invoice amount. |
| `status_code` | Invoice state. Decodes against **INVOICE_STATUS**. |
| `invoice_date`, `due_date`, `paid_date` | ISO dates; `paid_date` NULL until paid. |

#### carrier_invoices

| Column | Meaning |
|---|---|
| `carrier_invoice_id` | Primary key. |
| `carrier_id` | Billing carrier. |
| `invoice_number` | Unique invoice number. |
| `amount` | USD invoice amount (freight). |
| `status_code` | Invoice state. Decodes against **INVOICE_STATUS**. |
| `invoice_date`, `due_date`, `paid_date` | ISO dates; `paid_date` NULL until paid. |

#### Invoice aging, DSO-style measures, and disputes

Both ledgers carry `invoice_date`, `due_date`, and `paid_date`, which is enough
for aging and days-to-pay analysis anchored on TODAY (`2024-12-31`).

**Open (unpaid) invoices** are those without a `paid_date` (equivalently, not in
the **paid** state of INVOICE_STATUS). **Overdue** invoices are open invoices past
their `due_date`. **Days payable outstanding**–style figures compare
`invoice_date` (or `due_date`) to `paid_date` for paid invoices, or to TODAY for
open ones.

```sql
-- Supplier AP aging: open invoice amount by age bucket (days since invoice_date)
SELECT CASE
         WHEN julianday('2024-12-31') - julianday(invoice_date) <= 30  THEN '0-30'
         WHEN julianday('2024-12-31') - julianday(invoice_date) <= 60  THEN '31-60'
         WHEN julianday('2024-12-31') - julianday(invoice_date) <= 90  THEN '61-90'
         ELSE '90+'
       END AS age_bucket,
       ROUND(SUM(amount), 2) AS open_amount,
       COUNT(*) AS invoices
FROM supplier_invoices
WHERE paid_date IS NULL                    -- unpaid = open
GROUP BY age_bucket
ORDER BY age_bucket;
```

```sql
-- Average days-to-pay for paid carrier invoices
SELECT ROUND(AVG(julianday(paid_date) - julianday(invoice_date)), 1) AS avg_days_to_pay
FROM carrier_invoices
WHERE status_code = :paid                  -- INVOICE_STATUS 'paid'; the Code Dictionary section
  AND paid_date IS NOT NULL;
```

**Disputed invoices** carry the **disputed** label of INVOICE_STATUS and are a
distinct AP concern — they are neither cleanly open-and-current nor paid. Report
them separately rather than lumping them into standard aging:

```sql
-- Disputed payables across both ledgers
SELECT 'supplier' AS ledger, COUNT(*) AS invoices, ROUND(SUM(amount), 2) AS amount
FROM supplier_invoices WHERE status_code = :disputed        -- INVOICE_STATUS 'disputed'
UNION ALL
SELECT 'carrier',        COUNT(*),           ROUND(SUM(amount), 2)
FROM carrier_invoices  WHERE status_code = :disputed;       -- INVOICE_STATUS 'disputed'
```

Because both ledgers use INVOICE_STATUS, the same `:paid`, `:disputed`, etc.
bindings apply to both — that is the one place a decode legitimately spans two
tables. Everywhere else, respect the per-table code-set rule.

#### AP spend by counterparty

Total payables by supplier or carrier is a straightforward sum of invoice
amounts, optionally split by status. For supplier AP, join to `suppliers` for the
name; the `repl_id` link (nullable) ties an invoice to the purchase it billed
when you need line-level reconciliation:

```sql
-- Supplier payables by status
SELECT s.name AS supplier,
       si.status_code,                 -- INVOICE_STATUS; label via the Code Dictionary section
       COUNT(*) AS invoices,
       ROUND(SUM(si.amount), 2) AS amount
FROM supplier_invoices si
JOIN suppliers s ON s.supplier_id = si.supplier_id
GROUP BY s.name, si.status_code
ORDER BY s.name, amount DESC;
```

Carrier freight billing is the same shape against `carrier_invoices` joined to
`carriers`. Freight is billed at the carrier level (not per shipment), so a
carrier invoice does not join to an individual shipment; to relate freight *cost*
to freight *volume*, aggregate both sides to the carrier and period and compare,
rather than attempting a row-level shipment-to-invoice join:

```sql
-- Carrier freight billed vs shipments handled, by carrier and month
SELECT c.name AS carrier,
       substr(ci.invoice_date, 1, 7) AS ym,
       ROUND(SUM(ci.amount), 2) AS freight_billed
FROM carrier_invoices ci
JOIN carriers c ON c.carrier_id = ci.carrier_id
GROUP BY c.name, ym
ORDER BY c.name, ym;
```

Shipment counts per carrier come from `shipments` (see
`fulfillment_and_shipping.md`); join the two aggregates on carrier + month if
you want an approximate cost-per-shipment, keeping in mind the invoice period and
the ship dates will not align perfectly.

---

### Worked money analyses

Three end-to-end examples that respect the grain, exclusion, and bridge rules.

**A simple gross-margin walk by category.** Revenue from order lines, cost from
the preferred supplier, rolled to the leaf category, over fulfilled
reporting-eligible orders. The line joins to `products` on `sku`; cost joins on
`item_code`; both meet at `products`:

```sql
SELECT cat.name AS category,
       ROUND(SUM(ol.line_total), 2)                       AS revenue,
       ROUND(SUM(ol.quantity * sp.unit_cost), 2)          AS cost,
       ROUND(SUM(ol.line_total) - SUM(ol.quantity * sp.unit_cost), 2) AS gross_margin
FROM order_lines ol
JOIN orders            o   ON o.order_id = ol.order_id
JOIN products          p   ON p.sku = ol.sku
JOIN product_categories cat ON cat.category_id = p.category_id
JOIN supplier_products sp  ON sp.item_code = p.product_id AND sp.is_preferred = 1
WHERE o.status = :fulfilled                    -- ORDER_STATUS 'fulfilled'
  AND o.priority_code <> :internal_test         -- see the Exclusions, Reporting Conventions, and Data Quality section
GROUP BY cat.name
ORDER BY gross_margin DESC;
```

**Open payables and what they will cost us to clear.** Unpaid supplier and
carrier invoices combined, with days-until-due relative to TODAY, so AP can see
the near-term cash requirement:

```sql
SELECT ledger, invoice_number, amount,
       due_date,
       CAST(julianday(due_date) - julianday('2024-12-31') AS INTEGER) AS days_to_due
FROM (
    SELECT 'supplier' AS ledger, invoice_number, amount, due_date
    FROM supplier_invoices WHERE paid_date IS NULL
    UNION ALL
    SELECT 'carrier', invoice_number, amount, due_date
    FROM carrier_invoices WHERE paid_date IS NULL
)
ORDER BY days_to_due;                          -- negative = already overdue
```

**Net revenue after promotions by month.** Order value net of order-level
promotions, aggregating the promotion many-side per order first:

```sql
SELECT substr(o.order_date, 1, 7) AS ym,
       ROUND(SUM(o.order_total), 2)                        AS gross,
       ROUND(SUM(COALESCE(op.promo_discount, 0)), 2)       AS promo_discount,
       ROUND(SUM(o.order_total - COALESCE(op.promo_discount, 0)), 2) AS net_of_promo
FROM orders o
LEFT JOIN (
    SELECT order_id, SUM(discount_amount) AS promo_discount
    FROM order_promotions GROUP BY order_id
) op ON op.order_id = o.order_id
WHERE o.priority_code <> :internal_test         -- see the Exclusions, Reporting Conventions, and Data Quality section
  AND o.status <> :draft                         -- ORDER_STATUS 'draft'
GROUP BY ym
ORDER BY ym;
```

Each of these follows the same discipline: aggregate every one-to-many side to a
single grain before combining, keep the internal_test exclusion on orders, bridge
`sku` ⇄ `item_code` through `products`, and decode each `status`/`status_code`
against its own code set. The **Query Recipes and Pitfalls** section collects these
patterns and the mistakes they prevent.

### Where every amount lives (quick map)

| Amount | Column | Notes |
|---|---|---|
| Current list price | `products.unit_price` | Authoritative "now" price. |
| Historical list price | `price_history.unit_price` (`effective_date`) | Point-in-time list price. |
| Price paid per unit | `order_lines.unit_price` | Captured at order time. |
| Line value | `order_lines.line_total` | `qty*unit_price - discount_amount`. |
| Line discount | `order_lines.discount_amount` | Netted into `line_total`. |
| Order value | `orders.order_total` | Sum of line totals; not net of promotions. |
| Order promo discount | `order_promotions.discount_amount` | Separate; not in `order_total`. |
| Customer payment | `payments.amount` (`status_code`, `paid_date`) | Mirrors order total; tender view. |
| Gift-card balance | `gift_cards.current_balance` / `initial_balance` | Liability = balances on cards still holding value (active + partially-spent redeemed). |
| Gift-card movement | `gift_card_transactions.amount` (`txn_type_code`) | Redeem/issue/reload/refund. |
| Supplier unit cost | `supplier_products.unit_cost` (`is_preferred`) | `item_code` side. |
| Purchase unit cost | `replenishment_lines.unit_cost` | Captured at PO time. |
| Purchase order total | `replenishment_orders.total_cost` | Ordered value. |
| Supplier bill | `supplier_invoices.amount` (`status_code`) | INVOICE_STATUS; AP. |
| Carrier (freight) bill | `carrier_invoices.amount` (`status_code`) | INVOICE_STATUS; AP. |

### A note on REAL and rounding

Every amount is a SQLite `REAL` (double-precision float), so long sums can carry
tiny floating-point residue. Round only at presentation (`ROUND(x, 2)`); rounding
mid-calculation and then summing compounds error. When you reconcile two figures
that *should* match (for example `orders.order_total` against
`SUM(order_lines.line_total)`, or `replenishment_orders.total_cost` against its
lines), compare on the rounded values, or allow a sub-cent tolerance
(`ABS(a - b) < 0.01`), rather than testing exact float equality — an exact `=`
can spuriously report a mismatch that is only float noise.

### Invoice-to-purchase reconciliation

A supplier invoice can be tied to the replenishment order it billed through the
nullable `supplier_invoices.repl_id`. That lets you check invoiced amount against
the purchase's own `total_cost`:

```sql
-- Supplier invoices vs the replenishment total they billed
SELECT si.invoice_number, si.amount AS invoiced,
       ro.total_cost      AS po_total,
       ROUND(si.amount - ro.total_cost, 2) AS variance
FROM supplier_invoices si
JOIN replenishment_orders ro ON ro.repl_id = si.repl_id
WHERE si.repl_id IS NOT NULL
ORDER BY ABS(si.amount - ro.total_cost) DESC;
```

Invoices with `repl_id IS NULL` are not tied to a specific purchase and cannot be
reconciled this way; treat them as standalone payables. As always, the
`status_code` on both sides here is INVOICE_STATUS on the invoice and PO_STATUS on
the replenishment order — different code sets, not interchangeable.

### Recurring reminders for money queries

1. **Pick the right price.** Current list = `products.unit_price`; historical
   list = `price_history`; price paid = `order_lines.unit_price`. Revenue is
   built from price paid (sum `line_total`), not list price.
2. **`order_total` is net of line discounts, not of promotions.** Subtract
   `order_promotions.discount_amount` explicitly for a promotion-net figure.
3. **Exclude internal_test orders** from all revenue/economics with
   `priority_code <> :internal_test`. See the **Exclusions, Reporting Conventions, and Data Quality** section.
4. **Bridge cost to revenue through `products`.** Cost tables use `item_code`;
   order/return tables use `sku`. A direct `sku`-to-`item_code` join is silently
   empty. See the **Identifiers and Keys** section.
5. **INVOICE_STATUS is shared by the two invoice tables and by nothing else**;
   PAYMENT_STATUS, RETURN_STATUS, and GIFTCARD_STATUS are all distinct sets. Do
   not cross-decode. See the **Code Dictionary** section and
   the **Lifecycle and Statuses** section.
6. **Round at the end**, keep amounts as `REAL`, and anchor aging on TODAY
   (`2024-12-31`).

For the reported metric definitions built on these columns — revenue, gross
margin, discount rate, and the like — see the **Metrics and Definitions — the Canonical Catalog** section. For
the order-side detail behind prices and promotions, see
`order_management.md`. For returns and carrier operations behind refunds and
freight billing, see `fulfillment_and_shipping.md`; for suppliers and
replenishment behind purchase costs, see `warehouse_and_inventory.md`.

---

## Query Recipes and Pitfalls

A cookbook of worked, correct SQLite queries for the questions analysts ask most
often, followed by a common-mistakes section. Every recipe here runs against the
warehouse schema as defined in the DDL. Today's reporting date is
**2024-12-31**; money is USD to two decimals; weights are kilograms; dates are
`YYYY-MM-DD` and timestamps are ISO-8601.

### Conventions used in every recipe

- **Coded filters use named bind parameters, never literal integers.** A coded
  column (`status`, `priority_code`, `reason_code`, and so on) means a different
  set of integers on each table, and the integer behind each label lives only in
  the **Code Dictionary** section. So a recipe that filters on "cancelled orders" is
  written `WHERE o.status = :order_status_cancelled` with a comment naming the
  code set (here ORDER_STATUS). Bind the value from the **Code Dictionary** section
  before running. This keeps the recipes correct even if you are looking at a
  table whose "cancelled-like" label sits at a different integer.
- **Which code set applies to which column** is in the **Code Dictionary** section.
  The recipe comments name the set so you do not have to guess.
- **Reporting exclusions** (internal test orders, cancelled orders, and so on)
  come from the **Exclusions, Reporting Conventions, and Data Quality** section. They are applied in the recipes
  below and called out each time.
- **The product identifier split** — order-side `sku` (TEXT) versus
  inventory-side `item_code` (INTEGER), bridged only through `products` — is
  documented fully in the **Identifiers and Keys** section. It appears constantly here.
- **Metric definitions** (revenue, on-time, availability, return rate) are in
  the **Metrics and Definitions — the Canonical Catalog** section; the recipes implement those definitions.

---

### Recipe: Recognized revenue by month

Revenue is summed from `order_lines.line_total` (the amount actually charged per
line), and it **excludes internal-test orders and cancelled orders** per
the **Exclusions, Reporting Conventions, and Data Quality** section. Group by the order month.

```sql
SELECT strftime('%Y-%m', o.order_date)      AS order_month,
       ROUND(SUM(ol.line_total), 2)         AS revenue_usd,
       COUNT(DISTINCT o.order_id)           AS order_count
FROM orders o
JOIN order_lines ol ON ol.order_id = o.order_id
WHERE o.priority_code <> :order_priority_internal_test  -- ORDER_PRIORITY; see the Exclusions, Reporting Conventions, and Data Quality section & the Code Dictionary section
  AND o.status        <> :order_status_cancelled        -- ORDER_STATUS; see the Code Dictionary section
GROUP BY order_month
ORDER BY order_month;
```

If you would rather report on the order header total, sum `o.order_total` with
`COUNT`ing one row per order (do not join to `order_lines`, which would multiply
the header total by the number of lines). Line-level `SUM(line_total)` is the
recommended revenue figure — see the **Metrics and Definitions — the Canonical Catalog** section.

---

### Recipe: On-time vs late delivery rate

A shipment is **delivered late** when it reached the delivered state and its
`delivered_date` is strictly after its `promised_date`; it is **on time** when
delivered on or before the promised date. Shipments not yet delivered, or with a
NULL `promised_date`, are excluded from the rate because they are not gradeable.

```sql
SELECT COUNT(*)                                               AS delivered_shipments,
       SUM(CASE WHEN s.delivered_date > s.promised_date
                THEN 1 ELSE 0 END)                            AS late_shipments,
       ROUND(100.0 * SUM(CASE WHEN s.delivered_date > s.promised_date
                              THEN 1 ELSE 0 END) / COUNT(*), 2) AS late_pct
FROM shipments s
WHERE s.status = :ship_status_delivered   -- SHIP_STATUS; see the Code Dictionary section
  AND s.delivered_date IS NOT NULL
  AND s.promised_date  IS NOT NULL;
```

Dates are `YYYY-MM-DD` strings, so a plain string comparison (`>`) orders them
correctly; no `julianday` is needed just to compare two dates. Use `julianday`
only when you need the number of days between them (see the *Days late for late shipments* recipe).

---

### Recipe: On-time rate by carrier

The same rate, broken out by carrier, with the carrier name attached.

```sql
SELECT c.name                                                 AS carrier,
       COUNT(*)                                               AS delivered,
       SUM(CASE WHEN s.delivered_date <= s.promised_date
                THEN 1 ELSE 0 END)                            AS on_time,
       ROUND(100.0 * SUM(CASE WHEN s.delivered_date <= s.promised_date
                              THEN 1 ELSE 0 END) / COUNT(*), 2) AS on_time_pct
FROM shipments s
JOIN carriers c ON c.carrier_id = s.carrier_id
WHERE s.status = :ship_status_delivered   -- SHIP_STATUS; see the Code Dictionary section
  AND s.delivered_date IS NOT NULL
  AND s.promised_date  IS NOT NULL
GROUP BY c.carrier_id, c.name
ORDER BY on_time_pct DESC;
```

---

### Recipe: Items currently below reorder point

An item at a warehouse is **below reorder point** when
`quantity_on_hand < reorder_point` (see the **Metrics and Definitions — the Canonical Catalog** section). Because
`inventory` speaks `item_code`, bridge to `products` to show the SKU and name.

```sql
SELECT w.code                                       AS warehouse_code,
       p.sku,
       p.name                                       AS product,
       inv.quantity_on_hand,
       inv.reorder_point,
       inv.reorder_qty,
       (inv.reorder_point - inv.quantity_on_hand)   AS shortfall
FROM inventory inv
JOIN products   p ON p.product_id  = inv.item_code   -- INTEGER bridge, not sku
JOIN warehouses w ON w.warehouse_id = inv.warehouse_id
WHERE inv.quantity_on_hand < inv.reorder_point
ORDER BY shortfall DESC;
```

The `p.product_id = inv.item_code` join is the correct product link. Writing
`p.sku = inv.item_code` would compare TEXT to INTEGER and return nothing — see
the common-mistakes section.

---

### Recipe: Inventory available (on-hand minus allocated) by warehouse

**Available** stock is `quantity_on_hand - quantity_allocated`. Summed per
warehouse:

```sql
SELECT w.code                                                  AS warehouse_code,
       w.name                                                  AS warehouse,
       SUM(inv.quantity_on_hand)                               AS on_hand,
       SUM(inv.quantity_allocated)                             AS allocated,
       SUM(inv.quantity_on_hand - inv.quantity_allocated)      AS available
FROM inventory inv
JOIN warehouses w ON w.warehouse_id = inv.warehouse_id
GROUP BY w.warehouse_id, w.code, w.name
ORDER BY available DESC;
```

For availability of a single product across warehouses, add
`WHERE inv.item_code = :item_code` (an integer, for example 42) or join through
`products` and filter on `p.sku = 'SKU-00042'`.

---

### Recipe: Open replenishment POs and expected receipts

Open purchase orders are those in an in-flight PO_STATUS state (not received,
not cancelled). List them with supplier, destination warehouse, and expected
date, flagging any already past due as of today.

```sql
SELECT ro.repl_id,
       sup.name                       AS supplier,
       w.code                         AS warehouse,
       ro.order_date,
       ro.expected_date,
       ro.total_cost,
       CASE WHEN ro.expected_date < '2024-12-31'
            THEN 'past_due' ELSE 'upcoming' END AS timing
FROM replenishment_orders ro
JOIN suppliers  sup ON sup.supplier_id = ro.supplier_id
JOIN warehouses w   ON w.warehouse_id  = ro.warehouse_id
WHERE ro.status IN (:po_status_open, :po_status_partial)  -- PO_STATUS; see the Code Dictionary section
  AND ro.received_date IS NULL
ORDER BY ro.expected_date;
```

To see expected quantities per item on those POs, join `replenishment_lines` and
bridge `item_code` to `products` for the SKU and name:

```sql
SELECT ro.repl_id,
       p.sku,
       p.name,
       rl.qty_ordered,
       rl.qty_received,
       (rl.qty_ordered - rl.qty_received) AS qty_outstanding
FROM replenishment_orders ro
JOIN replenishment_lines rl ON rl.repl_id   = ro.repl_id
JOIN products            p  ON p.product_id = rl.item_code
WHERE ro.status IN (:po_status_open, :po_status_partial)  -- PO_STATUS; see the Code Dictionary section
ORDER BY ro.repl_id, p.sku;
```

---

### Recipe: Return rate by reason

Return rate here is the count of returns per reason as a share of all returns.
`reason_code` decodes via RETURN_REASON. To label the reasons in the output you
would join a decode; since there is no decode table, group by the code and read
the labels from the **Code Dictionary** section.

```sql
SELECT r.reason_code,                              -- RETURN_REASON; label via the Code Dictionary section
       COUNT(*)                                    AS return_count,
       ROUND(100.0 * COUNT(*) /
             (SELECT COUNT(*) FROM returns), 2)    AS pct_of_returns
FROM returns r
GROUP BY r.reason_code
ORDER BY return_count DESC;
```

For a return rate against orders — returns divided by shipped/fulfilled orders —
see the *Return rate against fulfilled orders* recipe, and remember to exclude
internal-test orders from the denominator.

---

### Recipe: Top products by units shipped

Units shipped live on `shipment_items.quantity`, keyed by `sku`. Join through
`products` to attach the name (a plain `sku`-to-`sku` join here, because both
sides are order-side text). Exclude internal-test orders by walking back to the
order via the shipment.

```sql
SELECT p.sku,
       p.name                       AS product,
       SUM(si.quantity)             AS units_shipped
FROM shipment_items si
JOIN shipments s ON s.shipment_id = si.shipment_id
JOIN orders    o ON o.order_id    = s.order_id
JOIN products  p ON p.sku         = si.sku
WHERE o.priority_code <> :order_priority_internal_test  -- ORDER_PRIORITY; see the Exclusions, Reporting Conventions, and Data Quality section & the Code Dictionary section
GROUP BY p.product_id, p.sku, p.name
ORDER BY units_shipped DESC
LIMIT 20;
```

`shipment_items.sku` is text, so it joins to `products.sku` directly; no
conversion is needed on this side of the model.

---

### Recipe: Exception rate by carrier

Share of a carrier's shipments that had at least one delivery exception. Count
shipments once (a shipment can have several exceptions), so use
`EXISTS` rather than a join that would fan out.

```sql
SELECT c.name                                                   AS carrier,
       COUNT(*)                                                 AS shipments,
       SUM(CASE WHEN EXISTS (SELECT 1 FROM delivery_exceptions de
                             WHERE de.shipment_id = s.shipment_id)
                THEN 1 ELSE 0 END)                              AS with_exception,
       ROUND(100.0 * SUM(CASE WHEN EXISTS (SELECT 1 FROM delivery_exceptions de
                                           WHERE de.shipment_id = s.shipment_id)
                              THEN 1 ELSE 0 END) / COUNT(*), 2) AS exception_pct
FROM shipments s
JOIN carriers c ON c.carrier_id = s.carrier_id
GROUP BY c.carrier_id, c.name
ORDER BY exception_pct DESC;
```

---

### Recipe: Open delivery exceptions aging report

Open exceptions have a NULL `resolved_ts`. Age them against today using
`julianday` on the timestamps.

```sql
SELECT de.exception_id,
       s.shipment_id,
       de.exception_type_code,                              -- EXCEPTION_TYPE; label via the Code Dictionary section
       de.reported_ts,
       CAST(julianday('2024-12-31') - julianday(de.reported_ts) AS INTEGER) AS days_open
FROM delivery_exceptions de
JOIN shipments s ON s.shipment_id = de.shipment_id
WHERE de.resolved_ts IS NULL
ORDER BY days_open DESC;
```

---

### Recipe: Average delivery transit time by service level

Days from ship to delivery, only for delivered shipments with both dates present,
grouped by the carrier service level.

```sql
SELECT cs.service_level_code,                              -- SERVICE_LEVEL; label via the Code Dictionary section
       COUNT(*)                                            AS delivered,
       ROUND(AVG(julianday(s.delivered_date)
                 - julianday(s.ship_date)), 2)             AS avg_transit_days
FROM shipments s
JOIN carrier_services cs ON cs.service_id = s.service_id
WHERE s.status = :ship_status_delivered   -- SHIP_STATUS; see the Code Dictionary section
  AND s.delivered_date IS NOT NULL
GROUP BY cs.service_level_code
ORDER BY avg_transit_days;
```

---

### Recipe: Days late for late shipments

For shipments delivered after their promise, how many days late, worst first.

```sql
SELECT s.shipment_id,
       s.tracking_number,
       s.promised_date,
       s.delivered_date,
       CAST(julianday(s.delivered_date) - julianday(s.promised_date) AS INTEGER) AS days_late
FROM shipments s
WHERE s.status = :ship_status_delivered   -- SHIP_STATUS; see the Code Dictionary section
  AND s.delivered_date IS NOT NULL
  AND s.promised_date  IS NOT NULL
  AND s.delivered_date > s.promised_date
ORDER BY days_late DESC;
```

---

### Recipe: Cycle-count accuracy by warehouse

Cycle counts store `variance = counted_qty - system_qty`. Accuracy is the share
of reconciled counts with zero variance. `status_code` decodes via
CYCLE_COUNT_STATUS.

```sql
SELECT w.code                                                  AS warehouse_code,
       COUNT(*)                                                AS counts,
       SUM(CASE WHEN cc.variance = 0 THEN 1 ELSE 0 END)        AS exact,
       ROUND(100.0 * SUM(CASE WHEN cc.variance = 0 THEN 1 ELSE 0 END)
                     / COUNT(*), 2)                            AS accuracy_pct
FROM cycle_counts cc
JOIN warehouses w ON w.warehouse_id = cc.warehouse_id
WHERE cc.status_code = :cycle_count_status_reconciled  -- CYCLE_COUNT_STATUS; see the Code Dictionary section
GROUP BY w.warehouse_id, w.code
ORDER BY accuracy_pct;
```

---

### Recipe: Inventory movement ledger for one product

`inventory_transactions` is the signed movement ledger. Net change and current
posture for one product across warehouses. `txn_type_code` decodes via
INV_TXN_TYPE.

```sql
SELECT w.code                         AS warehouse_code,
       it.txn_type_code,              -- INV_TXN_TYPE; label via the Code Dictionary section
       SUM(it.quantity_delta)         AS net_delta,
       COUNT(*)                       AS txn_count
FROM inventory_transactions it
JOIN warehouses w ON w.warehouse_id = it.warehouse_id
WHERE it.item_code = 42               -- SKU-00042
GROUP BY w.warehouse_id, w.code, it.txn_type_code
ORDER BY w.code, it.txn_type_code;
```

To start from a SKU instead of an item code, convert:
`WHERE it.item_code = CAST(SUBSTR('SKU-00042', 5) AS INTEGER)`.

---

### Recipe: Return rate against fulfilled orders

Returns as a share of fulfilled orders, excluding internal-test orders from the
denominator. Count distinct orders that generated at least one return.

```sql
WITH reportable_orders AS (
    SELECT o.order_id
    FROM orders o
    WHERE o.priority_code <> :order_priority_internal_test  -- ORDER_PRIORITY; see the Exclusions, Reporting Conventions, and Data Quality section & the Code Dictionary section
      AND o.status        =  :order_status_fulfilled        -- ORDER_STATUS; see the Code Dictionary section
)
SELECT (SELECT COUNT(*) FROM reportable_orders)              AS fulfilled_orders,
       COUNT(DISTINCT r.order_id)                            AS orders_with_returns,
       ROUND(100.0 * COUNT(DISTINCT r.order_id)
             / (SELECT COUNT(*) FROM reportable_orders), 2)  AS return_rate_pct
FROM returns r
JOIN reportable_orders ro ON ro.order_id = r.order_id;
```

---

### Recipe: Revenue by customer segment

Line revenue rolled up by the ordering customer's segment. `segment_code`
decodes via CUSTOMER_SEGMENT. Internal-test and cancelled orders excluded.

```sql
SELECT cu.segment_code,                                -- CUSTOMER_SEGMENT; label via the Code Dictionary section
       ROUND(SUM(ol.line_total), 2)                    AS revenue_usd,
       COUNT(DISTINCT o.order_id)                       AS orders
FROM orders o
JOIN customers   cu ON cu.customer_id = o.customer_id
JOIN order_lines ol ON ol.order_id    = o.order_id
WHERE o.priority_code <> :order_priority_internal_test  -- ORDER_PRIORITY; see the Exclusions, Reporting Conventions, and Data Quality section & the Code Dictionary section
  AND o.status        <> :order_status_cancelled        -- ORDER_STATUS; see the Code Dictionary section
GROUP BY cu.segment_code
ORDER BY revenue_usd DESC;
```

---

### Recipe: Supplier fill rate on received POs

For received POs, how much of what was ordered actually arrived, by supplier.
Aggregate the lines first so multiple lines per PO do not distort the header.

```sql
SELECT sup.name                                             AS supplier,
       SUM(rl.qty_ordered)                                  AS qty_ordered,
       SUM(rl.qty_received)                                 AS qty_received,
       ROUND(100.0 * SUM(rl.qty_received)
             / NULLIF(SUM(rl.qty_ordered), 0), 2)           AS fill_rate_pct
FROM replenishment_orders ro
JOIN suppliers           sup ON sup.supplier_id = ro.supplier_id
JOIN replenishment_lines rl  ON rl.repl_id      = ro.repl_id
WHERE ro.status = :po_status_received   -- PO_STATUS; see the Code Dictionary section
GROUP BY sup.supplier_id, sup.name
ORDER BY fill_rate_pct;
```

`NULLIF(..., 0)` guards against a divide-by-zero if a supplier's ordered total is
zero.

---

### Recipe: Products that are below reorder point AND have a preferred supplier

Combines inventory shortfall (item_code side) with the supplier catalog
(also item_code side), bridged through `products` for readable output.

```sql
SELECT w.code                          AS warehouse_code,
       p.sku,
       p.name                          AS product,
       inv.quantity_on_hand,
       inv.reorder_point,
       sup.name                        AS preferred_supplier,
       sp.lead_time_days
FROM inventory inv
JOIN products         p   ON p.product_id  = inv.item_code
JOIN warehouses       w   ON w.warehouse_id = inv.warehouse_id
JOIN supplier_products sp ON sp.item_code   = inv.item_code
                         AND sp.is_preferred = 1
JOIN suppliers        sup ON sup.supplier_id = sp.supplier_id
WHERE inv.quantity_on_hand < inv.reorder_point
ORDER BY (inv.reorder_point - inv.quantity_on_hand) DESC;
```

Both `inventory` and `supplier_products` use `item_code`, so they join directly
on `item_code`; `products` bridges only for the display SKU and name.

---

### Recipe: Order-to-ship cycle time

Days from order date to first ship date, for reportable orders that shipped. Use
the earliest ship date per order (an order can have more than one shipment).

```sql
SELECT o.order_id,
       o.order_date,
       MIN(s.ship_date)                                                AS first_ship_date,
       CAST(julianday(MIN(s.ship_date)) - julianday(o.order_date)
            AS INTEGER)                                                AS days_to_ship
FROM orders o
JOIN shipments s ON s.order_id = o.order_id
WHERE o.priority_code <> :order_priority_internal_test  -- ORDER_PRIORITY; see the Exclusions, Reporting Conventions, and Data Quality section & the Code Dictionary section
GROUP BY o.order_id, o.order_date
ORDER BY days_to_ship DESC;
```

---

### Recipe: Multi-leg shipments and their facility path

Shipments with more than one leg, listing the ordered leg path. `mode_code`
decodes via TRANSPORT_MODE; leg `status` via LEG_STATUS.

```sql
SELECT s.shipment_id,
       lg.leg_seq,
       ff.code AS from_facility,
       tf.code AS to_facility,
       lg.mode_code,                    -- TRANSPORT_MODE; label via the Code Dictionary section
       lg.status                        -- LEG_STATUS; label via the Code Dictionary section
FROM shipments s
JOIN shipment_legs lg ON lg.shipment_id     = s.shipment_id
JOIN facilities    ff ON ff.facility_id     = lg.from_facility_id
JOIN facilities    tf ON tf.facility_id     = lg.to_facility_id
WHERE s.shipment_id IN (
        SELECT shipment_id FROM shipment_legs
        GROUP BY shipment_id HAVING COUNT(*) > 1)
ORDER BY s.shipment_id, lg.leg_seq;
```

---

### Recipe: Carrier invoice payment status summary

Outstanding versus paid carrier spend. `status_code` decodes via INVOICE_STATUS.

```sql
SELECT c.name                                          AS carrier,
       ci.status_code,                                 -- INVOICE_STATUS; label via the Code Dictionary section
       COUNT(*)                                         AS invoices,
       ROUND(SUM(ci.amount), 2)                         AS total_amount
FROM carrier_invoices ci
JOIN carriers c ON c.carrier_id = ci.carrier_id
GROUP BY c.carrier_id, c.name, ci.status_code
ORDER BY c.name, ci.status_code;
```

---

### Recipe: Stock transfers in transit between warehouses

Transfers that have shipped but not yet been received. `status_code` decodes via
TRANSFER_STATUS.

```sql
SELECT st.transfer_id,
       fw.code AS from_warehouse,
       tw.code AS to_warehouse,
       st.shipped_date,
       SUM(stl.qty_shipped) AS units_in_transit
FROM stock_transfers st
JOIN warehouses fw ON fw.warehouse_id = st.from_warehouse_id
JOIN warehouses tw ON tw.warehouse_id = st.to_warehouse_id
JOIN stock_transfer_lines stl ON stl.transfer_id = st.transfer_id
WHERE st.status_code   = :transfer_status_in_transit  -- TRANSFER_STATUS; see the Code Dictionary section
  AND st.received_date IS NULL
GROUP BY st.transfer_id, fw.code, tw.code, st.shipped_date
ORDER BY units_in_transit DESC;
```

---

### Recipe: Products never shipped (in the reportable order stream)

A left-anti pattern: active products with no shipped units in reportable orders.

```sql
SELECT p.sku, p.name
FROM products p
WHERE p.is_active = 1
  AND NOT EXISTS (
        SELECT 1
        FROM shipment_items si
        JOIN shipments s ON s.shipment_id = si.shipment_id
        JOIN orders    o ON o.order_id    = s.order_id
        WHERE si.sku = p.sku
          AND o.priority_code <> :order_priority_internal_test  -- ORDER_PRIORITY; see the Exclusions, Reporting Conventions, and Data Quality section & the Code Dictionary section
  )
ORDER BY p.sku;
```

---

### Recipe: Inventory on hand valued at latest supplier cost

Value on-hand stock using the preferred supplier's `unit_cost`. Since a product
may have more than one supplier row, restrict to the preferred one.

```sql
SELECT w.code                                          AS warehouse_code,
       SUM(inv.quantity_on_hand * sp.unit_cost)        AS on_hand_value_usd
FROM inventory inv
JOIN warehouses w ON w.warehouse_id = inv.warehouse_id
JOIN supplier_products sp ON sp.item_code    = inv.item_code
                         AND sp.is_preferred = 1
GROUP BY w.warehouse_id, w.code
ORDER BY on_hand_value_usd DESC;
```

If a product has no preferred supplier row it drops out of this valuation; use a
`LEFT JOIN` and `COALESCE` if you need those items represented at zero cost. For
authoritative costing rules see the **Pricing, Costs & Billing** section.

---

### Common mistakes

These are the errors that most often produce a query that runs cleanly but
answers the wrong question.

#### Comparing `sku` to `item_code` and silently getting zero rows

The order side uses `sku` (TEXT, `SKU-00042`) and the inventory side uses
`item_code` (INTEGER, `42`). Writing `ON order_lines.sku = inventory.item_code`
compares a text value to an integer, which is never equal, so the join returns
**zero rows with no error**. The result looks like "no inventory exists" when the
join was simply meaningless. Always bridge through `products`
(`products.sku = ...sku` and `products.product_id = ...item_code`) or convert
explicitly with `CAST(SUBSTR(sku,5) AS INTEGER)` / `'SKU-' || printf('%05d',
item_code)`. Full treatment in the **Identifiers and Keys** section.

#### Forgetting to exclude internal-test orders

Orders at the `internal_test` value of ORDER_PRIORITY are internal orders and
must be excluded from all reporting (revenue, counts, rates). They look like
ordinary orders — real customers, normal amounts, real shipments — so nothing in
the data flags them; the rule lives only in guidance
(the **Exclusions, Reporting Conventions, and Data Quality** section). Every revenue, order-count, and rate query
should carry `WHERE priority_code <> :order_priority_internal_test`. When they
sit in a denominator (return rate, fill rate), exclude them there too.

#### Reusing a status decode from one table on another

`status` and `status_code` are the same column *name* on many tables, but each
table uses its **own code set**, and the terminal "done" value differs from
table to table (order fulfilled, shipment delivered, PO received, leg completed,
transfer received, pick completed are all different integers in different sets).
Decoding a shipment's status with the order code set, or hardcoding one table's
"done" integer against another, yields plausible-but-wrong filters. Look up the
right code set for each column in the **Code Dictionary** section, and take the
value from the **Code Dictionary** section. This is exactly why the recipes bind coded
values by name and comment which set applies.

#### Double-counting when fanning lines out to shipments, items, or legs

Order-to-shipment relationships are one-to-many at several levels: an order has
many order lines; an order line can appear in several `shipment_items`; a
shipment has many packages, legs, tracking events, and possibly exceptions.
Joining an order to any of these and then summing an order-level or line-level
amount multiplies it by the number of child rows. Symptoms are revenue or unit
totals that are too high by a small integer factor. Fixes: aggregate the child
to the grain you want *before* joining (a subquery or CTE that sums per order),
use `COUNT(DISTINCT order_id)` for order counts, and use `EXISTS` rather than a
join when you only need "has at least one" (as in the exception-rate recipe).
Never join two independent one-to-many children (say `packages` and
`shipment_legs`) to the same shipment and then aggregate — that produces a
cross-product.

#### Mishandling NULL delivered / promised / received dates

Many lifecycle dates are NULL until the event happens: `delivered_date`,
`promised_date`, `orders.promised_date`, `returns.received_date`,
`replenishment_orders.received_date`, `shipment_legs.arrived_ts`,
`delivery_exceptions.resolved_ts`, `pick_tasks.completed_ts`, invoice
`paid_date`. Two consequences: (1) a comparison like `delivered_date >
promised_date` is neither true nor false when either side is NULL — the row is
excluded from a `WHERE`, which is usually right for a delivered-late filter but
means you must not treat "not late" and "NULL" as the same thing; and (2)
counting on-time versus late must restrict to rows where both dates are present,
or your denominator silently drops undelivered shipments in one place and keeps
them in another. State the NULL handling explicitly (`IS NOT NULL` guards, or
`COALESCE` with a documented default) rather than relying on accident.

#### Date arithmetic in SQLite

Dates are ISO strings, so `>`/`<`/`BETWEEN` compare them correctly *as strings*
for equality and ordering — you do **not** need `julianday` just to ask "was it
delivered after the promise." Use `julianday(a) - julianday(b)` when you need the
**number of days between** two dates or timestamps (transit time, aging, cycle
time); it returns a float, so wrap in `CAST(... AS INTEGER)` or `ROUND(...)` for
whole days. `strftime('%Y-%m', order_date)` is the idiom for monthly buckets.
Do not use SQL-dialect functions like `DATEDIFF` or `DATE_TRUNC`; they are not
SQLite. Beware mixing a date (`YYYY-MM-DD`) with a timestamp
(`YYYY-MM-DDTHH:MM:SS`) in a raw string comparison — normalize with
`date(ts)` or `substr(ts,1,10)` first.

#### Joining facilities to warehouses

`facilities` (transit nodes) and `warehouses` (inventory buildings) are separate
identifier spaces with no shared id and no foreign key between them. A
`facility_id` is not a `warehouse_id`. Connect the two only through a shipment:
its `origin_warehouse_id` gives the warehouse, its legs give the facility path.
See the **Identifiers and Keys** section.

#### Summing header totals across joined lines

`orders.order_total` is a header value. If you join `order_lines` (or shipments,
or payments) and then `SUM(order_total)`, you multiply the header by the number
of joined rows. Either sum line-level `line_total` (the recommended revenue
figure), or aggregate to one row per order before summing the header. The same
caution applies to `replenishment_orders.total_cost` against its lines.

For anything about which code set a column uses, see
the **Code Dictionary** section; for the values in each set, see
the **Code Dictionary** section; for exclusion rules, see
the **Exclusions, Reporting Conventions, and Data Quality** section; and for metric definitions, see
the **Metrics and Definitions — the Canonical Catalog** section.

---

