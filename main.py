import logging
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from agent.loop import run_agent

# Quiet the noisy HTTP/SDK loggers so the console stays readable.
logging.basicConfig(level=logging.WARNING, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

console = Console()


def answer_once(question: str):
    start = time.time()
    result = run_agent(question)
    elapsed = time.time() - start

    console.rule("[bold green]Answer")
    console.print(result.get("answer", ""))
    if result.get("sql"):
        console.print(Panel(Syntax(result["sql"], "sql", theme="ansi_dark"), title="SQL", border_style="cyan"))
    console.print(
        f"[dim]({elapsed:.1f}s · {result.get('tool_calls', 0)} tool calls · "
        f"{result.get('tokens', 0):,} tokens)[/dim]"
    )


def main():
    # Answer a single question, then stop. The question can come from the command
    # line; if none is given, prompt for one. Each run handles exactly one question.
    question = " ".join(sys.argv[1:]).strip()
    try:
        if not question:
            question = console.input("[bold]Question:[/bold] ").strip()
    except (KeyboardInterrupt, EOFError):
        return
    if question:
        answer_once(question)


if __name__ == "__main__":
    main()
