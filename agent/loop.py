from rich.console import Console

from agent.llm import complete
from database.connection import run_sql
from agent.prompts import SYSTEM_PROMPT, TOOLS

console = Console()

MAX_PREVIEW_CHARS = 500

# Handlers for "action" tools: name -> fn(arguments: dict) -> str (the tool output).
# To add a new tool: declare it in agent/prompts/tools.py and register a handler here.
# submit_answer is handled separately below because it's terminal (ends the loop).
TOOL_HANDLERS = {
    "run_sql": lambda args: run_sql(args.get("query", "")),
}


def _rule():
    console.rule(style="grey37")


def _preview(text: str) -> str:
    text = (text or "").strip()
    if len(text) > MAX_PREVIEW_CHARS:
        return text[:MAX_PREVIEW_CHARS] + f"  [dim]… (+{len(text) - MAX_PREVIEW_CHARS} chars)[/dim]"
    return text


def run_agent(question: str, model=None, verbose=True) -> dict:
    input_items = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    previous_response_id = None

    while True:
        turn = complete(input_items, TOOLS, previous_response_id=previous_response_id, model=model)
        previous_response_id = turn["id"]

        if verbose and turn["reasoning"]:
            _rule()
            console.print(f"[bold yellow][THINKING][/bold yellow]")
            console.print(f"[dim italic]{_preview(turn['reasoning'])}[/dim italic]")
        if verbose and turn["content"]:
            _rule()
            console.print(f"[white]{turn['content']}[/white]")

        if not turn["tool_calls"]:
            input_items = [{"role": "user", "content": "Call submit_answer with your final answer."}]
            continue

        final = None
        outputs = []
        for tc in turn["tool_calls"]:
            name = tc["name"]
            args = tc["arguments"]

            if name == "submit_answer":
                final = args
                if verbose:
                    _rule()
                    console.print(f"[bold magenta][TOOL CALL: submit_answer][/bold magenta]")
                outputs.append({"type": "function_call_output", "call_id": tc["call_id"], "output": "Recorded."})
                continue

            if verbose:
                _rule()
                console.print(f"[bold cyan][TOOL CALL: {name}][/bold cyan]")
                console.print(f"[cyan]  - {args}[/cyan]")
            handler = TOOL_HANDLERS.get(name)
            result = handler(args) if handler else f"ERROR: unknown tool '{name}'"
            if verbose:
                console.print(f"[green]  - result:[/green] {_preview(result)}")
            outputs.append({"type": "function_call_output", "call_id": tc["call_id"], "output": result})

        if final is not None:
            return final

        input_items = outputs
