# ABOUTME: A simple grep-style search over the docs/ reference material.
# Returns matching lines (file:line + a little context) so the agent can locate
# the relevant guidance without reading whole files into context.
import re
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
MAX_MATCHES = 30


def grep_docs(pattern: str, context: int = 2) -> str:
    """Case-insensitive regex search across docs/*.md.

    Returns up to MAX_MATCHES blocks, each shown as `file:line` with `context`
    lines on either side. Does not return whole files.
    """
    if not pattern:
        return "ERROR: empty pattern."
    try:
        rx = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"ERROR: invalid regex: {e}"

    files = sorted(DOCS_DIR.glob("*.md"))
    if not files:
        return f"No docs found in {DOCS_DIR}."

    blocks = []
    total = 0
    for path in files:
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not rx.search(line):
                continue
            total += 1
            if len(blocks) < MAX_MATCHES:
                lo = max(0, i - context)
                hi = min(len(lines), i + context + 1)
                snippet = "\n".join(f"{path.name}:{n + 1}: {lines[n]}" for n in range(lo, hi))
                blocks.append(snippet)

    if total == 0:
        return f"No matches for /{pattern}/ in docs/ ({', '.join(p.name for p in files)})."

    header = f"{total} matching line(s) for /{pattern}/"
    if total > MAX_MATCHES:
        header += f" (showing first {MAX_MATCHES}; refine the pattern to narrow)"
    return header + ":\n\n" + "\n---\n".join(blocks)
