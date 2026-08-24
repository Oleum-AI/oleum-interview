# tools.py
# The tools the agent can call, plus the Databricks connection.
#
# There are two tools to start:
#   - run_sql:       run a query against the Databricks SQL warehouse and see the rows.
#   - submit_answer: the agent's FINAL, structured answer (this is how we enforce a
#                    structured output — the run ends when the agent calls it).
#
# Add more tools here: define the JSON schema, add it to TOOLS, and handle it in agent.py.

import os

# --- Tool schemas (normalized; llm.py translates these per provider) -------------------

RUN_SQL_TOOL = {
    "name": "run_sql",
    "description": "Run a read-only SQL query against the Databricks warehouse and return the resulting rows.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The SQL query to execute."}
        },
        "required": ["query"],
    },
}

# The final structured answer. Extend this schema as the task requires.
SUBMIT_ANSWER_TOOL = {
    "name": "submit_answer",
    "description": "Return your final answer. Call this exactly once, when you are confident.",
    "parameters": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "The final SQL query that produced the answer."},
            "answer": {"type": "string", "description": "A concise natural-language answer to the question."},
        },
        "required": ["sql", "answer"],
    },
}

TOOLS = [RUN_SQL_TOOL, SUBMIT_ANSWER_TOOL]


# --- Databricks connection -------------------------------------------------------------

_conn = None


def _get_conn():
    """Lazily open (and reuse) a single warehouse connection."""
    global _conn
    if _conn is None:
        from databricks import sql

        _conn = sql.connect(
            server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            http_path=os.environ["DATABRICKS_HTTP_PATH"],
            access_token=os.environ["DATABRICKS_TOKEN"],
        )
    return _conn


def run_sql(query: str, max_rows: int = 100) -> str:
    """Execute a query and return the rows as text. Errors are returned as text so the
    model can read them and self-correct rather than crashing the run."""
    try:
        with _get_conn().cursor() as cur:
            cur.execute(query)
            if cur.description is None:
                return "OK (no rows returned)."
            cols = [c[0] for c in cur.description]
            rows = cur.fetchmany(max_rows)
            return _format(cols, rows, max_rows)
    except Exception as e:  # noqa: BLE001 - surface any DB error back to the model
        return f"ERROR: {e}"


def _format(cols, rows, max_rows) -> str:
    lines = [" | ".join(cols)]
    for r in rows:
        lines.append(" | ".join("NULL" if v is None else str(v) for v in r))
    text = "\n".join(lines)
    if len(rows) >= max_rows:
        text += f"\n... (truncated at {max_rows} rows)"
    return f"{len(rows)} row(s):\n{text}"
