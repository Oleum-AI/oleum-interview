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
    console.print(f"[dim]({elapsed:.1f}s)[/dim]")


def main():
    # An optional first question can come from the command line; after that we
    # keep prompting so the session stays open until the user exits.
    pending = " ".join(sys.argv[1:]).strip()
    console.print("[dim]Ask a question. Ctrl-C or type 'exit' to quit.[/dim]")
    while True:
        try:
            question = pending or console.input("\n[bold]Question:[/bold] ").strip()
            pending = ""
            if not question:
                continue
            if question.lower() in {"exit", "quit"}:
                break
            answer_once(question)
        except (KeyboardInterrupt, EOFError):
            break
    console.print("\n[dim]Bye.[/dim]")


if __name__ == "__main__":
    main()
