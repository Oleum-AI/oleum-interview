# Meridian Retail — Data Guide

Reference for the Meridian Retail operational dataset: a small chain of
general-merchandise stores. This document describes what each table means, what every
column holds, how the tables relate, the rules the data is guaranteed to obey, and the
questions it can answer. It is the authoritative dictionary for anyone writing queries
against the database.

The data lives in a single SQLite database (`data.db`). It covers store operations,
purchasing, inventory, and sales.

---

## Domain overview

Products are purchased from **suppliers** via **purchase orders**, and the goods are
received into **warehouses**. Each product belongs to one **category** and one
supplier. Products are stocked at each **store**, and the **inventory** table records
the current on-hand quantity per store per product. Stores are staffed by
**employees**. Customers buy products in **sales orders**, whose line items are in
**sales_order_items** and which are rung up by an employee at a store. Loyalty
**customers** are tracked; walk-in sales are recorded without a customer.

---

## Field notes

A handful of columns follow internal naming and encoding conventions that are worth
calling out explicitly, since they drive most aggregate queries.

### Abbreviated column names

| Column | Table | Meaning |
|--------|-------|---------|
| `wac` | `products` | Weighted average cost — the unit cost of the product (what we pay the supplier per unit). |
| `unit_cost` | `purchase_order_items` | Cost paid per unit on that specific purchase-order line (close to, but distinct from, the product's `wac`). |
| `gla` | `stores` | Gross leasable area — the store's sellable floor space, in square feet. |
| `cap` | `warehouses` | Storage capacity — the maximum number of units the distribution center can hold. |
| `rop` | `inventory` | Reorder point — replenishment is triggered when `quantity_on_hand <= rop`. |
| `roq` | `inventory` | Reorder quantity — the number of units ordered when replenishing. |
| `chan` | `sales_orders` | Sales channel (encoded; see below). |

For the margin on a *sale*, use the product's `wac`. `purchase_order_items.unit_cost`
reflects the cost negotiated on a particular purchase order and is used for purchasing
analysis, not sales margin.

### `sales_orders.status`

Stored as an integer representing the order's fulfillment state:

| Code | State |
|------|-------|
| `1` | Pending — placed, not yet shipped |
| `2` | Shipped — in transit |
| `3` | Delivered — fulfilled and revenue-recognized |
| `4` | Returned |
| `5` | Cancelled |

**Recognized revenue comes from delivered orders (`status = 3`).** Pending and shipped
orders are still in flight (these concentrate among recent orders), and returned or
cancelled orders are not revenue.

### `sales_orders.chan`

The channel the sale came through:

| Code | Channel |
|------|---------|
| `1` | In-store |
| `2` | Online |
| `3` | Curbside pickup |

### `purchase_orders.status`

The purchasing lifecycle, which uses its own encoding (distinct from sales status):

| Code | State |
|------|-------|
| `1` | Open — placed, not yet received |
| `2` | Received |
| `3` | Cancelled |

`received_date` is populated only for received purchase orders (`status = 2`).

### `customers.seg`

Internal customer segmentation code, assigned by the ops team. It is not derivable
from any other field — the assignment is maintained out of band.

| Code | Segment |
|------|---------|
| `1` | Standard retail |
| `2` | Small business |
| `3` | Employee account |
| `9` | Internal / test seed account |

**`seg = 9` accounts are not real customers.** They are internal seed and QA accounts
used to exercise the system, and they place normal-looking orders. Exclude them
(`seg <> 9`) from every customer- or revenue-facing metric: customer counts, revenue,
average order value, loyalty analysis, and "top customer" rankings. They are otherwise
indistinguishable from real customers — same name/email format, real orders, computed
loyalty tier — so there is no way to identify them except this code.

---

## Conventions

- **Money** is USD, stored as `REAL` with 2 decimals (`unit_price`, `total_amount`,
  `wac`, …).
- **Dates** are ISO-8601 text, `'YYYY-MM-DD'`; lexical order equals chronological order,
  so string comparison works (e.g. `WHERE order_date >= '2024-01-01'`).
- **Booleans** are `INTEGER`: `0` = false, `1` = true (e.g. `is_active`).
- Every table's primary key is a single integer column named `<table>_id`.
- The dataset spans **2023-01-01 … 2024-12-31**, and the current reporting date is
  **2024-12-31**: inventory reflects stock as of then, and purchase orders expected to
  arrive after it are still open.

---

## Tables at a glance

| Table                  | Grain (one row = )                        | Rows   |
|------------------------|-------------------------------------------|--------|
| `categories`           | a product category                        | 14     |
| `suppliers`            | a company we buy from                     | 25     |
| `products`             | a catalog item                            | 220    |
| `stores`               | a physical store                          | 8      |
| `warehouses`           | a distribution center                     | 3      |
| `employees`            | a staff member                            | 99     |
| `inventory`            | on-hand stock of a product at a store     | 1,508  |
| `customers`            | a loyalty customer                        | 1,500  |
| `sales_orders`         | a sales transaction                       | 7,000  |
| `sales_order_items`    | one product line on a sales order         | 19,114 |
| `purchase_orders`      | an order we send a supplier               | 400    |
| `purchase_order_items` | one product line on a purchase order      | 1,788  |

---

## Table reference

### `categories`
Product categories, hierarchical.

| Column | Type | Meaning |
|--------|------|---------|
| `category_id` | INTEGER PK | |
| `name` | TEXT | e.g. `Electronics`, `Cookware`, `Snacks` |
| `parent_category_id` | INTEGER → categories | `NULL` = top-level; else a subcategory of that parent |

Top-level categories: Electronics, Home & Kitchen, Apparel, Grocery, Sports & Outdoors,
Toys & Games, Health & Beauty. Subcategories include Computers/Audio (Electronics),
Cookware/Furniture (Home & Kitchen), Men's/Women's Clothing (Apparel), Snacks (Grocery).
Products are assigned to leaf categories, so a top-level rollup joins up through
`parent_category_id` (a product in `Computers` rolls up to `Electronics`).

### `suppliers`
Companies we purchase products from.

| Column | Type | Meaning |
|--------|------|---------|
| `supplier_id` | INTEGER PK | |
| `name` | TEXT | |
| `email` | TEXT | orders contact (nullable) |
| `country` | TEXT | e.g. `USA`, `China`, `Germany` |
| `lead_time_days` | INTEGER | typical days from placing a PO to delivery |
| `is_active` | INTEGER | `1` if we still order from them |

### `products`
The catalog. Each product has exactly one category and one supplier.

| Column | Type | Meaning |
|--------|------|---------|
| `product_id` | INTEGER PK | |
| `sku` | TEXT UNIQUE | stock-keeping unit, e.g. `SKU-00042` |
| `name` | TEXT | e.g. `Vertex Headphones` |
| `category_id` | INTEGER → categories | |
| `supplier_id` | INTEGER → suppliers | |
| `wac` | REAL | unit cost (see field notes); always `< unit_price` |
| `unit_price` | REAL | list retail price |
| `is_active` | INTEGER | `1` if still sold |
| `created_at` | TEXT date | date added to the catalog |

Gross margin per unit = `unit_price - wac`. Price bands are realistic per category.

### `stores`
Physical retail stores (8 US cities).

| Column | Type | Meaning |
|--------|------|---------|
| `store_id` | INTEGER PK | |
| `name` | TEXT | e.g. `NYC SoHo` |
| `city`, `state`, `country` | TEXT | US locations (`state` = 2-letter code) |
| `opened_date` | TEXT date | between 2014 and 2021 |
| `gla` | INTEGER | gross leasable area (square feet) |

### `warehouses`
Distribution centers that receive supplier shipments.

| Column | Type | Meaning |
|--------|------|---------|
| `warehouse_id` | INTEGER PK | |
| `name`, `city`, `state`, `country` | TEXT | |
| `cap` | INTEGER | storage capacity in units |

### `employees`
Store staff plus a few HQ staff.

| Column | Type | Meaning |
|--------|------|---------|
| `employee_id` | INTEGER PK | |
| `first_name`, `last_name` | TEXT | |
| `store_id` | INTEGER → stores | the store they work at; `NULL` = HQ staff |
| `role` | TEXT | see enum below |
| `hire_date` | TEXT date | on/after their store's `opened_date` |
| `hourly_wage` | REAL | scales with role |
| `is_active` | INTEGER | `1` if currently employed |

`role` ∈ `cashier`, `sales_associate`, `stock_clerk`, `store_manager` (store roles),
and `buyer`, `regional_manager` (HQ roles, `store_id IS NULL`). Only cashiers, sales
associates, and store managers appear as the seller on a sales order.

### `inventory`
Current on-hand stock. One row per (`store_id`, `product_id`) pair (unique).

| Column | Type | Meaning |
|--------|------|---------|
| `inventory_id` | INTEGER PK | |
| `store_id` | INTEGER → stores | |
| `product_id` | INTEGER → products | |
| `quantity_on_hand` | INTEGER | units currently in stock (≥ 0) |
| `rop` | INTEGER | reorder point — replenish when `quantity_on_hand <= rop` |
| `roq` | INTEGER | reorder quantity |
| `last_restocked_date` | TEXT date | last restock (within ~150 days of 2024-12-31) |

Not every store carries every product — the table is sparse (~85% coverage). A product
needs reordering when `quantity_on_hand <= rop`.

### `customers`
Loyalty customers. Walk-in sales are not in this table (`sales_orders.customer_id` is
`NULL` for them).

| Column | Type | Meaning |
|--------|------|---------|
| `customer_id` | INTEGER PK | |
| `first_name`, `last_name`, `email` | TEXT | |
| `city`, `state` | TEXT | |
| `signup_date` | TEXT date | 2018 … 2024-12-31 |
| `loyalty_tier` | TEXT | derived from lifetime delivered spend (see invariants) |
| `seg` | INTEGER | internal segmentation code — see field notes; `seg = 9` = test account, exclude from reporting |

`loyalty_tier` ∈ `none`, `silver`, `gold`, `platinum`.

### `sales_orders`
One sales transaction at a store.

| Column | Type | Meaning |
|--------|------|---------|
| `order_id` | INTEGER PK | |
| `store_id` | INTEGER → stores | where the sale happened |
| `customer_id` | INTEGER → customers | `NULL` = walk-in (~35% of orders) |
| `employee_id` | INTEGER → employees | who rang it up (same store, hired by then) |
| `order_date` | TEXT date | 2023-01-01 … 2024-12-31 |
| `status` | INTEGER | fulfillment state — see field notes (1–5) |
| `chan` | INTEGER | sales channel — see field notes (1–3) |
| `payment_method` | TEXT | `cash`, `credit_card`, `debit_card`, `gift_card` |
| `subtotal` | REAL | sum of the order's `line_total` values |
| `discount_amount` | REAL | order-level discount (often 0) |
| `total_amount` | REAL | `subtotal - discount_amount` |

Recognized revenue is delivered orders (`status = 3`).

### `sales_order_items`
Line items of a sales order.

| Column | Type | Meaning |
|--------|------|---------|
| `order_item_id` | INTEGER PK | |
| `order_id` | INTEGER → sales_orders | |
| `product_id` | INTEGER → products | |
| `quantity` | INTEGER | units sold on this line |
| `unit_price` | REAL | price charged per unit (matches the product's `unit_price`) |
| `line_total` | REAL | `quantity * unit_price` |

### `purchase_orders`
Orders we send to suppliers; goods land in a warehouse.

| Column | Type | Meaning |
|--------|------|---------|
| `po_id` | INTEGER PK | |
| `supplier_id` | INTEGER → suppliers | |
| `warehouse_id` | INTEGER → warehouses | receiving DC |
| `order_date` | TEXT date | |
| `expected_date` | TEXT date | `order_date + supplier.lead_time_days` |
| `received_date` | TEXT date | when goods arrived; populated only when `status = 2` |
| `status` | INTEGER | purchasing lifecycle — see field notes (1–3) |
| `total_cost` | REAL | sum of line `quantity_ordered * unit_cost` |

### `purchase_order_items`
Line items of a purchase order.

| Column | Type | Meaning |
|--------|------|---------|
| `po_item_id` | INTEGER PK | |
| `po_id` | INTEGER → purchase_orders | |
| `product_id` | INTEGER → products | always belongs to the PO's supplier |
| `quantity_ordered` | INTEGER | units ordered |
| `quantity_received` | INTEGER | units received; `≤ quantity_ordered`, `0` if not yet received |
| `unit_cost` | REAL | cost paid per unit on this PO |

---

## How the tables connect

```
categories ──(parent_category_id, self)
     ▲
     │ category_id
products ──────────────► suppliers ◄────── purchase_orders ──► warehouses
   │  ▲                   ▲                      │
   │  │ product_id        │ supplier_id          │ po_id
   │  │                   └──────────────── purchase_order_items
   │  │
   │  └──────────────── inventory ──► stores ◄── employees
   │                                    ▲            ▲
   │ product_id                         │ store_id   │ employee_id
   └──────────── sales_order_items ──► sales_orders ─┘
                                         │ customer_id
                                         ▼
                                      customers
```

Common join paths:
- **Sale → what was sold**: `sales_orders → sales_order_items → products → categories`.
- **Sale → who/where**: `sales_orders → stores`, `→ employees`, `→ customers`.
- **Restocking**: `products → suppliers → purchase_orders → purchase_order_items`,
  received into `warehouses`.
- **Stock levels**: `inventory → stores` and `inventory → products`.

---

## Invariants

These rules hold for every row and can be relied on when writing and validating queries:

1. `sales_orders.total_amount = subtotal - discount_amount`.
2. `sales_orders.subtotal = SUM(sales_order_items.line_total)` for that order.
3. `sales_order_items.line_total = quantity * unit_price`.
4. `products.unit_price > products.wac` (every product has positive margin).
5. `purchase_orders.total_cost = SUM(quantity_ordered * unit_cost)` over its lines.
6. Every `purchase_order_items.product_id` belongs to that PO's `supplier_id`.
7. `quantity_received ≤ quantity_ordered`; a PO has a `received_date` iff `status = 2`.
8. A sales order's `employee_id` works at the order's `store_id` and was hired on/before `order_date`.
9. If `customer_id` is set, `order_date ≥ customer.signup_date`; always `order_date ≥ store.opened_date`.
10. `inventory` has at most one row per (`store_id`, `product_id`); `quantity_on_hand ≥ 0`.
11. `loyalty_tier` is derived from lifetime delivered (`status = 3`) spend:
    `platinum ≥ $5,000`, `gold ≥ $2,000`, `silver ≥ $500`, else `none`. (Tiers are
    computed over all accounts, including `seg = 9` test accounts.)
12. `customers.seg = 9` accounts are internal/test seed accounts and are excluded from
    customer- and revenue-facing reporting (`WHERE seg <> 9`).

---

## Example questions this data answers

Simple:
- What is total revenue? (`SUM(total_amount) WHERE status = 3`)
- How many orders were placed in 2024?
- How many products are in each category?
- Which stores are the largest by floor area (`gla`)?

Joins / grouping:
- Which product categories generate the most revenue?
- Who are the top 10 customers by lifetime spend? (exclude test accounts, `seg <> 9`)
- How many active customers do we have? (`seg <> 9`)
- What's the average order value per store?
- Which employees rang up the most delivered sales in 2024?
- Revenue by month; revenue by channel (`chan`); revenue by payment method.

Inventory / operations:
- Which products need reordering (`quantity_on_hand <= rop`), and at which stores?
- Which products are out of stock somewhere?
- Which suppliers have open (`status = 1`) purchase orders?
- What's total inventory value on hand (`quantity_on_hand * wac`) per store?

Deeper:
- Gross margin by category (`SUM((unit_price - wac) * quantity)` on delivered lines).
- Do higher loyalty tiers spend more per order?
- Which supplier's products sell best, and is their lead time short enough to keep up?
- Return rate (`status = 4`) by category or store.
