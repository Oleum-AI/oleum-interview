# oleum-interview

A tiny agent that answers questions about data in a local SQLite database. It's a
skeleton: it works, but it's deliberately basic. Your job is to build on it.

## What's here

| File          | What it is                                                        |
|---------------|-------------------------------------------------------------------|
| `main.py`     | Entry point — run the agent on one question.                      |
| `agent.py`    | The agent loop + system prompt. **This is where you'll work most.** |
| `tools.py`    | The tools (`run_sql`, `submit_answer`) and the SQLite connection. |
| `llm.py`      | Model-agnostic model call (OpenAI or Anthropic). You rarely touch this. |

The agent has two tools: `run_sql` (run a query, see the rows) and `submit_answer` (its
final, **structured** answer — the run ends when it's called).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your model key and DB_PATH
```

## Data

The agent queries a local SQLite file (read-only), set by `DB_PATH` in `.env`.
Build one from a `.sql` script:

```bash
sqlite3 data.db < schema.sql
```

## Run

```bash
python main.py "your question here"
```

## Where to build

- **`agent.py`** — the prompt and the control flow (planning, retries, validation, ...).
- **`tools.py`** — add tools (define a schema, add it to `TOOLS`, handle it in `agent.py`).
- **`llm.py`** — swap models freely via `LLM_MODEL` in `.env`; no code change needed.
