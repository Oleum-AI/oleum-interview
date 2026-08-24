# agent.py
# The agent loop. This is the heart of the exercise — extend it however you like
# (better prompting, planning, retries, validation, more tools, ...).
#
# The loop is deliberately tiny:
#   ask the model  ->  it calls run_sql (maybe several times)  ->  it calls submit_answer  ->  done.

from llm import complete
from tools import TOOLS, run_sql

# Intentionally minimal — improving this prompt is part of the exercise.
SYSTEM_PROMPT = (
    "You are a data analyst agent. Answer the user's question about data in a SQL warehouse.\n"
    "Use the run_sql tool to inspect the schema and run queries. Base your answer only on query results.\n"
    "When you are confident, call submit_answer with the final SQL and a concise answer."
)

MAX_STEPS = 15


def run_agent(question: str, model=None, provider=None, verbose=True) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    for _ in range(MAX_STEPS):
        turn = complete(messages, TOOLS, model=model, provider=provider)
        messages.append({"role": "assistant", "content": turn["content"], "tool_calls": turn["tool_calls"]})

        if verbose and turn["content"]:
            print(f"\n[assistant] {turn['content']}")

        if not turn["tool_calls"]:
            # Model replied without acting — nudge it to finish via the structured tool.
            messages.append({"role": "user", "content": "Call submit_answer with your final answer."})
            continue

        final = None
        for tc in turn["tool_calls"]:
            if tc["name"] == "run_sql":
                query = tc["arguments"].get("query", "")
                if verbose:
                    print(f"\n[run_sql]\n{query}")
                result = run_sql(query)
                if verbose:
                    print(f"[result]\n{result}")
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": "run_sql", "content": result})
            elif tc["name"] == "submit_answer":
                final = tc["arguments"]
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": "submit_answer", "content": "Recorded."})

        if final is not None:
            return final

    return {"error": "max_steps_reached"}
