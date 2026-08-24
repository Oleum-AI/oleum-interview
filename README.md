# oleum-interview

A tiny agent that answers questions about data in a local SQLite database. It's a
skeleton: it works, but it's deliberately basic. Your job is to build on it.

## Project layout

```
.
├── main.py              # entry point — ask the agent questions
├── start.sh             # one-step setup + run
├── docs/
│   └── DATA_GUIDE.md    # full reference for the dataset (hand this to the model)
├── agent/               # the agent
│   ├── loop.py          #   the agent loop   <- you'll work here most
│   ├── llm.py           #   the OpenAI model call
│   └── prompts/         #   what the agent is told   <- edit these freely
│       ├── system.py    #     the system prompt
│       └── tools.py     #     the tool schemas (run_sql, submit_answer)
└── database/            # the data layer
    ├── schema.sql       #   the database schema (copy/paste-ready context)
    ├── build.py         #   generates data.db and fills it with sample data
    └── connection.py    #   read-only connection + query runner
```

The agent has two tools: `run_sql` (run a query, see the rows) and `submit_answer` (its
final, **structured** answer — the run ends when it's called).

## Setup

The quickest path — one script sets up the venv, builds the data, and starts the agent:

```bash
./start.sh                  # add your OPENAI_API_KEY to .env when prompted
```

Or do it by hand from the project root:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then add your OPENAI_API_KEY
python database/build.py    # creates data.db and fills it with sample data
```

## The data

A small retail chain — **Meridian Retail**: products, suppliers, stores, warehouses,
inventory, employees, customers, and sales/purchase orders (12 tables).

It's mostly self-explanatory, but a handful of columns can't be understood from the
schema alone: a few have terse names (`wac`, `gla`, `cap`, `rop`, `roq`, `chan`), a few
store **numeric codes** instead of readable text (`sales_orders.status` where `3` =
delivered, `purchase_orders.status`, `chan`), and one — `customers.seg` — is an
internal code with **no signal anywhere in the data** (e.g. `seg = 9` marks test
accounts that must be excluded from reporting). That out-of-band knowledge is exactly
what `docs/DATA_GUIDE.md` is for.

- `database/schema.sql` — the schema only (clean DDL, copy-paste-ready context).
- `docs/DATA_GUIDE.md` — the full reference: every table and column, the decoder for
  the coded/cryptic ones, how they join, the invariants the data obeys, and example
  questions. **Hand this to the model as context.**
- `database/build.py` — creates `data.db` and fills it from a fixed random seed, so
  everyone gets the same, internally-consistent data.

## Run

```bash
python main.py                                    # interactive — keeps asking
python main.py "how many orders were placed in 2024?"   # or seed the first question
```

## Where to build

- **`agent/prompts/system.py`** — the system prompt that steers the agent.
- **`agent/prompts/tools.py`** — add tools (define a schema, add it to `TOOLS`, handle it in `loop.py`).
- **`agent/loop.py`** — the control flow (planning, retries, validation, ...).
- **`agent/llm.py`** — swap OpenAI models via `LLM_MODEL` in `.env`; no code change needed.
