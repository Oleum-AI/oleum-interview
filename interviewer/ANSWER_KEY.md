# Part 2 — answer key (INTERVIEWER ONLY)

Gold answers for `docs/part2/QUESTIONS.md`. Numbers computed against `data.db`
(seed=42, TODAY 2024-12-31). Do NOT ship this file — the whole `interviewer/`
dir is gitignored and is not in the delivered git history.

**The point of this set.** None of these questions can be answered from the schema
alone, and none has a lucky-guess answer. Each hinges on a **guidance-only
convention** or a **join the data does not hand you**. An agent with no guidance
retrieval will *burn turns* probing the data, form a plausible-but-wrong number,
and submit it; an agent that retrieves the right guidance collapses each to one or
two queries. We are grading the retrieval design and the reasoning, not just the
final integer.

Trap legend:
- **X-EXCL** the internal-test exclusion (`priority_code = internal_test`, ~3% of
  orders, invisible in the data) + the cancelled/draft revenue exclusions.
- **X-STATUS (G2)** `status` is a *different* code set per table; the "done" integer
  differs (order fulfilled = 4, shipment delivered = 5, …).
- **X-BRIDGE (G1)** sell side uses `sku` (TEXT, `SKU-00042`), stock side uses
  `item_code` (INTEGER, `42`); the only bridge is `products`. A direct
  `sku = item_code` join returns **zero rows, no error**.
- **X-ACTIVE** `is_active` selects the *current operational* set; it is guidance-only
  and invisible unless you read §2.6.
- **X-LEDGER** `inventory_transactions` is a signed movement ledger; outbound =
  INV_TXN_TYPE `shipment`, deltas are negative (use `ABS`), window is measured
  against fixed TODAY = 2024-12-31, not `date('now')`.
- **X-NET / X-FANOUT / X-NULL** returns netting, header-vs-line grain fan-out, and
  NULL-as-lifecycle-signal conventions.

---

## 1. Total recognized revenue for 2024

- **Answer: $10,382,697.48** (8,723 reportable orders)
- **Convention:** sum `order_total` over 2024 orders that are **not** internal-test
  priority, **not** cancelled, **not** draft; **returned orders stay in** (the sale
  happened — netting is a separate metric, see Q2).
- **Pitfalls:** X-EXCL. None of the three exclusions is visible in the data —
  internal-test orders look like normal orders.
- **Wrong answers:**
  - **$11,917,426.93** — every 2024 order, no exclusions (the number a context-free
    agent lands on).
  - **$10,961,799.55** — excluded cancelled only, left internal-test + draft in.
  - Restricting to `fulfilled` only is a defensible *alternate* finance convention
    (recognize at fulfillment) — accept it **only if the candidate states it**; the
    house definition is the committed-demand population above.

## 2. Net revenue after returns for 2024

- **Answer: $9,934,476.10**  (gross recognized $10,382,697.48 − returned value
  $448,221.38)
- **Convention (§20):** net = gross recognized revenue **minus** the value of
  realized returns. Value returned units at the line's sale price
  (`return_lines.quantity × order_lines.unit_price`, matched on `order_id`+`sku`).
  Count only **realized** returns (RETURN_STATUS `received`/`refunded`), and exclude
  internal-test. Aggregate gross and returned value as **separate** CTEs and
  subtract at the end.
- **Pitfalls:** X-NET, X-FANOUT, X-STATUS (RETURN_STATUS, not order status).
- **Wrong answers:**
  - **~$9,563,577.32** — "net" approximated by *dropping* returned orders from
    gross. This is the canonical wrong approach and it under-counts by ~$371k
    (a returned order is usually only partially returned).
  - **$10,382,697.48** — ignored returns entirely (= gross).
  - Netting *requested/rejected* RMAs, or fanning returns × order-lines into one sum.

## 3. Order fill rate (order fulfillment rate)

- **Answer: 77.6%**  (13,533 fulfilled ÷ 17,446 eligible)
- **Convention (§6):** fulfilled orders ÷ **eligible** orders, where eligible =
  real committed demand: not internal-test, not draft, not cancelled. Fulfilled =
  ORDER_STATUS `fulfilled`.
- **Pitfalls:** X-EXCL in the *denominator*, plus "fill rate" is genuinely
  ambiguous — there is also a **unit-level** fill rate (units shipped ÷ units
  ordered, §21/§14). The candidate should pick the order-level definition or state
  which they used.
- **Wrong answers:**
  - **69.9%** — fulfilled ÷ **all** orders (draft/cancelled/internal-test left in
    the denominator).
  - A unit-level number reported without saying so.

## 4. Of delivered shipments, what percentage were delivered on time?

- **Answer: 71.7% on-time**  (equivalently **28.3% late** — 4,142 late of 14,628
  graded delivered shipments)
- **Convention (§3):** among shipments in SHIP_STATUS `delivered`, on-time =
  `delivered_date <= promised_date`. Require a promised date; exclude shipments of
  internal-test orders (join to `orders`).
- **Pitfalls:** X-STATUS (G2) — "delivered" is **SHIP_STATUS = 5**, not the order
  `fulfilled` code. X-EXCL — 470 delivered shipments belong to internal-test orders
  and must be dropped. (The NULL-promise carve-out is real in general but doesn't
  bite here: all delivered shipments carry a promise.)
- **Wrong answers:**
  - Reusing the **orders** status decode against `shipments.status` — filtering
    `status = 4` selects `out_for_delivery` (308 rows), an entirely wrong
    population. A candidate who does this and doesn't notice the tiny count fell in.
  - Grading over **all 15,098** delivered shipments (internal-test included) instead
    of the 14,628 reportable ones.

## 5. Distribution center with the most items below reorder point

- **Answer: Northeast DC, with 83 items.**
- **Convention (§7 + §2.6):** below reorder = `quantity_on_hand < reorder_point`
  (strict `<`). This is a *current-state* question, so restrict to the **active
  operational set**: `products.is_active = 1` **and** `warehouses.is_active = 1`.
- **Pitfalls:** X-ACTIVE. **Central DC is inactive** (`is_active = 0`) and must be
  dropped even though it has 67 below-reorder positions. Using `<=` instead of `<`
  also inflates every count.
- **Wrong answers:**
  - **Northeast DC, 93** — used `<=` and skipped the `is_active` filters.
  - Reporting **Central DC** at all (it is retired) — the tell that `is_active` was
    ignored.
- Gold ranking (active set): Northeast 83, East 73, Southeast 73, Midwest 71,
  Northwest 69, Southwest 69, West 69.

## 6. Distinct ordered products currently below reorder in ≥1 warehouse

- **Answer: 354**
- **Convention:** order lines identify a product by `sku` (TEXT); inventory by
  `item_code` (INTEGER = `product_id`). Bridge through `products`, then apply the
  below-reorder test.
- **Pitfalls:** X-BRIDGE (G1). This is the headline cross-domain trap.
- **Wrong answers:**
  - **0** — joining `order_lines.sku = inventory.item_code` directly. Text never
    equals integer, so the join returns **zero rows with no error**. A candidate who
    reports "0" and never questions an empty join is the classic failure; the tell is
    that they trusted a silently-empty result.

## 7. Active inventory positions with zero outbound movement in the trailing 90 days

- **Answer: 676 positions** (of 2,815 active product × active warehouse positions)
- **Convention (§8 + §3.5 + §2.6):** a "position" is one `(warehouse, item_code)`
  row in `inventory`. Outbound movement = `inventory_transactions` rows of
  INV_TXN_TYPE `shipment`. The 90-day window is measured against **TODAY =
  2024-12-31** (`date('2024-12-31','-90 days')`), not `date('now')`. Restrict to the
  active operational set. Count positions with **no** such movement.
- **Pitfalls:** X-LEDGER + X-ACTIVE, and the join trap is inverted: an **inner join**
  from positions to the ledger *drops exactly the zero-movement rows you are trying
  to count*. The correct shape is `NOT EXISTS` / `LEFT JOIN … IS NULL`.
- **Wrong answers:**
  - Any positive-movement count (e.g. **542** distinct products *with* outbound) —
    the inner-join inversion, i.e. they counted the opposite set.
  - Using `date('now')` (returns a real current date → empty window → wrong).
  - Filtering outbound by a *status* code instead of INV_TXN_TYPE `shipment`, or
    forgetting `is_active`.

## 8. Avg days order-placed → delivered, for fulfilled orders (excl. internal/test)

- **Answer: 7.0 days**  (over 13,280 fulfilled orders with a delivered shipment)
- **Convention (§5):** per order, take the **first** shipment's `delivered_date`
  (`MIN`), measure `delivered_date − order_date` in days, average. Exclude
  internal-test. Fulfilled = ORDER_STATUS `fulfilled`; delivered date comes from
  `shipments`.
- **Pitfalls:** X-STATUS (G2) in one query — `fulfilled` is an **order** code while
  the delivery timestamp lives on **shipments** (SHIP_STATUS world); X-NULL —
  undelivered shipments have NULL `delivered_date` and must not count as 0-day
  deliveries; X-EXCL.
- **Wrong answers:**
  - Reusing one status decode across both tables.
  - Letting NULL `delivered_date` rows enter the average (or counting them as 0).
  - Using every shipment instead of the first per order (fan-out).

## 9. Active enterprise customers with ≥1 reportable order in 2024

- **Answer: 253**
- **Convention:** CUSTOMER_SEGMENT `enterprise` **and** `customers.is_active = 1`,
  **and** the customer has at least one 2024 order in the reportable population (not
  internal-test, not cancelled, not draft). Count **distinct customers**.
- **Pitfalls:** the segment decode is necessary but **not sufficient** — X-ACTIVE +
  X-EXCL + a distinct-customer join all layer on top. A correct decode alone still
  gives a wrong number.
- **Wrong answers:**
  - **294** — all enterprise customers (no `is_active`, no order requirement).
  - **265** — active enterprise customers, but not restricted to those who actually
    placed a reportable 2024 order.

## 10. Recognized revenue by month for 2024 (twelve totals)

- **Answer** (sums to $10,382,697.48):

  | month | revenue | month | revenue |
  |---|---|---|---|
  | 2024-01 | 771,092.67 | 2024-07 | 869,626.89 |
  | 2024-02 | 859,201.34 | 2024-08 | 929,663.35 |
  | 2024-03 | 962,505.04 | 2024-09 | 907,900.13 |
  | 2024-04 | 873,009.29 | 2024-10 | 830,656.92 |
  | 2024-05 | 819,961.08 | 2024-11 | 777,769.67 |
  | 2024-06 | 898,773.92 | 2024-12 | 882,537.18 |

- **Convention:** the same recognized-revenue population as Q1, grouped by
  `strftime('%Y-%m', order_date)`.
- **Pitfalls:** X-EXCL applied consistently across all twelve months.
- **Wrong answers:** monthly totals that do not reconcile to the Q1 gold — the tell
  that the exclusions were applied inconsistently (or not at all).

---

## What each question is really probing (turn-burn map)

- **Q1, Q2, Q3, Q9, Q10** — the headline reporting conventions (internal-test +
  draft/cancelled exclusions, gross-vs-net, eligible population). Not deducible from
  the data; only guidance reveals them. A context-free agent burns turns hunting for
  a definition that isn't in any table, then guesses. **Prime discriminators.**
- **Q4, Q8** — per-table status decode (G2): does the agent re-derive the right code
  set for `shipments`/`orders` instead of reusing one decode everywhere?
- **Q6, Q7** — cross-domain joins the data won't hand you: G1's silent-zero bridge
  (Q6) and the inverted inner-join / ledger-sign / fixed-clock trap (Q7). Does the
  agent *verify* a join returned the rows it should?
- **Q5** — the `is_active` current-set convention, and noticing a retired DC.
- **The retrieval test:** with a guidance-search/-read tool wired in, each of these
  is one or two queries. Without it, watch the trace burn probes and reason in
  circles — that gap is the signal.
