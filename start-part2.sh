# !/usr/bin/env bash
# ./start-part2.sh ["your question here"]   (no question -> prompts you)
# Builds the Part 2 database and points the agent at it via DB_PATH.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
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

export DB_PATH="$PWD/part2.db"

if [ ! -f part2.db ]; then
    python database/build_part2.py
fi

python main.py "$@"
