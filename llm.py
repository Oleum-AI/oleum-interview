# llm.py
# Model-agnostic chat completion with tool-calling. Works with OpenAI or Anthropic.
# No agent framework — just the vendor client libraries and a small normalization layer.
#
# You will rarely need to touch this file. It exposes ONE function:
#
#     complete(messages, tools) -> {"content": str, "tool_calls": [ {id, name, arguments}, ... ]}
#
# `messages` and `tools` use a small normalized format (see agent.py / tools.py) so the
# rest of the code never has to care which provider is behind it.

import json
import os


def _provider_for(model: str) -> str:
    """Pick a provider from the model name. Override with LLM_PROVIDER if you like."""
    return "anthropic" if model.lower().startswith("claude") else "openai"


def complete(messages, tools, model=None, provider=None, temperature=None, max_tokens=4096):
    """Send one turn to the model and return a normalized assistant response."""
    model = model or os.environ.get("LLM_MODEL", "gpt-4o")
    provider = provider or os.environ.get("LLM_PROVIDER") or _provider_for(model)
    if provider == "anthropic":
        return _anthropic_complete(messages, tools, model, temperature, max_tokens)
    return _openai_complete(messages, tools, model, temperature)


# --------------------------------------------------------------------------------------
# OpenAI
# --------------------------------------------------------------------------------------
def _openai_complete(messages, tools, model, temperature):
    from openai import OpenAI

    client = OpenAI()  # reads OPENAI_API_KEY
    oai_tools = [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
        for t in tools
    ]
    kwargs = {"model": model, "messages": _to_openai_messages(messages), "tools": oai_tools}
    if temperature is not None:
        kwargs["temperature"] = temperature

    msg = client.chat.completions.create(**kwargs).choices[0].message
    tool_calls = [
        {"id": tc.id, "name": tc.function.name, "arguments": json.loads(tc.function.arguments or "{}")}
        for tc in (msg.tool_calls or [])
    ]
    return {"content": msg.content or "", "tool_calls": tool_calls}


def _to_openai_messages(messages):
    out = []
    for m in messages:
        role = m["role"]
        if role in ("system", "user"):
            out.append({"role": role, "content": m["content"]})
        elif role == "assistant":
            msg = {"role": "assistant", "content": m.get("content") or None}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])}}
                    for tc in m["tool_calls"]
                ]
            out.append(msg)
        elif role == "tool":
            out.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]})
    return out


# --------------------------------------------------------------------------------------
# Anthropic
# --------------------------------------------------------------------------------------
def _anthropic_complete(messages, tools, model, temperature, max_tokens):
    from anthropic import Anthropic

    client = Anthropic()  # reads ANTHROPIC_API_KEY
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    a_tools = [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]

    kwargs = {"model": model, "messages": _to_anthropic_messages(messages), "tools": a_tools, "max_tokens": max_tokens}
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature

    resp = client.messages.create(**kwargs)
    content, tool_calls = "", []
    for block in resp.content:
        if block.type == "text":
            content += block.text
        elif block.type == "tool_use":
            tool_calls.append({"id": block.id, "name": block.name, "arguments": block.input})
    return {"content": content, "tool_calls": tool_calls}


def _to_anthropic_messages(messages):
    # Anthropic has no `system`/`tool` roles in the message list: system is a top-level
    # arg, and tool results are `tool_result` blocks inside a following user turn.
    out, pending = [], []

    def flush():
        if pending:
            out.append({"role": "user", "content": list(pending)})
            pending.clear()

    for m in messages:
        role = m["role"]
        if role == "system":
            continue
        if role == "tool":
            pending.append({"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]})
            continue
        flush()
        if role == "user":
            out.append({"role": "user", "content": m["content"]})
        elif role == "assistant":
            blocks = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls", []):
                blocks.append({"type": "tool_use", "id": tc["id"], "name": tc["name"], "input": tc["arguments"]})
            out.append({"role": "assistant", "content": blocks or m.get("content", "")})
    flush()
    return out
