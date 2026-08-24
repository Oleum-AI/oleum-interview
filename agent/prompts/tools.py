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
