from rich.console import Console

from agent.llm import complete
from database.connection import run_sql
from agent.prompts import SYSTEM_PROMPT, TOOLS

console = Console()

MAX_PREVIEW_CHARS = 500


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
            if tc["name"] == "run_sql":
                query = tc["arguments"].get("query", "")
                if verbose:
                    _rule()
                    console.print(f"[bold cyan][TOOL CALL: run_sql][/bold cyan]")
                    console.print(f"[cyan]  - {query}[/cyan]")
                result = run_sql(query)
                if verbose:
                    console.print(f"[green]  - result:[/green] {_preview(result)}")
                outputs.append({"type": "function_call_output", "call_id": tc["call_id"], "output": result})
            elif tc["name"] == "submit_answer":
                final = tc["arguments"]
                if verbose:
                    _rule()
                    console.print(f"[bold magenta][TOOL CALL: submit_answer][/bold magenta]")
                outputs.append({"type": "function_call_output", "call_id": tc["call_id"], "output": "Recorded."})

        if final is not None:
            return final

        input_items = outputs
