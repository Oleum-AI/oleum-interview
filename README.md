# oleum-interview

A small agent that answers analyst questions about data in a local SQLite database.
It's a skeleton: it runs, but it's deliberately basic. Your job is to build on it.

Your task is described in **`INSTRUCTIONS.md`** — read that first.

## Project layout

```
.
├── main.py                     # entry point — ask the agent questions
├── start.sh                    # one-step setup + run
├── INSTRUCTIONS.md             # your brief — start here
├── docs/                       # the company's reference docs (large — read on demand)
│   ├── reference.md            #   code sets, reporting conventions, exclusions
│   ├── order_management.md
│   ├── fulfillment_and_shipping.md
│   └── warehouse_and_inventory.md
├── agent/                      # the agent
│   ├── loop.py                 #   the agent loop        <- you'll work here most
│   ├── llm.py                  #   the OpenAI model call
│   └── prompts/                #   what the agent is told <- edit these freely
│       ├── system.py           #     the system prompt
│       └── tools.py            #     the tool schemas (run_sql, submit_answer)
└── database/                   # the data layer
    ├── schema.sql              #   the database schema (discoverable at runtime too)
    ├── build.py                #   generates data.db from a fixed seed
    └── connection.py           #   read-only connection + query runner
```

The agent starts with two tools: `run_sql` (run a query, see the rows) and
`submit_answer` (its final, **structured** answer — the run ends when it's called).

## Setup & run

The quickest path — one script sets up the venv, builds the data, and starts the agent:

```bash
./start.sh                  # add your OPENAI_API_KEY to .env when prompted
```

Or by hand from the project root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your OPENAI_API_KEY
python database/build.py    # creates data.db from a fixed seed
DB_PATH="$PWD/data.db" python main.py
```

`build.py` builds the database deterministically (fixed seed), so everyone gets
the same, internally-consistent data.

```bash
python main.py                                   # interactive — keeps asking
python main.py "how many orders were placed in 2024?"   # or seed the first question
```

## The data and the guidance

The database is large — dozens of tables across order management, fulfillment/shipping,
and warehouse & inventory. The schema is discoverable at runtime (e.g. `sqlite_master`),
but the schema alone won't tell you what coded columns mean or which reporting
conventions apply. The company's reference documentation lives under
**`docs/`** — it is organized by topic and is far too large to read all
at once, so the agent has to find and read only what it needs.

## Where to build

- **`agent/prompts/system.py`** — the system prompt that steers the agent.
- **`agent/prompts/tools.py`** — add tools (define a schema, add it to `TOOLS`, handle it in `loop.py`).
- **`agent/loop.py`** — the control flow (planning, retrieval, retries, validation, ...).
- **`agent/llm.py`** — swap OpenAI models via `LLM_MODEL` in `.env`; no code change needed.
</content>
</invoke>
