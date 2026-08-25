import json
import os


def _parse(resp):
    content, reasoning, tool_calls = "", [], []
    for item in resp.output:
        if item.type == "reasoning":
            reasoning.extend(s.text for s in (item.summary or []))
        elif item.type == "message":
            content += "".join(c.text for c in item.content if c.type == "output_text")
        elif item.type == "function_call":
            tool_calls.append({
                "call_id": item.call_id,
                "name": item.name,
                "arguments": json.loads(item.arguments or "{}"),
            })
    usage = getattr(resp, "usage", None)
    return {
        "id": resp.id,
        "content": content,
        "reasoning": "\n".join(reasoning),
        "tool_calls": tool_calls,
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", 0),
            "output_tokens": getattr(usage, "output_tokens", 0),
            "total_tokens": getattr(usage, "total_tokens", 0),
        } if usage else {},
    }


def complete(input_items, tools, previous_response_id=None, model=None, reasoning_effort=None):
    from openai import OpenAI

    model = model or os.environ.get("LLM_MODEL", "gpt-5.6-luna")
    reasoning_effort = reasoning_effort or "low"
    client = OpenAI()

    resp = client.responses.create(
        model=model,
        input=input_items,
        tools=[{"type": "function", **t} for t in tools],
        reasoning={"effort": reasoning_effort, "summary": "auto"},
        previous_response_id=previous_response_id,
    )
    return _parse(resp)
