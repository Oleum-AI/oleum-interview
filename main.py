# main.py
# Run the agent on a single question:
#
#     python main.py "how many orders were placed in 2024?"
#
# or run it with no argument and type your question at the prompt.

import json
import sys
import time

from dotenv import load_dotenv

load_dotenv()  # load .env before anything reads os.environ

from agent import run_agent  # noqa: E402 - must come after load_dotenv()


def main():
    question = " ".join(sys.argv[1:]).strip() or input("Question: ").strip()
    start = time.time()
    result = run_agent(question)
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    print(json.dumps(result, indent=2))
    print(f"({elapsed:.1f}s)")


if __name__ == "__main__":
    main()
