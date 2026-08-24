# Part 2 — brief

> TODO: candidate-facing brief. Fill in once the domain + schemas are locked.

The dataset is now large enough that you **cannot** paste the full reference into
the model's context. Your Part 1 approach — hand the model the whole guide — no
longer fits. Redesign the agent so it can find the right tables/fields on demand
and look up their guidance only when it needs them.

## What's new

- New, larger data (multiple subsystems). See `database/part2_schema.sql`.
- Field-level guidance is no longer one document — it lives in the data itself
  (TODO: catalog table vs. per-table docs — decide before building).

## Getting there

```bash
./start-part2.sh          # builds part2.db and points the agent at it
```

Same agent, same runner. You keep your Part 1 scaffold (the loop, the SQL
runner, tracing) — but you'll want to **reset your system prompt and tools** for
this problem.

## What we're looking for

> TODO: grading rubric — retrieval design, on-demand field lookup, context
> curation, verification behavior.
