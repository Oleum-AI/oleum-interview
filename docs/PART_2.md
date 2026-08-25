# Part 2 — brief

In Part 1 you built a SQL-analyst agent and — the intended move — handed the model
the entire data guide in its system prompt. That worked because the world was
small. Part 2 is a much larger world, and that approach no longer fits.

You are now the analyst agent for a **mid-size third-party-logistics (3PL) /
omnichannel retail operation**: orders, fulfillment/shipping, and warehouse &
inventory — **47 tables** across the three domains. The company's reference
documentation is extensive: it does **not** fit in a single context window. Your
job is to redesign the agent so it can **find the right tables and fields on
demand and look up only the guidance it needs**, then answer real analyst
questions correctly.

## What carries over, what you throw away

- **Keep the scaffold**: the agent loop, the LLM client, the `run_sql` tool, the
  `submit_answer` tool, tracing, `main.py`. It all still runs.
- **Throw away the Part 1 solution**: the "dump the whole guide into the system
  prompt" design is gone. Reset your system prompt and rebuild your tools for this
  problem. The two tools that make sense to keep are `run_sql` and `submit_answer`;
  everything else is yours to design.

## The data and the guidance

- The database is defined in `database/part2_schema.sql` and built into `part2.db`.
  The schema is discoverable at runtime (e.g. `sqlite_master`) — but the schema
  alone will not tell you what the coded columns *mean* or which reporting
  conventions apply.
- The company's guidance lives as markdown under **`docs/part2/guidance/`**. It is
  **organized by topic, not by table**, and it is **large** — reading it all into
  context is not an option. Notable structure you'll have to work with:
  - Coded columns (`status`, `*_code`) are documented by *code set*: a topic doc
    tells you which code set a column uses; a separate **code dictionary** defines
    that set's values. Resolving a code is a two-step lookup.
  - The same column name can mean different things in different tables.
  - There are standard reporting conventions (exclusions, metric definitions) that
    you can only know by reading the guidance — they are not visible in the data.

## Running it

```bash
./start-part2.sh          # builds part2.db (first run) and points the agent at it
```

Same runner as Part 1; it just points `DB_PATH` at `part2.db`.

## Your questions

Answer the questions in **`docs/part2/QUESTIONS.md`**.

## What we're looking for

- **Retrieval design**: how the agent discovers the schema and *searches/reads the
  guidance on demand* instead of pre-loading it. There's no single right tool
  shape — a guidance search tool, a doc reader, a code-lookup helper, etc. are all
  reasonable. We care about the reasoning.
- **Grounding**: resolving coded columns and applying the company's definitions and
  exclusions rather than guessing from column names.
- **Cross-domain correctness**: joining across the domains correctly, and
  **verifying** a join actually returns rows rather than trusting a query that
  silently produces nothing.
- **Context discipline**: pulling in only what's needed, and knowing when it has
  enough to answer.
