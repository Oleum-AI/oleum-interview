import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "data.db")

_conn = None


def get_conn():
    global _conn
    if _conn is None:
        path = os.environ.get("DB_PATH", DEFAULT_DB)
        _conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    return _conn


def run_sql(query: str, max_rows: int = 100) -> str:
    try:
        cur = get_conn().execute(query)
        if cur.description is None:
            return "OK (no rows returned)."
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows)
        return _format(cols, rows, max_rows)
    except Exception as e:
        return f"ERROR: {e}"


def _format(cols, rows, max_rows) -> str:
    lines = [" | ".join(cols)]
    for r in rows:
        lines.append(" | ".join("NULL" if v is None else str(v) for v in r))
    text = "\n".join(lines)
    if len(rows) >= max_rows:
        text += f"\n... (truncated at {max_rows} rows)"
    return f"{len(rows)} row(s):\n{text}"
