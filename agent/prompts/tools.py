# ABOUTME: Tool definitions the agent can call. Edit descriptions/parameters freely.

RUN_SQL_TOOL = {
    "name": "run_sql",
    "description": "Run a read-only SQL query against the database and return the resulting rows.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The SQL query to execute (SQLite dialect)."}
        },
        "required": ["query"],
    },
}

GREP_DOCS_TOOL = {
    "name": "grep_docs",
    "description": (
        "Search the docs/ reference material with a case-insensitive regex. Returns matching "
        "lines as file:line with a little surrounding context — not whole files. Use this to "
        "locate code meanings, conventions, and definitions instead of reading entire guides."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Case-insensitive regex to search for."},
            "context": {"type": "integer", "description": "Lines of context on each side (default 2)."},
        },
        "required": ["pattern"],
    },
}

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

TOOLS = [RUN_SQL_TOOL, GREP_DOCS_TOOL, SUBMIT_ANSWER_TOOL]
