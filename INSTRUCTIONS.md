# Instructions

Your task is to build a **SQL-analyst agent**: an agent that takes an analyst's
natural-language question, explores a live SQLite database, and returns a
correct, grounded answer.

## Part 1

You're given a barebones agent skeleton with one `run_sql` tool. Build it out
however you see fit — add tools, change prompts, edit the control flow, etc.
A handful of question/answer pairs in `benchmark_questions.md` serve as a
performance benchmark.

For Part 1 you're working with one database about a small retail chain with 12 tables.

Out of the box, the agent gets most of the benchmark questions wrong. That's
because crucial information about the data's ambiguities lives in
`docs/DATA_GUIDE.md`, the full reference for the dataset. The heart of this
problem is getting that documented knowledge in front of the agent at runtime.

You'll mainly work in `/agent/prompts`, where the system prompt and tool
definitions live. You can also view the database schema in
`/database/schema.sql`.

## Part 2

We are extending the previous task. You now have a larger database and more
documentation (in `/docs`), spanning several business domains (order
management, fulfillment/shipping, warehouse/inventory) of a mid-size retail
logistics operation.

**Craft a scalable solution: minimize turn-burn (wasteful tool calls caused by
missing context) while optimizing accuracy and latency as best as possible.**

This is deliberately open-ended, and there are many reasonable ways to
approach it. The context is now too large to simply dump into the system
prompt. Deciding *what* the agent retrieves, *when*, and *how much* is the
heart of the problem; design that however you think is best.

To run / test your program, run `./start.sh`. This spins up the venv, builds
the SQLite database, and starts the agent as a chat in your terminal. Note the
chat is stateless — conversation history does not grow question-to-question.
