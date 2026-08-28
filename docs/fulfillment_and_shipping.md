# Fulfillment and Shipping

This document is the deep dive on the movement side of the business: how an order
becomes one or more shipments, how those shipments are packed, routed across a
transportation network, tracked, and occasionally recovered from an exception;
the warehouse pick work that assembles an order before it ships; and the returns
process that runs after delivery. It also covers the carrier and service reference
data that shipments hang off, and it points at the freight-billing tables at a
topical level.

Read `reference.md` first for the company and the three-domain map. This
document assumes you know that the order is the spine of the warehouse, that a
shipment ships *from* a warehouse, and that products are referenced by two
different identifier vocabularies depending on which side of the business you are
standing on. Every coded column named below is decoded in exactly one place —
`reference.md` — and this document only ever names the code set and uses
its symbolic labels.

Coded columns (`status`, `*_code`) are decoded via the **Code Dictionary** in `reference.md`; this guide names the code set each column uses, and that dictionary gives the integer values.

**SQL convention used in this document.** Because the integer code values live only
in the **Code Dictionary**, the worked queries never hard-code them. Where a query *filters* on a coded
value, it uses a named bind parameter (for example `:ship_status_delivered`) and a
comment naming the code set and label; bind the integer from the **Code Dictionary** at run time. Where
a query merely *groups by* or *selects* a coded column, the raw column is carried
through and decoded to its label at presentation, again via the **Code Dictionary**. Both patterns are
valid SQLite and keep the dictionary as the single source of the numbers.

A short orientation before the details:

- The **shipment** is the hub. Everything physical about getting the order to the
  customer hangs off `shipments`: the carrier and service chosen, the origin
  warehouse, the packages, the shipped contents, the multi-leg journey, the
  tracking stream, and any delivery exceptions.
- The **pick task** is the warehouse work that precedes the shipment. It assembles
  the order inside a distribution center. Picks reference product by `item_code`;
  shipment contents reference product by `sku`. Keeping those two straight is the
  single most common source of a zero-row join in this domain (see
  `reference.md`).
- The **return** is the reverse flow that runs after delivery. It has its own
  status vocabulary, its own reason and disposition vocabularies, and its own
  item-condition vocabulary.

The rest of this document walks each area in the order an analyst usually needs
them: carriers and services, the facility network and lanes, shipments and the
on-time definition, packages, shipment items and fan-out, legs, tracking events,
delivery exceptions, pick tasks and pick lines, returns and return lines, and
finally carrier invoices.

---

## Carriers and carrier services

### Table: carriers

- **Columns:** carrier_id, name, scac, country, is_active
- **Joined by:** PK `carrier_id` (← `shipments.carrier_id`, `carrier_services.carrier_id`, `carrier_invoices.carrier_id`)

`carriers` is the master list of the transportation companies we tender freight
to. Columns:

- `carrier_id` — primary key. Every shipment names exactly one carrier through
  `shipments.carrier_id`.
- `name` — the carrier's business name, for display and grouping.
- `scac` — the Standard Carrier Alpha Code, the short alphabetic carrier
  identifier used across freight documents. It is a stable business identifier for
  the carrier and is convenient when you want a compact label, but it is not the
  join key — always join on `carrier_id`.
- `country` — the carrier's home country.
- `is_active` — whether the carrier is currently one we tender to. As with every
  `is_active` flag in this warehouse, an inactive carrier still appears in
  history: a carrier we no longer use can still be named on old shipments and old
  invoices. Filter on `is_active` only when the question is about the *current*
  roster of usable carriers, not about historical shipment volume.

### Table: carrier_services

- **Columns:** service_id, carrier_id, service_level_code, name, transit_days_est
- **Joined by:** PK `service_id` (← `shipments.service_id`); FK `carrier_id` → `carriers.carrier_id`

A carrier does not sell "a shipment." It sells named *services*, each at a
particular speed class. `carrier_services` holds one row per service a carrier
offers:

- `service_id` — primary key. `shipments.service_id` points here.
- `carrier_id` — the carrier that owns this service.
- `service_level_code` — the speed/class of the service, drawn from the
  **SERVICE_LEVEL** code set (labels: ground, two_day, overnight, economy,
  freight). This is the analytic dimension you group by when someone asks about
  "expedited vs ground" volume or cost.
- `name` — the carrier's marketing name for the service (a human label).
- `transit_days_est` — the carrier's own estimate, in days, of how long this
  service takes door to door. This is a *reference* number attached to the
  service, not a measurement of any individual shipment.

**How promised transit relates to the service level.** The chain of reasoning is:
the order carries a `promised_date`; the shipment is placed on a `service_id`; the
service has a `service_level_code` and a `transit_days_est`. The service level is
the *class of service the customer paid for or that operations selected*, and
`transit_days_est` is the *expected* number of days that class should take. Whether
a given shipment actually met its promise is measured on the shipment itself
(`delivered_date` vs `promised_date`, below), not by comparing to
`transit_days_est`. Use `transit_days_est` to answer questions about the
*expected/quoted* transit of a service; use the shipment dates to answer questions
about *actual* performance. Keeping "estimated transit" (a property of the service)
separate from "was it late" (a property of the shipment) is important; they answer
different questions and the canonical definitions live in
`reference.md`.

Because `service_level_code` lives on `carrier_services` and not on `shipments`,
any shipment-level question sliced by service level must join through
`carrier_services`. There is no service-level column on the shipment itself.

### Worked example — service catalog by level and its quoted transit

Group a carrier's services by service level and show the average quoted transit.
`service_level_code` is grouped and decoded to its SERVICE_LEVEL label at
presentation via `reference.md`.

```sql
-- Services offered by each carrier, with quoted transit, ordered by speed class.
SELECT c.name              AS carrier_name,
       c.scac,
       cs.service_level_code,       -- decode via SERVICE_LEVEL in reference.md
       COUNT(*)            AS services_at_level,
       AVG(cs.transit_days_est) AS avg_quoted_transit_days
FROM carrier_services cs
JOIN carriers c ON c.carrier_id = cs.carrier_id
WHERE c.is_active = 1                -- current roster only; drop this for all-history
GROUP BY c.carrier_id, cs.service_level_code
ORDER BY c.name, cs.service_level_code;
```

`services_at_level` above will usually be 1 unless a carrier sells more than one
named product at the same speed class; the pattern generalizes either way.

### Worked example — quoted transit vs measured transit by service level

A frequent analytic ask is "does the service actually deliver in the time it
quotes?" That question crosses the estimate/actual boundary described above: the
quote lives on `carrier_services.transit_days_est`, the measurement lives on the
delivered shipments placed on that service. Compute both side by side, at the
service-level grain, over delivered shipments only. Bind the SHIP_STATUS delivered
value from the **Code Dictionary** for the filter; `service_level_code` is decoded at presentation.

```sql
-- Quoted transit vs actual transit, by service level, over delivered shipments.
SELECT cs.service_level_code,                    -- decode via SERVICE_LEVEL in the Code Dictionary
       COUNT(*)                          AS delivered_shipments,
       ROUND(AVG(cs.transit_days_est), 1) AS avg_quoted_days,
       ROUND(AVG(julianday(s.delivered_date) - julianday(s.ship_date)), 1)
                                          AS avg_actual_days
FROM shipments s
JOIN carrier_services cs ON cs.service_id = s.service_id
WHERE s.status = :ship_status_delivered   -- bind the SHIP_STATUS delivered value from the Code Dictionary
GROUP BY cs.service_level_code
ORDER BY cs.service_level_code;
```

The gap between `avg_quoted_days` and `avg_actual_days` is a service-quality
signal, but note it is *not* the same as the on-time rate: a service can beat its
quote on average and still miss the customer promise on individual shipments,
because the promise (`shipments.promised_date`) and the service quote
(`transit_days_est`) are set independently. Keep the three concepts distinct —
quoted transit (service reference), actual transit (measured on the shipment), and
on-time (actual delivery vs the promise). The canonical framing is in
`reference.md`.

---

## Facilities and route lanes

### Table: facilities

- **Columns:** facility_id, code, name, facility_type_code, city, state, country
- **Joined by:** PK `facility_id` (← `shipment_legs.from_facility_id`, `shipment_legs.to_facility_id`, `tracking_events.facility_id`, `route_lanes.origin_facility_id`, `route_lanes.dest_facility_id`)

`facilities` are the nodes in the *transportation* network — the places freight
moves *between*. This is a distinct concept from a warehouse. A **warehouse**
(`warehouses`, covered in `warehouse_and_inventory.md`) holds inventory and is
where a shipment *originates* (`shipments.origin_warehouse_id`). A **facility** is a
routing node that a shipment *leg* travels from and to. Do not join a shipment's
`origin_warehouse_id` to `facilities`; they are different tables with different
keys.

Columns:

- `facility_id` — primary key. Referenced by `shipment_legs.from_facility_id`,
  `shipment_legs.to_facility_id`, `tracking_events.facility_id`,
  `route_lanes.origin_facility_id`, and `route_lanes.dest_facility_id`.
- `code` — a short unique facility code (a stable business identifier).
- `name` — display name.
- `facility_type_code` — the kind of node, from the **FACILITY_TYPE** code set
  (labels: origin_dc, hub, cross_dock, last_mile_depot, port). This is how you
  slice the network by role: for instance, "how much volume passes through a hub"
  or "which shipments touched a port."
- `city`, `state`, `country` — location.

The facility types describe a typical omnichannel network: freight originates at an
**origin_dc**, consolidates at a **hub**, may pass through a **cross_dock** for
sortation without storage, clears international movement through a **port**, and is
handed to the customer from a **last_mile_depot**. A single shipment's legs will
often walk up and down this hierarchy.

### Table: route_lanes

- **Columns:** lane_id, origin_facility_id, dest_facility_id, mode_code, distance_km, standard_transit_days
- **Joined by:** PK `lane_id`; FK `origin_facility_id` → `facilities.facility_id`, `dest_facility_id` → `facilities.facility_id`

`route_lanes` is the reference table of standard origin→destination routes the
network runs on. Think of a lane as "the standard way we move freight from
facility A to facility B by a given mode." Columns:

- `lane_id` — primary key.
- `origin_facility_id`, `dest_facility_id` — the two endpoints, both pointing at
  `facilities`.
- `mode_code` — the transport mode for the lane, from the **TRANSPORT_MODE** code
  set (labels: truck, rail, air, ocean, parcel).
- `distance_km` — the lane distance in kilometers.
- `standard_transit_days` — the expected transit time for the lane, in days.

A lane is a *standard/planned* route; an individual shipment leg is an *actual*
movement. A leg carries its own `from_facility_id`, `to_facility_id`, and
`mode_code`, so you can align a leg to its lane by matching those three, but the
schema does not carry a foreign key from a leg to a lane — the correspondence is
by facility pair plus mode, not by a stored `lane_id` on the leg. Treat
`route_lanes.standard_transit_days` as the planning benchmark for a lane and the
leg's `departed_ts`/`arrived_ts` as the actual.

### Worked example — actual leg duration vs the lane standard

Because a leg does not store a `lane_id`, join leg to lane on the facility pair and
mode to compare actual transit against the standard. `mode_code` is decoded to its
TRANSPORT_MODE label at presentation via the **Code Dictionary**.

```sql
-- For completed legs, compare actual days in transit to the lane's standard.
SELECT sl.shipment_id,
       sl.leg_seq,
       sl.mode_code,                          -- decode via TRANSPORT_MODE in the Code Dictionary
       f_from.code AS from_facility,
       f_to.code   AS to_facility,
       rl.standard_transit_days,
       julianday(sl.arrived_ts) - julianday(sl.departed_ts) AS actual_days
FROM shipment_legs sl
JOIN facilities f_from ON f_from.facility_id = sl.from_facility_id
JOIN facilities f_to   ON f_to.facility_id   = sl.to_facility_id
LEFT JOIN route_lanes rl
       ON rl.origin_facility_id = sl.from_facility_id
      AND rl.dest_facility_id   = sl.to_facility_id
      AND rl.mode_code          = sl.mode_code
WHERE sl.arrived_ts IS NOT NULL                -- only legs that have completed
ORDER BY sl.shipment_id, sl.leg_seq;
```

Note the `LEFT JOIN` to `route_lanes`: not every actual facility pair need have a
defined standard lane, and you do not want to silently drop legs that ran on an
ad-hoc route. Note also `arrived_ts IS NOT NULL` — a leg that has departed but not
arrived has a NULL `arrived_ts`, and `julianday(NULL)` yields NULL, so those legs
would produce a NULL duration rather than a wrong one; filtering them out keeps the
average honest.

### Worked example — facility throughput by role

To answer "how much freight moves through each kind of node," count the legs that
touch a facility. A leg touches two facilities (its `from` and its `to`), so the
clean way to count node throughput is to treat each leg endpoint as one touch,
which a `UNION ALL` of the two endpoint columns expresses directly.
`facility_type_code` is decoded to its FACILITY_TYPE label at presentation via the **Code Dictionary**.

```sql
-- Leg touches per facility type (each leg contributes one "from" touch and one "to" touch).
WITH touches AS (
    SELECT from_facility_id AS facility_id FROM shipment_legs
    UNION ALL
    SELECT to_facility_id   AS facility_id FROM shipment_legs
)
SELECT f.facility_type_code,        -- decode via FACILITY_TYPE in the Code Dictionary
       COUNT(*) AS leg_touches
FROM touches t
JOIN facilities f ON f.facility_id = t.facility_id
GROUP BY f.facility_type_code
ORDER BY leg_touches DESC;
```

Use `UNION ALL`, not `UNION`: `UNION` would deduplicate identical
`(facility_id)` values across the two halves and undercount, whereas each physical
leg endpoint is a distinct touch that should be counted. If instead you want
distinct *shipments* that passed through a facility type — a different question —
carry the `shipment_id` through the CTE and `COUNT(DISTINCT shipment_id)`.

---

## Table: shipments

- **Columns:** shipment_id, order_id, carrier_id, service_id, origin_warehouse_id, status, ship_date, delivered_date, promised_date, tracking_number, weight_kg
- **Joined by:** PK `shipment_id` (← `packages.shipment_id`, `shipment_items.shipment_id`, `shipment_legs.shipment_id`, `tracking_events.shipment_id`, `delivery_exceptions.shipment_id`); FK `order_id` → `orders.order_id`, `carrier_id` → `carriers.carrier_id`, `service_id` → `carrier_services.service_id`, `origin_warehouse_id` → `warehouses.warehouse_id`

`shipments` is the operational hub of this domain. One row is one shipment
fulfilling an order. A fulfilled order (order `status` in the **ORDER_STATUS** code
set at the fulfilled label) has one or more shipments; a cancelled or draft order
has none (see `reference.md`). One order can have several shipments
— split shipments are normal in a 3PL — so **never assume one shipment per order**.

Columns:

- `shipment_id` — primary key.
- `order_id` — the order this shipment fulfills, pointing at `orders`. This is the
  join back into the order-management domain. Because an order can fan out to
  multiple shipments, joining `orders` to `shipments` multiplies order rows; see
  the fan-out warning below and in `reference.md`.
- `carrier_id` — the carrier moving the shipment, pointing at `carriers`.
- `service_id` — the carrier service chosen, pointing at `carrier_services`. This
  is your path to the service level (`carrier_services.service_level_code`,
  **SERVICE_LEVEL**).
- `origin_warehouse_id` — the warehouse the shipment ships *from*, pointing at
  `warehouses` (the inventory domain — see `warehouse_and_inventory.md`). This
  is **not** a facility.
- `status` — the shipment's lifecycle state, from the **SHIP_STATUS** code set
  (labels: label_created, picked_up, in_transit, out_for_delivery, delivered,
  exception, lost). The delivered label is the terminal "successfully delivered"
  state for a shipment. See the on-time definition below and the state machine in
  `reference.md`.
- `ship_date` — the date the shipment left the origin (a `YYYY-MM-DD` date).
- `delivered_date` — the date it was delivered, **NULL until delivered**. This is a
  lifecycle NULL: a shipment that has not been delivered has no delivered date. Any
  delivery-timing metric must handle the NULL.
- `promised_date` — the date we promised delivery by (a `YYYY-MM-DD` date). This is
  the benchmark for on-time vs late.
- `tracking_number` — the carrier tracking identifier for the shipment.
- `weight_kg` — the shipment's total weight in kilograms.

### The on-time / late definition (authoritative operational rule)

This is the single most important semantic in the domain and it must be stated
precisely. Reference `reference.md` for the canonical metric; the
operational rule is:

1. A shipment is **delivered** when its `status` (the **SHIP_STATUS** code set) is
   the *delivered* label. It is not delivered by having a non-NULL
   `delivered_date` alone, and it is not delivered by any other status — in
   particular the *out_for_delivery*, *exception*, and *lost* labels are not
   delivered. Use the SHIP_STATUS delivered label as the gate.
2. A delivered shipment is **late** when `delivered_date > promised_date`. It is
   **on time** when `delivered_date <= promised_date` (delivering exactly on the
   promised date counts as on time).
3. On-time and late are defined **only over delivered shipments**. A shipment that
   is still in transit, out for delivery, sitting in an exception, or lost has no
   on-time outcome yet — it is neither on time nor late, it is undelivered. Do not
   count undelivered shipments as "on time" merely because their `delivered_date`
   is NULL and NULL fails the `>` comparison. Always restrict the denominator to
   delivered shipments first.

The subtle pitfall is step 3 interacting with NULL. `delivered_date > promised_date`
is NULL (not true) when `delivered_date` is NULL, so an undelivered shipment will
*not* be flagged late — but it will also not be a delivered shipment, so it should
never have entered the calculation. Gate on the SHIP_STATUS delivered label first,
then apply the date comparison.

Also mind `promised_date` NULLs. If `promised_date` is NULL for a delivered
shipment, the `>` comparison is NULL and the shipment is neither on time nor late;
decide explicitly whether such shipments belong in your denominator and state the
choice.

### Worked example — on-time delivery rate

Compute the on-time rate over delivered shipments. Bind the SHIP_STATUS delivered
value from `reference.md` for the filter.

```sql
-- On-time delivery rate: among DELIVERED shipments, share delivered on/before promise.
SELECT COUNT(*)                                                   AS delivered_shipments,
       SUM(CASE WHEN s.delivered_date > s.promised_date THEN 1 ELSE 0 END) AS late_shipments,
       ROUND(
         100.0 * SUM(CASE WHEN s.delivered_date <= s.promised_date THEN 1 ELSE 0 END)
              / COUNT(*), 2)                                       AS on_time_pct
FROM shipments s
WHERE s.status = :ship_status_delivered   -- bind the SHIP_STATUS delivered value from the Code Dictionary
  AND s.promised_date IS NOT NULL;   -- exclude shipments with no promise from the rate
```

The `promised_date IS NOT NULL` guard makes the denominator well defined: every
shipment in the calculation both is delivered and had a promise to measure against.

### Worked example — days to deliver, and undelivered aging as of TODAY

Two related timing questions. First, actual door-to-door days for delivered
shipments; second, how long undelivered shipments have been outstanding as of
TODAY (2024-12-31).

```sql
-- Actual transit days for delivered shipments.
SELECT s.shipment_id,
       s.ship_date,
       s.delivered_date,
       julianday(s.delivered_date) - julianday(s.ship_date) AS days_to_deliver
FROM shipments s
WHERE s.status = :ship_status_delivered   -- bind the SHIP_STATUS delivered value from the Code Dictionary
ORDER BY days_to_deliver DESC;
```

```sql
-- Aging of shipments not yet delivered, measured against TODAY = 2024-12-31.
SELECT s.shipment_id,
       s.status,                       -- decode via SHIP_STATUS in the Code Dictionary
       s.ship_date,
       julianday('2024-12-31') - julianday(s.ship_date) AS days_since_ship
FROM shipments s
WHERE s.delivered_date IS NULL         -- undelivered: lifecycle NULL
ORDER BY days_since_ship DESC;
```

In the second query, note that "undelivered" is best expressed as
`delivered_date IS NULL`; the corresponding statuses are any SHIP_STATUS label
other than delivered. Both framings should agree, but the delivered *label* and the
`delivered_date IS NOT NULL` condition are meant to move together — a delivered
shipment has a delivered date and a non-delivered one does not.

### Worked example — status mix of the current shipment book

A quick health picture of everything in flight: the distribution of shipments
across the SHIP_STATUS states. The *exception* and *lost* labels are the ones an
operations reader will want to see aged; the *out_for_delivery* label is imminent
delivery; *label_created* through *in_transit* are the pipeline. Decode the labels
at presentation via the **Code Dictionary**.

```sql
-- Distribution of shipments across their SHIP_STATUS states.
SELECT s.status,                    -- decode via SHIP_STATUS in the Code Dictionary
       COUNT(*)                    AS shipment_count,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM shipments), 2) AS pct_of_book
FROM shipments s
GROUP BY s.status
ORDER BY shipment_count DESC;
```

Read this together with `reference.md`, which lays out the legal
transitions between these states and confirms that the delivered and lost labels
are terminal.

### Split shipments — one order, many shipments

A 3PL routinely splits a single order into multiple shipments: part of the order
ships from one warehouse and part from another, or the fast-moving lines ship
immediately while a backordered line follows later. The schema supports this
directly — `shipments.order_id` is many-to-one, so an order can have any number of
shipment rows, each with its own carrier, service, origin warehouse, status, and
dates. Practical consequences you must design around:

- **"Was the order delivered on time" is not the same as "was the shipment
  delivered on time."** An order with a split shipment is only fully delivered when
  *all* its shipments are delivered, and it is arguably late if *any* shipment
  missed the order's promise. Decide, per question, whether the grain is the
  shipment or the order, and if it is the order, aggregate across its shipments
  (e.g. `MAX(delivered_date)` for the last piece to arrive). State the choice.
- **Ship-from can differ across an order's shipments.** Do not assume a single
  origin warehouse per order; read it per shipment.
- **Counting.** "How many shipments" and "how many orders shipped" are different
  numbers whenever splits exist; use `COUNT(*)` on shipments for the former and
  `COUNT(DISTINCT order_id)` for the latter.

### Worked example — orders that shipped in more than one shipment

```sql
-- Orders split across multiple shipments, with the span of ship dates.
SELECT s.order_id,
       COUNT(*)              AS shipment_count,
       MIN(s.ship_date)      AS first_ship_date,
       MAX(s.ship_date)      AS last_ship_date,
       COUNT(DISTINCT s.origin_warehouse_id) AS distinct_origins
FROM shipments s
GROUP BY s.order_id
HAVING COUNT(*) > 1
ORDER BY shipment_count DESC;
```

### Fan-out warning at the shipment level

Because one order can produce multiple shipments, joining `orders` to `shipments`
and then aggregating an order-level amount (say `orders.order_total`) will
double-count that amount once per shipment. If you need shipment counts per order,
aggregate; if you need order-level money, aggregate the shipments first or compute
the order amount independently. The general treatment of fan-out is in
`reference.md`; it recurs at every one-to-many boundary in this
domain (order→shipment, shipment→package, shipment→item, shipment→leg,
shipment→tracking event, shipment→exception).

### A note on the internal/test-order exclusion

Shipment analysis inherits an exclusion rule from the order side: orders flagged
with the internal/test priority in the **ORDER_PRIORITY** code set must be excluded
from all reporting (they carry no data signal and are not real customer demand).
Because shipments join back to orders, any customer-facing fulfillment metric —
on-time rate, volume, carrier spend attribution — should filter those orders out by
joining to `orders` and dropping the internal/test priority. The full rule, and the
list of what else to exclude, lives in `reference.md`; it is
called out here so that shipment-level rollups do not silently include test
traffic. The pattern is a simple `JOIN orders o ON o.order_id = s.order_id` plus a
`WHERE o.priority_code <> :order_priority_internal_test`, binding the ORDER_PRIORITY
internal/test value from the **Code Dictionary**.

---

## Table: packages

- **Columns:** package_id, shipment_id, packaging_type_code, weight_kg, length_cm, width_cm, height_cm
- **Joined by:** PK `package_id` (← `shipment_items.package_id`); FK `shipment_id` → `shipments.shipment_id`

A shipment is packed into one or more **packages**. `packages` holds the physical
parcels:

- `package_id` — primary key.
- `shipment_id` — the shipment this parcel belongs to. One shipment can have many
  packages (a multi-box shipment), so `shipments` → `packages` is one-to-many.
- `packaging_type_code` — the kind of parcel, from the **PACKAGING_TYPE** code set
  (labels: box, envelope, pallet, tube, crate).
- `weight_kg` — the parcel's weight in kilograms.
- `length_cm`, `width_cm`, `height_cm` — the parcel's dimensions in centimeters.

Two cautions:

- **Package weight vs shipment weight.** `packages.weight_kg` is the parcel weight;
  `shipments.weight_kg` is the shipment's total weight. Depending on how the data
  is captured these need not be identical, and in any case they are different
  grains. When someone asks for "shipment weight," use `shipments.weight_kg`; when
  they ask about parcel-level dimensions or per-parcel weight, use `packages`. Do
  not sum package weights and assume it equals the shipment weight unless the
  question specifically wants the packed total.
- **Fan-out.** Joining `shipments` to `packages` multiplies shipment rows by the
  number of packages. Count packages with an aggregate; do not, for example, count
  `shipment_id` rows after joining packages and expect a shipment count.

### Worked example — package mix and volumetric size

Volume from dimensions, and the packaging-type mix. `packaging_type_code` is
grouped and decoded to its PACKAGING_TYPE label at presentation via the **Code Dictionary**.

```sql
-- Package count and average volume by packaging type.
SELECT p.packaging_type_code,          -- decode via PACKAGING_TYPE in the Code Dictionary
       COUNT(*)                        AS package_count,
       ROUND(AVG(p.weight_kg), 2)      AS avg_weight_kg,
       ROUND(AVG(p.length_cm * p.width_cm * p.height_cm) / 1000.0, 1) AS avg_volume_liters
FROM packages p
GROUP BY p.packaging_type_code
ORDER BY package_count DESC;
```

(One liter is 1000 cubic centimeters, hence the `/ 1000.0`.)

---

## Table: shipment_items

- **Columns:** shipment_item_id, shipment_id, package_id, order_line_id, sku, quantity
- **Joined by:** PK `shipment_item_id`; FK `shipment_id` → `shipments.shipment_id`, `package_id` → `packages.package_id`, `order_line_id` → `order_lines.order_line_id`; `sku` (TEXT) → `products.sku` (order-side vocabulary — never joins to inventory-side `item_code`)

`shipment_items` records what was actually shipped, at the line level, and it is
the bridge from a shipment back to the order lines that were fulfilled. Columns:

- `shipment_item_id` — primary key.
- `shipment_id` — the shipment these units went out on.
- `package_id` — the specific parcel within the shipment that held these units.
  This is how you know which box a line item was packed in.
- `order_line_id` — the order line being fulfilled, pointing at `order_lines`. This
  is the tie back to demand: it lets you compare quantity ordered (on the order
  line) to quantity shipped (here).
- `sku` — the product identifier, **TEXT**, formatted `SKU-00042`. This is the
  **order-side** vocabulary. It matches `order_lines.sku` and `products.sku`.
- `quantity` — the number of units of that SKU shipped in that package for that
  order line.

### Identifier note — `sku` here, `item_code` on pick lines

`shipment_items` references product by **`sku`** (the order/shipping-side text
identifier). The warehouse pick detail (`pick_lines`, below) references the same
product by **`item_code`** (the inventory-side integer identifier equal to
`products.product_id`). These are two encodings of one product and they do not join
directly — `shipment_items.sku = pick_lines.item_code` returns zero rows without
error, because a text value never equals an integer. To relate shipped units to
picked units for the same product you must bridge through `products`
(`products.sku` ⇄ `products.product_id = item_code`). The full mechanics are in
`reference.md`; this is the same two-vocabulary rule that pervades the
warehouse.

### Fan-out — the double-counting warning

`shipment_items` is where quantity double-counting most often creeps in. A shipment
has many items; an order has many lines; a package has many items. Any time you
join `shipments` (or `orders`, or `packages`) to `shipment_items` and then sum or
count something from the *parent*, the parent value repeats once per item row.
Concretely:

- Summing `shipments.weight_kg` after joining `shipment_items` multiplies the
  shipment weight by the number of item rows — a large overcount.
- Counting `DISTINCT shipment_id` after the join is safe for a shipment count, but
  `COUNT(*)` counts item rows, not shipments.
- Summing `shipment_items.quantity` is the correct way to get "units shipped," and
  it is *not* double-counted, because quantity lives at the item grain.

Reference `reference.md` for the general fan-out treatment. The
rule of thumb: sum a measure only at its own grain, and use `COUNT(DISTINCT ...)`
or a pre-aggregated subquery when you need a parent-level count or amount across a
one-to-many join.

### Worked example — units shipped per SKU, and shipped vs ordered

```sql
-- Units shipped by SKU (quantity lives at item grain; safe to SUM directly).
SELECT si.sku,                                  -- order-side TEXT identifier
       SUM(si.quantity) AS units_shipped
FROM shipment_items si
GROUP BY si.sku
ORDER BY units_shipped DESC;
```

```sql
-- Per order line: ordered vs shipped, to find partially/over-shipped lines.
SELECT ol.order_line_id,
       ol.sku,
       ol.quantity                       AS qty_ordered,
       COALESCE(SUM(si.quantity), 0)     AS qty_shipped
FROM order_lines ol
LEFT JOIN shipment_items si ON si.order_line_id = ol.order_line_id
GROUP BY ol.order_line_id
HAVING qty_shipped <> qty_ordered        -- lines not shipped complete
ORDER BY (qty_ordered - qty_shipped) DESC;
```

The second query uses a `LEFT JOIN` so order lines with nothing shipped yet
(`qty_shipped = 0`) are retained, and aggregates the item quantities up to the
order-line grain before comparing — the correct way to avoid the item-level fan-out
distorting the ordered quantity.

---

## Table: shipment_legs

- **Columns:** leg_id, shipment_id, leg_seq, mode_code, from_facility_id, to_facility_id, status, departed_ts, arrived_ts
- **Joined by:** PK `leg_id`; FK `shipment_id` → `shipments.shipment_id`, `from_facility_id` → `facilities.facility_id`, `to_facility_id` → `facilities.facility_id`

A shipment's physical journey is decomposed into ordered **legs**. `shipment_legs`
holds one row per leg:

- `leg_id` — primary key.
- `shipment_id` — the shipment this leg belongs to. One shipment has one or more
  legs, ordered by `leg_seq`.
- `leg_seq` — the sequence number of the leg within the shipment (1, 2, 3, …). Use
  it to order the journey and to identify the first and last legs.
- `mode_code` — the transport mode for this leg, from the **TRANSPORT_MODE** code
  set (labels: truck, rail, air, ocean, parcel). A multi-leg journey commonly mixes
  modes — for example ocean to a port, truck to a hub, parcel for last mile.
- `from_facility_id`, `to_facility_id` — the origin and destination *facilities* of
  the leg, both pointing at `facilities`. Note again: facilities, not warehouses.
- `status` — the leg's state, from the **LEG_STATUS** code set (labels: pending,
  in_progress, completed, failed). **The leg's "done" state is the LEG_STATUS
  completed label — this is a different value in a different code set than the
  shipment's delivered state (SHIP_STATUS) or a pick's completed state
  (PICK_STATUS).** Never carry a status decode across tables; see
  `reference.md` and rule G2 in the overview.
- `departed_ts` — the timestamp the leg departed its origin (ISO-8601).
- `arrived_ts` — the timestamp the leg arrived at its destination, **NULL until the
  leg completes**. A leg in progress has a `departed_ts` but a NULL `arrived_ts`.

Because legs are sequenced, common patterns are: the origin of the whole journey is
the `from_facility_id` of the leg with the minimum `leg_seq`; the final destination
is the `to_facility_id` of the leg with the maximum `leg_seq`; the number of legs is
the count of rows per shipment; and "still moving" means the last leg's status is
not the completed label (or its `arrived_ts` is NULL).

### Worked example — journey shape per shipment

Number of legs, modes used, and whether the whole journey has completed.
Bind the LEG_STATUS completed value from the **Code Dictionary** for the filter.

```sql
-- Per-shipment journey summary.
SELECT sl.shipment_id,
       COUNT(*)                                        AS leg_count,
       MIN(sl.leg_seq)                                 AS first_seq,
       MAX(sl.leg_seq)                                 AS last_seq,
       SUM(CASE WHEN sl.status = :leg_status_completed THEN 1 ELSE 0 END) AS legs_completed,  -- LEG_STATUS completed
       SUM(CASE WHEN sl.arrived_ts IS NULL THEN 1 ELSE 0 END)                    AS legs_open
FROM shipment_legs sl
GROUP BY sl.shipment_id
ORDER BY leg_count DESC;
```

### Worked example — origin and final facility of each shipment

Use the min/max `leg_seq` to pull the endpoints of the whole journey.

```sql
-- First leg's origin facility and last leg's destination facility per shipment.
WITH bounds AS (
    SELECT shipment_id,
           MIN(leg_seq) AS min_seq,
           MAX(leg_seq) AS max_seq
    FROM shipment_legs
    GROUP BY shipment_id
)
SELECT b.shipment_id,
       f_first.code AS journey_origin_facility,
       f_last.code  AS journey_dest_facility
FROM bounds b
JOIN shipment_legs first_leg
     ON first_leg.shipment_id = b.shipment_id AND first_leg.leg_seq = b.min_seq
JOIN shipment_legs last_leg
     ON last_leg.shipment_id = b.shipment_id AND last_leg.leg_seq = b.max_seq
JOIN facilities f_first ON f_first.facility_id = first_leg.from_facility_id
JOIN facilities f_last  ON f_last.facility_id  = last_leg.to_facility_id
ORDER BY b.shipment_id;
```

---

## Table: tracking_events

- **Columns:** event_id, shipment_id, event_code, event_ts, facility_id, message
- **Joined by:** PK `event_id`; FK `shipment_id` → `shipments.shipment_id`, `facility_id` → `facilities.facility_id` (nullable)

`tracking_events` is an **append-only event stream**: one row per tracking scan or
milestone on a shipment, in the order it happened. It is the closest thing to a
narrative of what happened to a shipment. Columns:

- `event_id` — primary key.
- `shipment_id` — the shipment the event belongs to.
- `event_code` — the kind of event, from the **TRACK_EVENT** code set (labels:
  created, departed, arrived, customs_hold, delivered, delivery_failed,
  return_to_sender).
- `event_ts` — when the event occurred (ISO-8601). Order by this to reconstruct the
  timeline.
- `facility_id` — the facility where the event occurred, pointing at `facilities`,
  and **nullable**: some events (for example an in-transit scan not tied to a
  node) may not have a facility. Join to `facilities` with a `LEFT JOIN` if you
  want to keep facility-less events.
- `message` — a free-text human-readable description of the event.

Because the stream is append-only, you never `UPDATE` a shipment's history — you
read the events and derive state. Two important framing points:

- **The tracking stream is evidence, not the system of record for status.** The
  authoritative delivered state is `shipments.status` (SHIP_STATUS delivered
  label). The TRACK_EVENT delivered label is the *scan* that a delivery happened.
  In a clean world they agree, but when a question asks "is this delivered," answer
  from `shipments.status`; when it asks "when was the delivery scan," read the
  TRACK_EVENT delivered event's `event_ts`. Do not conflate a TRACK_EVENT label
  with a SHIP_STATUS label — they are different code sets even where the words look
  similar. Both happen to put "delivered" at the same integer (`5`), which makes them
  especially easy to conflate, but a `5` under TRACK_EVENT and a `5` under SHIP_STATUS
  are decodes from two separate sets; resolve each against its own column (see the
  **Code Dictionary**).
- **Latest event.** "Current tracking status" means the event with the maximum
  `event_ts` for the shipment. Use a window function or a correlated subquery to
  get it; do not assume the highest `event_id` is the latest, order by `event_ts`.

### Worked example — most recent tracking event per shipment

```sql
-- Latest tracking scan per shipment (by event timestamp).
WITH ranked AS (
    SELECT te.*,
           ROW_NUMBER() OVER (PARTITION BY te.shipment_id
                              ORDER BY te.event_ts DESC, te.event_id DESC) AS rn
    FROM tracking_events te
)
SELECT r.shipment_id,
       r.event_code,       -- decode via TRACK_EVENT in the Code Dictionary
       r.event_ts,
       r.facility_id,
       r.message
FROM ranked r
WHERE r.rn = 1
ORDER BY r.shipment_id;
```

The tie-breaker on `event_id` keeps the result deterministic when two events share
a timestamp.

### Worked example — shipments that hit a customs hold

Count shipments whose stream ever contained a customs-hold scan. Bind the
TRACK_EVENT customs_hold value from the **Code Dictionary** for the filter.

```sql
-- Distinct shipments that experienced at least one customs hold.
SELECT COUNT(DISTINCT te.shipment_id) AS shipments_with_customs_hold
FROM tracking_events te
WHERE te.event_code = :track_event_customs_hold;   -- bind the TRACK_EVENT customs_hold value from the Code Dictionary
```

`COUNT(DISTINCT shipment_id)` is essential — a shipment can have more than one
customs-hold event and you want to count shipments, not scans.

### Worked example — reconstruct a shipment's timeline

Because the stream is append-only and time-ordered, you reconstruct the full
narrative of a shipment simply by ordering its events. This is the query to run
when someone asks "what happened to shipment X." Substitute nothing here — the
decode of `event_code` happens at presentation via the **Code Dictionary**.

```sql
-- Full ordered event history for a single shipment, with elapsed time between scans.
SELECT te.event_ts,
       te.event_code,      -- decode via TRACK_EVENT in the Code Dictionary
       f.code AS facility_code,
       te.message,
       ROUND(
         (julianday(te.event_ts)
          - julianday(LAG(te.event_ts) OVER (ORDER BY te.event_ts, te.event_id))) * 24, 1)
         AS hours_since_prev
FROM tracking_events te
LEFT JOIN facilities f ON f.facility_id = te.facility_id
WHERE te.shipment_id = :shipment_id
ORDER BY te.event_ts, te.event_id;
```

The `LAG` window gives the gap between consecutive scans, which is how you spot a
shipment that sat idle at a facility. The `LEFT JOIN` to `facilities` preserves
events with a NULL `facility_id`.

### Worked example — delivery-scan timestamp vs the delivered date

The TRACK_EVENT delivered event carries the precise timestamp of the delivery scan,
while `shipments.delivered_date` is the delivery *date*. When you need the exact
scan time (for example to compute time-of-day delivery patterns), read it from the
stream; when you need the on-time comparison, use `shipments.delivered_date`
against `promised_date` as defined above. Bind the TRACK_EVENT delivered and
SHIP_STATUS delivered values from the **Code Dictionary** for the filters.

```sql
-- Delivery scan time from the stream, alongside the shipment's delivered_date.
SELECT s.shipment_id,
       s.delivered_date,
       te.event_ts AS delivery_scan_ts
FROM shipments s
JOIN tracking_events te
     ON te.shipment_id = s.shipment_id
    AND te.event_code = :track_event_delivered   -- TRACK_EVENT delivered
WHERE s.status = :ship_status_delivered   -- bind the SHIP_STATUS delivered value from the Code Dictionary
ORDER BY s.shipment_id;
```

If a shipment has more than one delivery scan (a rare data condition), this join
would return more than one row per shipment; guard with `MAX(te.event_ts)` in a
subquery when you need exactly one delivery time per shipment.

---

## Table: delivery_exceptions

- **Columns:** exception_id, shipment_id, exception_type_code, reported_ts, resolved_ts, note
- **Joined by:** PK `exception_id`; FK `shipment_id` → `shipments.shipment_id`

`delivery_exceptions` records problems reported against a shipment during its
journey. Columns:

- `exception_id` — primary key.
- `shipment_id` — the affected shipment. One shipment can have multiple exceptions.
- `exception_type_code` — the kind of problem, from the **EXCEPTION_TYPE** code set
  (labels: weather_delay, address_issue, damaged, missed_delivery, customs,
  mechanical).
- `reported_ts` — when the exception was reported (ISO-8601).
- `resolved_ts` — when it was resolved, **NULL while the exception is still open**.
  This is the open/closed signal: `resolved_ts IS NULL` means open,
  `resolved_ts IS NOT NULL` means resolved.
- `note` — free text.

Two relationships to keep straight:

- The **SHIP_STATUS exception label** on `shipments.status` marks a shipment
  *currently* sitting in an exception state; a row in `delivery_exceptions` records
  a *specific* problem event, which may since have been resolved. A shipment can
  have historical exception rows and still be delivered now. Use
  `delivery_exceptions` for "what went wrong and was it fixed"; use
  `shipments.status` for "what state is the shipment in now."
- **Open vs resolved is driven entirely by `resolved_ts` NULL-ness**, not by a
  status code. Do not look for a status; look at the timestamp.

### Worked example — open exceptions aging as of TODAY

```sql
-- Currently-open delivery exceptions, aged against TODAY = 2024-12-31.
SELECT de.exception_id,
       de.shipment_id,
       de.exception_type_code,     -- decode via EXCEPTION_TYPE in the Code Dictionary
       de.reported_ts,
       ROUND(julianday('2024-12-31') - julianday(de.reported_ts), 1) AS days_open
FROM delivery_exceptions de
WHERE de.resolved_ts IS NULL       -- open == unresolved
ORDER BY days_open DESC;
```

### Worked example — resolution time by exception type

For resolved exceptions only, average time to resolve, by type.

```sql
-- Average resolution time (hours) by exception type, resolved exceptions only.
SELECT de.exception_type_code,     -- decode via EXCEPTION_TYPE in the Code Dictionary
       COUNT(*) AS resolved_count,
       ROUND(AVG(julianday(de.resolved_ts) - julianday(de.reported_ts)) * 24, 1)
         AS avg_hours_to_resolve
FROM delivery_exceptions de
WHERE de.resolved_ts IS NOT NULL   -- exclude still-open ones from resolution time
GROUP BY de.exception_type_code
ORDER BY avg_hours_to_resolve DESC;
```

Excluding open exceptions (`resolved_ts IS NOT NULL`) is required: an open
exception has no resolution time, and `julianday(NULL)` would poison the average
with NULLs.

---

## Pick tasks and pick lines

Before a shipment can go out, the warehouse has to physically assemble the order.
That work is a **pick task**, decomposed into **pick lines**. Picking happens on
the inventory side of the house, which is why it uses the inventory-side product
vocabulary (`item_code`), not the order-side one (`sku`).

### Table: pick_tasks

- **Columns:** pick_id, warehouse_id, order_id, status_code, created_ts, completed_ts
- **Joined by:** PK `pick_id` (← `pick_lines.pick_id`); FK `warehouse_id` → `warehouses.warehouse_id`, `order_id` → `orders.order_id`

- `pick_id` — primary key.
- `warehouse_id` — the warehouse doing the picking, pointing at `warehouses` (the
  inventory domain — see `warehouse_and_inventory.md`).
- `order_id` — the order being assembled, pointing at `orders`. This is the link
  back to demand.
- `status_code` — the pick's state, from the **PICK_STATUS** code set (labels:
  queued, assigned, picking, completed, short). **A pick task's "done" state is the
  PICK_STATUS completed label — a different value in a different code set than the
  shipment delivered state (SHIP_STATUS) or the leg completed state (LEG_STATUS).**
  The *short* label means the pick could not be completed in full (insufficient
  stock at the bin). Never reuse a status decode across tables (rule G2, overview).
- `created_ts` — when the pick task was created (ISO-8601).
- `completed_ts` — when it finished, **NULL until the pick completes**.

### Table: pick_lines

- **Columns:** pick_line_id, pick_id, item_code, bin_id, quantity
- **Joined by:** PK `pick_line_id`; FK `pick_id` → `pick_tasks.pick_id`, `bin_id` → `bins.bin_id` (nullable); `item_code` (INTEGER) → `products.product_id` (inventory-side vocabulary — never joins to order-side `sku`)

- `pick_line_id` — primary key.
- `pick_id` — the pick task this line belongs to.
- `item_code` — the product picked, **INTEGER**, equal to `products.product_id`.
  This is the **inventory-side** vocabulary — the same product that
  `shipment_items` calls by `sku`. See the identifier note below.
- `bin_id` — the bin the units were picked from, pointing at `bins`, and
  **nullable** (a pick line may not always record a specific bin).
- `quantity` — units picked on the line.

### Identifier note — `item_code` here, `sku` on shipment items

This is the mirror image of the shipment-items note above, and it is the classic
zero-row pitfall in this domain. `pick_lines` uses **`item_code`** (integer,
inventory-side); `shipment_items` uses **`sku`** (text, order-side). To relate what
was picked to what was shipped for the same product, bridge through `products`:
`pick_lines.item_code = products.product_id` and `products.sku =
shipment_items.sku`. A direct `pick_lines.item_code = shipment_items.sku`
comparison returns zero rows without error. Full treatment in
`reference.md`.

### Worked example — pick throughput and short picks by warehouse

Bind the PICK_STATUS completed and short values from the **Code Dictionary** for the filters.

```sql
-- Pick task outcomes by warehouse.
SELECT w.code AS warehouse_code,
       COUNT(*) AS pick_tasks,
       SUM(CASE WHEN pt.status_code = :pick_status_completed THEN 1 ELSE 0 END) AS completed,     -- PICK_STATUS completed
       SUM(CASE WHEN pt.status_code = :pick_status_short THEN 1 ELSE 0 END)      AS short_picks,   -- PICK_STATUS short
       ROUND(AVG(CASE WHEN pt.completed_ts IS NOT NULL
                      THEN (julianday(pt.completed_ts) - julianday(pt.created_ts)) * 24
                 END), 1) AS avg_hours_to_complete
FROM pick_tasks pt
JOIN warehouses w ON w.warehouse_id = pt.warehouse_id
GROUP BY pt.warehouse_id
ORDER BY pick_tasks DESC;
```

The `CASE` inside `AVG` restricts the cycle-time average to picks that actually
completed (a NULL `completed_ts` yields NULL and is ignored by `AVG`).

### Worked example — picked units for a product across warehouses

To roll picked units up by product *using the order-side SKU*, bridge through
`products`.

```sql
-- Units picked per product, resolved to its SKU via the products bridge.
SELECT p.sku,
       p.name,
       SUM(pl.quantity) AS units_picked
FROM pick_lines pl
JOIN products p ON p.product_id = pl.item_code   -- item_code == product_id
GROUP BY p.product_id
ORDER BY units_picked DESC;
```

### Pick and shipment are parallel, not chained

Both `pick_tasks` and `shipments` reference `order_id`, but the schema does not
carry a direct key between a pick task and the shipment it fed. They are two
children of the same order, not a chain. To relate the two, join each to the order
independently. Be careful: an order can have several picks *and* several shipments,
so a naive `pick_tasks` × `shipments` join on `order_id` produces the cross-product
of picks and shipments for that order — a fan-out on both sides at once. When you
genuinely need pick-and-ship together for an order, aggregate each side to the
order grain first, then join the two summaries, exactly as in the scorecard pattern
at the end of this document.

### Worked example — orders picked but not yet shipped as of TODAY

A useful operational backlog view. An order whose picks have completed but which
has no shipment yet is work waiting to be tendered. Bind the PICK_STATUS completed
value from the **Code Dictionary** for the filter.

```sql
-- Orders with a completed pick but no shipment (assembled, awaiting dispatch).
SELECT DISTINCT pt.order_id
FROM pick_tasks pt
WHERE pt.status_code = :pick_status_completed   -- bind the PICK_STATUS completed value from the Code Dictionary
  AND NOT EXISTS (
        SELECT 1 FROM shipments s WHERE s.order_id = pt.order_id
      )
ORDER BY pt.order_id;
```

The `NOT EXISTS` anti-join is the clean way to express "has no shipment"; it avoids
the fan-out that a `LEFT JOIN … WHERE s.shipment_id IS NULL` can introduce when
there are multiple picks, and it reads as the business rule states it.

---

## Returns and return lines

The reverse flow. After delivery a customer may send goods back; that is a
**return**, identified by an RMA, decomposed into **return lines**.

### Table: returns

- **Columns:** return_id, order_id, rma_number, reason_code, status, disposition_code, requested_date, received_date
- **Joined by:** PK `return_id` (← `return_lines.return_id`); FK `order_id` → `orders.order_id`

- `return_id` — primary key.
- `order_id` — the order the return is against, pointing at `orders`.
- `rma_number` — the Return Merchandise Authorization number, a unique business
  identifier for the return. Use `rma_number` to reference a return in reports; use
  `return_id` to join.
- `reason_code` — why the customer is returning, from the **RETURN_REASON** code set
  (labels: defective, wrong_item, no_longer_needed, damaged_in_transit,
  late_delivery).
- `status` — the return's state, from the **RETURN_STATUS** code set (labels:
  requested, authorized, received, refunded, rejected). **The return's "received"
  state is the RETURN_STATUS received label — its own value in its own code set,
  not the shipment delivered, leg completed, or pick completed values.** Note also
  that this is the `returns.status` column, which is the RETURN_STATUS set — do not
  confuse it with `orders.status` (ORDER_STATUS), whose *returned* label is a
  different thing at the order level. See `reference.md`.
- `disposition_code` — what we decided to do with the returned goods, from the
  **RETURN_DISPOSITION** code set (labels: restock, refurbish, scrap,
  return_to_supplier). **Nullable**: disposition is NULL until it has been decided,
  which typically only happens once the goods are physically received. A NULL
  disposition is a lifecycle signal ("not yet dispositioned"), not missing data.
- `requested_date` — when the return was requested (`YYYY-MM-DD`).
- `received_date` — when the goods were received back, **NULL until received**.

The two-timestamp / two-status structure lets you distinguish the phases: a return
can be requested and authorized but not yet physically back (`received_date` NULL,
`disposition_code` NULL), or received and dispositioned. The RETURN_STATUS *refunded*
label indicates the financial resolution; the money detail is out of scope here and
lives in `reference.md`.

### Table: return_lines

- **Columns:** return_line_id, return_id, sku, quantity, condition_code
- **Joined by:** PK `return_line_id`; FK `return_id` → `returns.return_id`; `sku` (TEXT) → `products.sku` (order-side vocabulary)

- `return_line_id` — primary key.
- `return_id` — the return this line belongs to.
- `sku` — the product being returned, **TEXT**, order-side vocabulary (matches
  `order_lines.sku` / `products.sku`). Returns are on the order/shipping side, so
  like `order_lines` and `shipment_items` they use `sku`, **not** `item_code`.
- `quantity` — units returned on the line.
- `condition_code` — the condition of the returned unit, from the **ITEM_CONDITION**
  code set (labels: new, opened, damaged, defective), and **nullable** (condition
  may be unrecorded until inspection). This condition drives the eventual
  disposition decision but is captured per line.

### Worked example — return rate reasons and open returns

"Open" here is expressed by the lifecycle NULLs (`received_date`,
`disposition_code`) rather than a status filter, so no code value is bound.
`reason_code` is grouped and decoded to its RETURN_REASON label at presentation
via the **Code Dictionary**.

```sql
-- Return volume by reason, and how many are still open (not yet received).
SELECT r.reason_code,                 -- decode via RETURN_REASON in the Code Dictionary
       COUNT(*) AS returns_count,
       SUM(CASE WHEN r.received_date IS NULL THEN 1 ELSE 0 END) AS not_yet_received,
       SUM(CASE WHEN r.disposition_code IS NULL THEN 1 ELSE 0 END) AS not_yet_dispositioned
FROM returns r
GROUP BY r.reason_code
ORDER BY returns_count DESC;
```

### Worked example — returned units by condition

Join `returns` to `return_lines` to slice returned quantity by item condition.
`condition_code` is grouped and decoded to its ITEM_CONDITION label at presentation
via the **Code Dictionary**.

```sql
-- Returned units by condition, for returns physically received.
SELECT rl.condition_code,             -- decode via ITEM_CONDITION in the Code Dictionary
       SUM(rl.quantity) AS units_returned
FROM return_lines rl
JOIN returns r ON r.return_id = rl.return_id
WHERE r.received_date IS NOT NULL     -- only goods actually back in our hands
GROUP BY rl.condition_code
ORDER BY units_returned DESC;
```

Watch the fan-out here just as with shipment items: a return has many lines, so
counting returns after joining `return_lines` needs `COUNT(DISTINCT return_id)`,
while `SUM(rl.quantity)` at the line grain is safe.

### Worked example — relate a return to the order it came from

Because `returns.order_id` points straight at `orders`, tying returns back to the
originating order (and thence to the customer) is a direct join. To compare
returned SKUs against what was ordered, bridge on `sku` — both sides are order-side
text identifiers, so this join is direct (no `products` bridge needed).

```sql
-- Returned lines matched to the order lines they came from, same SKU vocabulary.
SELECT r.rma_number,
       r.order_id,
       rl.sku,
       rl.quantity AS qty_returned,
       ol.quantity AS qty_ordered
FROM returns r
JOIN return_lines rl ON rl.return_id = r.return_id
JOIN order_lines ol  ON ol.order_id = r.order_id AND ol.sku = rl.sku
ORDER BY r.order_id, rl.sku;
```

Note this join is between two order-side tables, so `sku = sku` is correct and
direct. The moment either side were an inventory-side table (`pick_lines`,
`inventory`, …), you would have to bridge through `products` instead — that is the
whole point of the two-vocabulary rule.

---

## Table: carrier_invoices

- **Columns:** carrier_invoice_id, carrier_id, invoice_number, amount, status_code, invoice_date, due_date, paid_date
- **Joined by:** PK `carrier_invoice_id`; FK `carrier_id` → `carriers.carrier_id`

`carrier_invoices` records what carriers bill us for freight. It sits in this
domain because it is carrier-facing, but the *money mechanics* — how to sum spend,
reconcile invoices, and treat statuses financially — live in
`reference.md`. Here we cover only the shape and its status
vocabulary.

Columns:

- `carrier_invoice_id` — primary key.
- `carrier_id` — the billing carrier, pointing at `carriers`.
- `invoice_number` — the carrier's unique invoice identifier.
- `amount` — the invoiced amount in USD.
- `status_code` — the invoice's state, from the **INVOICE_STATUS** code set (labels:
  draft, submitted, approved, paid, disputed). Note that carrier invoices and
  supplier invoices *share* the INVOICE_STATUS code set — the same labels mean the
  same things on both — but that is the exception, not the rule; do not generalize
  it to the other `status` columns, which each have their own set (G2, overview).
- `invoice_date` — when the invoice was issued (`YYYY-MM-DD`).
- `due_date` — when payment is due.
- `paid_date` — when we paid, **NULL until paid**. Unpaid is `paid_date IS NULL`,
  and the INVOICE_STATUS paid label should move together with a non-NULL
  `paid_date`.

An important modeling point: `carrier_invoices` is at the **carrier** grain (an
invoice references a carrier, not a specific shipment). There is no foreign key
from an invoice to a shipment in this schema, so you cannot attribute a carrier
invoice to an individual shipment through a stored key. Freight cost analysis is
therefore done at the carrier (and period) level, or by allocation logic defined in
`reference.md` — do not invent a shipment↔invoice join that the
schema does not provide.

### Worked example — outstanding carrier invoices as of TODAY

A topical example only; see `reference.md` for the full billing
treatment. Unpaid is expressed by the `paid_date IS NULL` lifecycle NULL rather
than a status filter; `status_code` is decoded to its INVOICE_STATUS label at
presentation via the **Code Dictionary**.

```sql
-- Unpaid carrier invoices, flagged overdue as of TODAY = 2024-12-31.
SELECT c.name AS carrier_name,
       ci.invoice_number,
       ci.amount,
       ci.status_code,                  -- decode via INVOICE_STATUS in the Code Dictionary
       ci.due_date,
       CASE WHEN ci.due_date < '2024-12-31' THEN 1 ELSE 0 END AS is_overdue
FROM carrier_invoices ci
JOIN carriers c ON c.carrier_id = ci.carrier_id
WHERE ci.paid_date IS NULL              -- unpaid == no payment date
ORDER BY ci.due_date;
```

---

## Putting the domain together — a cross-cutting example

A realistic fulfillment question usually walks several of these tables at once.
Here is a shipment-level report that pulls the carrier, the service level, the
origin warehouse, the on-time outcome, the package count, and the units shipped —
carefully avoiding the fan-out traps by pre-aggregating the one-to-many children
before joining them to the shipment.

```sql
-- Shipment scorecard: one row per shipment, children pre-aggregated to avoid fan-out.
WITH pkg AS (
    SELECT shipment_id, COUNT(*) AS package_count
    FROM packages
    GROUP BY shipment_id
),
units AS (
    SELECT shipment_id, SUM(quantity) AS units_shipped
    FROM shipment_items
    GROUP BY shipment_id
)
SELECT s.shipment_id,
       s.order_id,
       c.name                    AS carrier_name,
       cs.service_level_code,     -- decode via SERVICE_LEVEL in the Code Dictionary
       w.code                    AS origin_warehouse,
       s.status,                  -- decode via SHIP_STATUS in the Code Dictionary
       s.ship_date,
       s.promised_date,
       s.delivered_date,
       CASE
         WHEN s.status <> :ship_status_delivered   THEN 'undelivered'  -- SHIP_STATUS delivered
         WHEN s.delivered_date <= s.promised_date  THEN 'on_time'
         ELSE 'late'
       END                       AS delivery_outcome,
       COALESCE(pkg.package_count, 0) AS package_count,
       COALESCE(units.units_shipped, 0) AS units_shipped
FROM shipments s
JOIN carriers c          ON c.carrier_id = s.carrier_id
JOIN carrier_services cs ON cs.service_id = s.service_id
JOIN warehouses w        ON w.warehouse_id = s.origin_warehouse_id
LEFT JOIN pkg   ON pkg.shipment_id = s.shipment_id
LEFT JOIN units ON units.shipment_id = s.shipment_id
ORDER BY s.shipment_id;
```

The pattern is the general antidote to fan-out: aggregate each one-to-many child
(`packages`, `shipment_items`) to the shipment grain in its own CTE, then `LEFT
JOIN` the pre-aggregated result. That keeps the output at exactly one row per
shipment and prevents package count and unit count from multiplying each other.
The `delivery_outcome` `CASE` encodes the on-time rule precisely: gate on the
SHIP_STATUS delivered label first, then compare `delivered_date` to
`promised_date`.

---

## Quick reference — code sets used in this domain

Every coded column below is decoded (integer → label) in `reference.md`.
This document only names the set and uses labels.

- `carrier_services.service_level_code` → **SERVICE_LEVEL** (ground, two_day,
  overnight, economy, freight).
- `facilities.facility_type_code` → **FACILITY_TYPE** (origin_dc, hub, cross_dock,
  last_mile_depot, port).
- `shipments.status` → **SHIP_STATUS** (label_created, picked_up, in_transit,
  out_for_delivery, delivered, exception, lost). Delivered is the terminal success
  state and the gate for on-time.
- `packages.packaging_type_code` → **PACKAGING_TYPE** (box, envelope, pallet, tube,
  crate).
- `shipment_legs.mode_code` and `route_lanes.mode_code` → **TRANSPORT_MODE** (truck,
  rail, air, ocean, parcel).
- `shipment_legs.status` → **LEG_STATUS** (pending, in_progress, completed, failed).
  Completed is the leg's done state — not the same value as SHIP_STATUS delivered.
- `tracking_events.event_code` → **TRACK_EVENT** (created, departed, arrived,
  customs_hold, delivered, delivery_failed, return_to_sender).
- `delivery_exceptions.exception_type_code` → **EXCEPTION_TYPE** (weather_delay,
  address_issue, damaged, missed_delivery, customs, mechanical).
- `pick_tasks.status_code` → **PICK_STATUS** (queued, assigned, picking, completed,
  short). Completed is the pick's done state — not the same value as SHIP_STATUS
  delivered or LEG_STATUS completed.
- `returns.reason_code` → **RETURN_REASON** (defective, wrong_item, no_longer_needed,
  damaged_in_transit, late_delivery).
- `returns.status` → **RETURN_STATUS** (requested, authorized, received, refunded,
  rejected).
- `returns.disposition_code` → **RETURN_DISPOSITION** (restock, refurbish, scrap,
  return_to_supplier); nullable until decided.
- `return_lines.condition_code` → **ITEM_CONDITION** (new, opened, damaged,
  defective); nullable until inspected.
- `carrier_invoices.status_code` → **INVOICE_STATUS** (draft, submitted, approved,
  paid, disputed); shared with supplier invoices, but do not generalize sharing to
  other status columns.

## Quick reference — identifier vocabularies in this domain

- **Order/shipping side uses `sku` (TEXT, `SKU-00042`):** `shipment_items.sku`,
  `return_lines.sku`. These match `order_lines.sku` and `products.sku` directly.
- **Inventory side uses `item_code` (INTEGER = `products.product_id`):**
  `pick_lines.item_code`. This matches inventory-side tables and
  `products.product_id` directly.
- **The two never join directly.** `shipment_items.sku = pick_lines.item_code`
  returns zero rows with no error. Bridge through `products`. Full mechanics:
  `reference.md`.

## Quick reference — the NULL lifecycle signals in this domain

- `shipments.delivered_date` NULL → not yet delivered.
- `shipment_legs.arrived_ts` NULL → leg not yet completed.
- `tracking_events.facility_id` NULL → event not tied to a facility node.
- `delivery_exceptions.resolved_ts` NULL → exception still open.
- `pick_tasks.completed_ts` NULL → pick not yet complete.
- `pick_lines.bin_id` NULL → bin not recorded on the line.
- `returns.received_date` NULL → goods not yet received back.
- `returns.disposition_code` NULL → disposition not yet decided.
- `return_lines.condition_code` NULL → condition not yet inspected.
- `carrier_invoices.paid_date` NULL → invoice unpaid.

Because these NULLs are meaningful, always test them with `IS NULL` / `IS NOT
NULL`; inequality and `<>` comparisons silently drop NULL rows and will
misclassify undelivered, open, or unpaid records. For the canonical metric
definitions that build on these rules — on-time delivery rate, days-to-deliver,
fill/ship completeness — see `reference.md`; for the exclusion
rules (for example, internal/test orders that must be dropped from all reporting)
and broader NULL guidance, see `reference.md`; and for the
warehouse/inventory side of picks and stock, see `warehouse_and_inventory.md`.
```