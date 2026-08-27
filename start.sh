#!/usr/bin/env bash
# ./start.sh ["your question here"]   (no question -> prompts you)
# Builds the database and points the agent at it via DB_PATH.
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
    echo "!! python3 not found on PATH. Install Python 3 (>=3.10) and re-run." >&2
    exit 1
fi

if [ ! -f .venv/bin/activate ]; then
    rm -rf .venv
    python3 -m venv .venv
fi
source .venv/bin/activate

pip install -q -r requirements.txt

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
    fi
    echo "!! No .env found. Created one from .env.example — add your OPENAI_API_KEY, then re-run." >&2
    exit 1
fi

export DB_PATH="$PWD/data.db"

if [ ! -f data.db ]; then
    python database/build.py
fi

python main.py "$@"
