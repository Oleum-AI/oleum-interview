# Part 2 — Analyst Questions

You are the analyst agent for the logistics operation. Answer the questions below
against the live database using the tools you build. The company's documentation
lives under `docs/part2/guidance/` — it is large, so you will not be able to read
all of it at once; find what you need as you go.

Notes that apply to every question:
- "Today" is **2024-12-31**. Money is in **US dollars**, weights in **kilograms**.
- Apply the company's standard reporting conventions. When a question implies a
  metric the company defines (revenue, delivered late, below reorder point, …),
  use the company's definition from the guidance, not your own.
- Give the number(s) asked for, and briefly show how you got there.

---

### Warm-up

1. How many customers are in the **enterprise** segment?

2. What was the company's total **recognized revenue** for **2024**?

3. How many orders were placed through the **mobile app** channel in **2024**?

### Operations

4. Of all shipments that were **delivered**, what percentage were **delivered late**?

5. Which **distribution center** currently has the most items sitting **below their
   reorder point**, and how many items is that?

6. How many returns were requested with the reason **"no longer needed"**?

### Cross-domain

7. How many **distinct products that appear on customer orders** are currently
   **below their reorder point in at least one warehouse**?

8. Take the **five products with the most units shipped**. For each, what is the
   **total available quantity on hand** across all warehouses?

9. For **fulfilled** orders (excluding internal/test orders), what is the **average
   number of days from when the order was placed to when it was delivered**?

### Synthesis

10. Produce **recognized revenue by month for 2024**. Return the twelve monthly
    totals.
