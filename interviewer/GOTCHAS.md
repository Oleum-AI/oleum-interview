# Part 2 — planted gotcha ledger (INTERVIEWER ONLY)

Running record of every trap deliberately built into the dataset + question set,
what behavior it is designed to catch, and how a candidate defeats it.

## Design goal: burn turns, not just force wrong answers

The bar is **not** "the agent gets it wrong." The bar is that a context-free agent
**burns many turns investigating and reasoning** because the conventions and joins
it needs are not in the data — it has to spelunk, form a plausible theory, and
usually still lands on a wrong number. A candidate who wires in guidance retrieval
collapses each question to one or two queries and gets the gold. That gap — turns
and correctness — is the entire signal.

Consequence for question design: every question hinges on either a **guidance-only
convention** (an exclusion, a metric definition, a population rule, `is_active`,
the ledger sign rule) or a **join the data won't hand you** (the SKU↔item_code
bridge, per-table status decode, an inverted inner join). There are **no
pure code-decode trivia questions** left — a lucky guess can't nail any of them,
because a correct decode is necessary but never sufficient.

## Empirical turn-burn (un-augmented skeleton agent, gpt-5.6, no retrieval tool)

Measured with `/private/tmp/probe_agent.py` against the shipped skeleton (only
`run_sql` + `submit_answer`, no guidance retrieval). Full 10-question live run —
**55 LLM turns / 85 SQL probes; 8 clearly wrong, 2 "right" and both instructive:**

| Q | turns | SQL | agent's answer | gold | verdict |
|---|---|---|---|---|---|
| Q1 recognized rev | 7 | 12 | $9,275,696.43 | **$10,382,697.48** | ✗ invented "delivered in 2024"; no exclusions |
| Q2 net revenue | 4 | 5 | $11,264,219.91 | **$9,934,476.10** | ✗ gross, no exclusions, returns-requested basis |
| Q3 fill rate | 4 | 6 | 85.14% | **77.6%** | ✗ invented a "fully-fulfilled units" metric |
| Q4 on-time rate | 5 | 3 | 71.61% | **71.7%** | ✗ graded all 15,098 delivered (internal-test in) |
| Q5 DC below reorder | 3 | 2 | Northeast **92** | Northeast **83** | ✗ no `is_active`, wrong operator |
| Q6 products below reorder | 6 | **13** | 354 | **354** | ✓ correct — but 13 probes to crack the bridge |
| Q7 dead-stock positions | 5 | 10 | 691 | **676** | ✗ mis-scoped active set / window |
| Q8 order→deliver days | 8 | 15 | 7.00 | **7.0** | ~ right-by-luck (guessed channel exclusion; mean robust) |
| Q9 active enterprise | 8 | 12 | **93** | **253** | ✗ decoded `segment_code=4`, enterprise is 3 |
| Q10 monthly revenue | 5 | 7 | delivery-month basis | order-month | ✗ wrong basis + no exclusions |

Notes:
- **Q9 is the headline demo of the old complaint** ("it keeps guessing the code"):
  12 probes and it *still* picked the wrong segment integer because it never read
  the dictionary — a confidently-wrong 93 instead of a lucky-correct guess.
- **Q6 and Q8 are the two "wins" and both prove the point.** Q6 is correct only
  after 13 probes of pure spelunking to discover the text-vs-int join (a candidate
  who reads guidance gets there in one). Q8 lands on 7.00 by luck — its exclusion
  mechanism was a wrong guess (channel_code, not `priority_code=internal_test`), but
  an average is insensitive to it; the number is right for the wrong reason.
- **Q4 burns the fewest probes (3)** because `delivered_date IS NOT NULL` lets the
  agent deduce the delivered status from the data — the one place the data is partly
  revealing. It still misses the internal-test exclusion, so the population is wrong.
  Kept as the intentional "easier" operations anchor.
- A retrieval-augmented solution runs 1–2 queries per question and reconciles to
  the golds; the delta — turns burned and correctness — is what you are grading.

---

## Trap ledger

### G1 — Cross-domain key mismatch (SKU text vs item_code int) — used by Q6
- **Where:** order/returns/shipment side uses `sku` TEXT (`SKU-00042`); inventory/
  supplier side uses `item_code` INTEGER (`42`). `products` bridges (`product_id` +
  `sku`).
- **The bite:** `order_lines.sku = inventory.item_code` returns **0 rows silently**
  (text ≠ int, no error). Verified: naive join **0 rows**; bridged via `products`
  **302,990 rows**.
- **Defeat:** bridge via `products`, or decode `item_code = CAST(SUBSTR(sku,5) AS
  INT)`. Verify the join returns rows instead of trusting a silent zero.

### G2 — `status` is a different code set per table — used by Q4, Q8
- **Where:** `orders.status` [ORDER_STATUS], `shipments.status` [SHIP_STATUS],
  `returns.status` [RETURN_STATUS], `replenishment_orders.status` [PO_STATUS],
  `pick_tasks.status_code` [PICK_STATUS], etc.
- **The bite:** the terminal "done" integer differs — order fulfilled = 4, shipment
  delivered = 5, leg completed = 3, transfer received = 3. Reusing one decode across
  tables gives a plausible-but-wrong population. Verified sets: orders {1..6},
  shipments {2,3,4,5,7}.
- **Defeat:** re-derive the code set for the specific table; look the value up in
  the dictionary. (Q4 partly deducible via `delivered_date`; Q8 is not.)

### X-EXCL — the reporting exclusions (internal-test + draft/cancelled) — Q1,2,3,9,10
- **Where:** `orders.priority_code = internal_test` (the ORDER_PRIORITY carve-out),
  plus ORDER_STATUS `cancelled`/`draft` for revenue/demand populations.
- **The bite:** internal-test orders are **~3.09% of orders (618/20,000)** and look
  completely normal — real customers, normal totals (avg $1,205 vs $1,194 for real,
  indistinguishable), real shipments. **No data signal** separates them. Cancelled/
  draft carry an `order_total` too and corrupt a naive sum. Fully guidance-only.
- **Defeat:** habitually exclude internal-test on any order-touching query; add
  cancelled+draft for revenue/demand. **Prime discriminator.**

### X-ACTIVE — `is_active` selects the current operational set — Q5, Q7, Q9
- **Where:** `products.is_active`, `warehouses.is_active`, `customers.is_active`.
- **The bite:** guidance-only (§2.6). For a *current-state* question, retired records
  must be dropped. Verified: **Central DC is inactive** (7 of 8 warehouses active);
  542 of 600 products active; 265 of 294 enterprise customers active. Omit the filter
  and a naive Q5 reports Central DC and inflated counts.
- **Defeat:** filter `is_active = 1` for "currently…" questions; leave it off for
  historical ones.

### X-LEDGER — signed movement ledger + fixed clock — Q7
- **Where:** `inventory_transactions` — outbound = INV_TXN_TYPE `shipment`, deltas
  negative (`ABS` for magnitude); windows measured against **TODAY = 2024-12-31**,
  not `date('now')`.
- **The bite:** Q7 counts positions with **no** outbound in 90 days, so an **inner
  join** from positions to the ledger *drops exactly the rows being counted* — the
  correct shape is `NOT EXISTS` / `LEFT JOIN … IS NULL`. Filtering by a status code
  instead of INV_TXN_TYPE, or using `date('now')`, also breaks it.
- **Defeat:** ledger sign rule (§3.5) + days-of-supply window machinery (§8) + the
  anti-join shape.

### X-NET / X-FANOUT — gross vs net, header-vs-line grain — Q2
- **Where:** net revenue = gross − realized-return value (§20); returned orders stay
  in gross (§2.3). `order_total` is header-grain; `line_total` is line-grain.
- **The bite:** approximating net by *dropping* returned orders under-counts (a
  return is usually partial) — verified gap ~$371k. Summing a header measure across
  a fanned child join inflates it.
- **Defeat:** value returns at line sale price, count only RETURN_STATUS
  `received`/`refunded`, aggregate gross and returns as separate CTEs, subtract last.

### G4/G5 — 2-hop dictionary + topic-organized guidance (structural) — all questions
- **G4:** a topic doc names the code set for a column; the separate **Code
  Dictionary** defines the integers. Single-hop grep on a column name never resolves
  a value.
- **G5:** `docs/part2/guidance/` is organized by **topic, not table**, and is large
  (~100k+ tokens). "Open the doc named after my table" finds nothing; a full dump
  doesn't fit — runtime search/retrieval is mandatory.
- **Defeat:** content search across docs, follow cross-references, chain
  column → code-set name → dictionary value.

---

## Build verification (data.db, seed=42, 47 tables, 528,289 rows)

- **G1:** naive `sku = item_code` join → **0 rows**; bridged via `products` →
  **302,990 rows**.
- **G2:** orders status {1..6}, shipments {2,3,4,5,7}; terminal ints differ
  (orders 4, shipments 5).
- **X-EXCL:** internal_test = **618/20,000 (3.09%)**; avg order_total $1,205 (test)
  vs $1,194 (real). 2024 alone: 317 internal-test, 193 draft.
- **X-ACTIVE:** active products 542/600; active warehouses **7/8 (Central DC
  retired)**; active enterprise customers 265/294.
- **Golds:** Q1 $10,382,697.48 (8,723 orders) · Q2 $9,934,476.10 (gross
  $10,382,697.48 − returns $448,221.38) · Q3 77.6% (13,533/17,446) · Q4 71.7%
  on-time / 28.3% late (14,628 graded) · Q5 Northeast DC 83 · Q6 354 (naive 0) ·
  Q7 676 of 2,815 active positions · Q8 7.0 days (n=13,280) · Q9 253 · Q10 twelve
  months summing to $10,382,697.48.
