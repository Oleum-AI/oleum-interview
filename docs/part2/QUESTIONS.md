# Part 2 — Analyst Questions

You are the analyst agent for the logistics operation. Answer the questions below
against the live database using the tools you build. The company's documentation
lives under `docs/part2/guidance/` — it is large, so you will not be able to read
all of it at once; find what you need as you go.

Notes that apply to every question:
- "Today" is **2024-12-31**. Money is in **US dollars**, weights in **kilograms**.
- Apply the company's **standard reporting conventions**. When a question names a
  metric the company defines — recognized revenue, net revenue, fill rate, on-time
  delivery, below reorder point, days of supply, and so on — use the company's
  definition and population rules from the guidance, **not** your own reading of
  the column names. Several of these conventions are not visible in the data; the
  only way to get them right is to read the guidance.
- A coded column (`status`, `*_code`) means what the guidance says it means, and
  the **same column name can map to a different code set in a different table**.
- Give the number(s) asked for, and briefly show how you got there.

---

### Revenue & demand

1. What was the company's total **recognized revenue** for **2024**?

2. What was the company's **net revenue after returns** for **2024**?

3. What is the company's **order fill rate** (order fulfillment rate)?

### Operations

4. Of all shipments that were **delivered**, what percentage were **delivered on
   time**?

5. Which **distribution center** currently has the most items sitting **below their
   reorder point**, and how many items is that?

### Cross-domain

6. How many **distinct products that appear on customer orders** are currently
   **below their reorder point in at least one warehouse**?

7. Across the **current active operational set**, how many **inventory positions**
   (a given product at a given warehouse) had **zero outbound shipment movement
   over the trailing 90 days** ending 2024-12-31?

8. For **fulfilled** orders (excluding internal/test orders), what is the **average
   number of days from when the order was placed to when it was delivered**?

### Customers & synthesis

9. How many **active enterprise customers** placed **at least one reportable order**
   in **2024**?

10. Produce **recognized revenue by month for 2024**. Return the twelve monthly
    totals.
