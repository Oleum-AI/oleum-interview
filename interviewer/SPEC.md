# Part 2 — canonical spec (INTERVIEWER ONLY)

File: order_management.md
Role: domain
Contents: customers/segments, catalog, orders & lines, status ledger, payments, promotions, gift cards
────────────────────────────────────────
File: fulfillment_and_shipping.md
Role: domain
Contents: shipments, packages, legs, tracking, exceptions, pick tasks, returns, carriers, facilities, lanes
────────────────────────────────────────
File: warehouse_and_inventory.md
Role: domain
Contents: warehouses/zones/bins, suppliers, inventory & lots, the movement ledger, replenishment, receipts,
transfers, cycle counts
────────────────────────────────────────
File: reference.md
Role: cross-cutting
Contents: 8 sections: Overview · Identifiers & Keys (G1) · Code Dictionary (G4 — the only place integers live) ·
Lifecycle & Statuses (G2) · Exclusions & Data Quality (G3) · Metric Definitions · Pricing/Costs/Billing · Query
Recipes


Single source of truth for the Part 2 dataset. The schema
(`database/schema.sql`), the generator (`database/build.py`), and
every guidance doc under `docs/part2/guidance/` must agree with what is written
here. Do NOT ship this file to the candidate (the whole `interviewer/` dir is
excluded at merge).

The world: a **mid-size 3PL / omnichannel retail logistics operator**. Three
clean domains that share keys so cross-domain questions are answerable.

Deterministic build: `random.seed(42)`. `TODAY = 2024-12-31`.
47 tables (14 + 15 + 18). Money in **dollars** (REAL, 2dp). Weights in **kilograms**.
Dates `YYYY-MM-DD`; timestamps ISO-8601. No timezone/units trap.

---

## Cross-cutting conventions (LOAD-BEARING — the traps)

**G1 — two identifier vocabularies for the same product.**
- **Order/Returns/Shipment side** references products by **`sku` (TEXT)**,
  formatted `SKU-%05d` (e.g. `SKU-00042`). Tables: `order_lines`, `return_lines`,
  `shipment_items`.
- **Inventory/Supplier/Warehouse side** references the same product by
  **`item_code` (INTEGER)** = `products.product_id` (e.g. `42`). Tables:
  `supplier_products`, `inventory`, `inventory_lots`, `inventory_transactions`,
  `replenishment_lines`, `receipt_lines`, `stock_transfer_lines`,
  `inventory_adjustments`, `cycle_counts`, `pick_lines`.
- `products` is the ONLY bridge (`product_id` + `sku`).
  `item_code = CAST(SUBSTR(sku,5) AS INTEGER)`;
  `sku = 'SKU-' || printf('%05d', item_code)`.
- Naive `order_lines.sku = inventory.item_code` → ZERO rows, no error.

**G2 — `status` / `status_code` is a different code set per table.** Same column
name, different meaning. The terminal "done" integer differs by table (orders
fulfilled=4, shipments delivered=5, replenishment received=4, legs completed=3,
transfers received=3, picks completed=4). Reusing a decode across tables →
plausible-but-wrong.

**G3 — `orders.priority_code = 7` = internal/test orders, exclude from ALL
reporting.** No data signal (normal customers/amounts/shipments). ~3% of orders.
Real tiers are 1 standard / 2 expedited / 3 rush. Rule lives only in guidance.

**G4** — coded columns require a 2-hop lookup (column → code-set name in a topic
doc → values in the dictionary doc). **G5** — guidance is topic-organized, not
per-table.

---

## Code sets (shared code dictionary)

| Code set | Values |
|---|---|
| CUSTOMER_SEGMENT | 1 consumer, 2 small_business, 3 enterprise, 4 government |
| ADDRESS_TYPE | 1 billing, 2 shipping, 3 both |
| ORDER_STATUS | 1 draft, 2 placed, 3 confirmed, 4 fulfilled, 5 cancelled, 6 returned |
| ORDER_PRIORITY | 1 standard, 2 expedited, 3 rush, 7 internal_test |
| ORDER_CHANNEL | 1 web, 2 mobile_app, 3 phone, 4 marketplace, 5 in_store |
| PROMO_TYPE | 1 percent_off, 2 amount_off, 3 bogo, 4 free_shipping |
| PAYMENT_METHOD | 1 credit_card, 2 debit_card, 3 paypal, 4 gift_card, 5 net_terms, 6 wire |
| PAYMENT_STATUS | 1 authorized, 2 captured, 3 refunded, 4 voided, 5 failed |
| GIFTCARD_STATUS | 1 active, 2 redeemed, 3 expired, 4 void |
| GIFTCARD_TXN_TYPE | 1 issue, 2 redeem, 3 reload, 4 refund |
| SERVICE_LEVEL | 1 ground, 2 two_day, 3 overnight, 4 economy, 5 freight |
| FACILITY_TYPE | 1 origin_dc, 2 hub, 3 cross_dock, 4 last_mile_depot, 5 port |
| SHIP_STATUS | 1 label_created, 2 picked_up, 3 in_transit, 4 out_for_delivery, 5 delivered, 6 exception, 7 lost |
| PACKAGING_TYPE | 1 box, 2 envelope, 3 pallet, 4 tube, 5 crate |
| TRANSPORT_MODE | 1 truck, 2 rail, 3 air, 4 ocean, 5 parcel |
| LEG_STATUS | 1 pending, 2 in_progress, 3 completed, 4 failed |
| TRACK_EVENT | 1 created, 2 departed, 3 arrived, 4 customs_hold, 5 delivered, 6 delivery_failed, 7 return_to_sender |
| EXCEPTION_TYPE | 1 weather_delay, 2 address_issue, 3 damaged, 4 missed_delivery, 5 customs, 6 mechanical |
| PICK_STATUS | 1 queued, 2 assigned, 3 picking, 4 completed, 5 short |
| RETURN_REASON | 1 defective, 2 wrong_item, 3 no_longer_needed, 4 damaged_in_transit, 5 late_delivery |
| RETURN_STATUS | 1 requested, 2 authorized, 3 received, 4 refunded, 5 rejected |
| RETURN_DISPOSITION | 1 restock, 2 refurbish, 3 scrap, 4 return_to_supplier |
| ITEM_CONDITION | 1 new, 2 opened, 3 damaged, 4 defective |
| ZONE_TYPE | 1 receiving, 2 storage, 3 picking, 4 shipping, 5 cold_storage |
| SUPPLIER_STATUS | 1 active, 2 on_hold, 3 terminated, 4 pending_approval |
| PO_STATUS | 1 draft, 2 open, 3 partial, 4 received, 5 cancelled |
| INV_TXN_TYPE | 1 receipt, 2 shipment, 3 transfer_out, 4 transfer_in, 5 adjustment, 6 return_restock |
| INVOICE_STATUS | 1 draft, 2 submitted, 3 approved, 4 paid, 5 disputed |
| TRANSFER_STATUS | 1 requested, 2 in_transit, 3 received, 4 cancelled |
| ADJ_REASON | 1 cycle_count, 2 damage, 3 theft, 4 found, 5 correction |
| CYCLE_COUNT_STATUS | 1 scheduled, 2 counted, 3 reconciled |

Columns using each `status`-family set: orders.status→ORDER_STATUS;
shipments.status→SHIP_STATUS; shipment_legs.status→LEG_STATUS;
returns.status→RETURN_STATUS; replenishment_orders.status→PO_STATUS;
payments.status_code→PAYMENT_STATUS; pick_tasks.status_code→PICK_STATUS;
gift_cards.status_code→GIFTCARD_STATUS; suppliers.status_code→SUPPLIER_STATUS;
supplier_invoices.status_code & carrier_invoices.status_code→INVOICE_STATUS;
stock_transfers.status_code→TRANSFER_STATUS; cycle_counts.status_code→CYCLE_COUNT_STATUS.

---

## Domain 1 — Order Management (14)

- **product_categories**(category_id PK, name, parent_category_id FK NULL)
- **products**(product_id PK, sku UNIQUE, name, category_id FK, unit_price, weight_kg, is_active, launched_date) — SKU⇄item_code bridge
- **product_attributes**(attribute_id PK, product_id FK, attr_name, attr_value)
- **price_history**(price_history_id PK, product_id FK, effective_date, unit_price)
- **customers**(customer_id PK, first_name, last_name, email, phone, segment_code[CUSTOMER_SEGMENT], signup_date, is_active)
- **customer_addresses**(address_id PK, customer_id FK, address_type_code[ADDRESS_TYPE], line1, city, state, postal_code, country, is_default)
- **orders**(order_id PK, customer_id FK, order_date, status[ORDER_STATUS], priority_code[ORDER_PRIORITY], channel_code[ORDER_CHANNEL], ship_to_address_id FK, promised_date, order_total)
- **order_lines**(order_line_id PK, order_id FK, sku TEXT→products.sku, quantity, unit_price, discount_amount, line_total)
- **order_status_history**(history_id PK, order_id FK, status[ORDER_STATUS], changed_ts, note)
- **payments**(payment_id PK, order_id FK, method_code[PAYMENT_METHOD], status_code[PAYMENT_STATUS], amount, paid_date)
- **promotions**(promotion_id PK, code, name, promo_type_code[PROMO_TYPE], value, start_date, end_date)
- **order_promotions**(order_promotion_id PK, order_id FK, promotion_id FK, discount_amount)
- **gift_cards**(gift_card_id PK, code, initial_balance, current_balance, status_code[GIFTCARD_STATUS], issued_date, customer_id FK NULL)
- **gift_card_transactions**(gc_txn_id PK, gift_card_id FK, order_id FK NULL, txn_type_code[GIFTCARD_TXN_TYPE], amount, txn_ts)

## Domain 2 — Fulfillment (15)

- **carriers**(carrier_id PK, name, scac, country, is_active)
- **carrier_services**(service_id PK, carrier_id FK, service_level_code[SERVICE_LEVEL], name, transit_days_est)
- **facilities**(facility_id PK, code, name, facility_type_code[FACILITY_TYPE], city, state, country)
- **shipments**(shipment_id PK, order_id FK, carrier_id FK, service_id FK, origin_warehouse_id FK→warehouses, status[SHIP_STATUS], ship_date, delivered_date NULL, promised_date, tracking_number, weight_kg)
- **packages**(package_id PK, shipment_id FK, packaging_type_code[PACKAGING_TYPE], weight_kg, length_cm, width_cm, height_cm)
- **shipment_items**(shipment_item_id PK, shipment_id FK, package_id FK, order_line_id FK→order_lines, sku TEXT→products.sku, quantity)
- **shipment_legs**(leg_id PK, shipment_id FK, leg_seq, mode_code[TRANSPORT_MODE], from_facility_id FK→facilities, to_facility_id FK→facilities, status[LEG_STATUS], departed_ts, arrived_ts NULL)
- **tracking_events**(event_id PK, shipment_id FK, event_code[TRACK_EVENT], event_ts, facility_id FK→facilities NULL, message)
- **delivery_exceptions**(exception_id PK, shipment_id FK, exception_type_code[EXCEPTION_TYPE], reported_ts, resolved_ts NULL, note)
- **pick_tasks**(pick_id PK, warehouse_id FK, order_id FK, status_code[PICK_STATUS], created_ts, completed_ts NULL)
- **pick_lines**(pick_line_id PK, pick_id FK, item_code INT→products.product_id, bin_id FK→bins NULL, quantity)
- **returns**(return_id PK, order_id FK, rma_number UNIQUE, reason_code[RETURN_REASON], status[RETURN_STATUS], disposition_code[RETURN_DISPOSITION] NULL, requested_date, received_date NULL)
- **return_lines**(return_line_id PK, return_id FK, sku TEXT→products.sku, quantity, condition_code[ITEM_CONDITION] NULL)
- **carrier_invoices**(carrier_invoice_id PK, carrier_id FK, invoice_number, amount, status_code[INVOICE_STATUS], invoice_date, due_date, paid_date NULL)
- **route_lanes**(lane_id PK, origin_facility_id FK→facilities, dest_facility_id FK→facilities, mode_code[TRANSPORT_MODE], distance_km, standard_transit_days)

## Domain 3 — Warehouse & Inventory (18)

- **warehouses**(warehouse_id PK, code UNIQUE, name, city, state, country, capacity_units, is_active)
- **warehouse_zones**(zone_id PK, warehouse_id FK, zone_code, zone_type_code[ZONE_TYPE], capacity_units)
- **bins**(bin_id PK, warehouse_id FK, zone_id FK, bin_code, capacity_units)
- **suppliers**(supplier_id PK, name, country, status_code[SUPPLIER_STATUS], default_lead_time_days)
- **supplier_products**(supplier_product_id PK, supplier_id FK, item_code INT→products.product_id, supplier_sku, unit_cost, lead_time_days, is_preferred)
- **supplier_contacts**(contact_id PK, supplier_id FK, name, email, phone, role)
- **inventory**(inventory_id PK, warehouse_id FK, item_code INT→products.product_id, quantity_on_hand, quantity_allocated, reorder_point, reorder_qty, last_counted_date) — UNIQUE(warehouse_id,item_code)
- **inventory_lots**(lot_id PK, warehouse_id FK, item_code INT→products.product_id, lot_number, quantity, received_date, expiry_date NULL)
- **inventory_transactions**(txn_id PK, warehouse_id FK, item_code INT→products.product_id, txn_type_code[INV_TXN_TYPE], quantity_delta, reference_type, reference_id, txn_ts)
- **replenishment_orders**(repl_id PK, supplier_id FK, warehouse_id FK, status[PO_STATUS], order_date, expected_date, received_date NULL, total_cost)
- **replenishment_lines**(repl_line_id PK, repl_id FK, item_code INT→products.product_id, qty_ordered, qty_received, unit_cost)
- **receipts**(receipt_id PK, repl_id FK, warehouse_id FK, received_ts, reference)
- **receipt_lines**(receipt_line_id PK, receipt_id FK, item_code INT→products.product_id, qty_received, condition_code[ITEM_CONDITION])
- **supplier_invoices**(supplier_invoice_id PK, supplier_id FK, repl_id FK NULL, invoice_number, amount, status_code[INVOICE_STATUS], invoice_date, due_date, paid_date NULL)
- **stock_transfers**(transfer_id PK, from_warehouse_id FK→warehouses, to_warehouse_id FK→warehouses, status_code[TRANSFER_STATUS], created_date, shipped_date NULL, received_date NULL)
- **stock_transfer_lines**(transfer_line_id PK, transfer_id FK, item_code INT→products.product_id, qty_requested, qty_shipped, qty_received)
- **inventory_adjustments**(adjustment_id PK, warehouse_id FK, item_code INT→products.product_id, adjustment_date, quantity_delta, reason_code[ADJ_REASON])
- **cycle_counts**(count_id PK, warehouse_id FK, item_code INT→products.product_id, bin_id FK→bins NULL, system_qty, counted_qty, variance, count_date, status_code[CYCLE_COUNT_STATUS])

(Domain 3 lists 18 bullets; `inventory_adjustments` + `cycle_counts` bring the
audit tables in — 47 tables total across the three domains.)

---

## Key relationships (cross-domain joins)

- orders → shipments → {packages, shipment_items, shipment_legs, tracking_events, delivery_exceptions}
- orders → returns → return_lines ; orders → pick_tasks → pick_lines
- order_lines.sku ⇄ products.sku ; products.product_id = item_code everywhere on the inventory side
- shipments.origin_warehouse_id → warehouses → {inventory, bins, zones, ...}
- replenishment_orders → suppliers, warehouses → replenishment_lines, receipts→receipt_lines, supplier_invoices
- shipment_legs.from/to_facility_id → facilities ; route_lanes between facilities

## Semantics that must match the data

- **Delivered late**: shipment `status=5` (delivered) AND `delivered_date > promised_date`.
- **Below reorder point**: `inventory.quantity_on_hand < inventory.reorder_point`.
- **Recognized revenue / order counts** exclude `orders.priority_code=7`.
- Fulfilled order (status 4) → ≥1 shipment; cancelled (5)/draft(1) → none.
- `inventory_transactions` is a movement ledger; adjustments/receipts/transfers post to it.
