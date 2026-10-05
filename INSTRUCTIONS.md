# Instructions

Your task is to build a **SQL-analyst agent** that takes an analyst's natural-language question, explores a live SQLite database, and returns a correct, grounded answer.

You're given a barebones agent skeleton with one `run_sql` tool. Build it out however you see fit—you may add tools, change prompts, and edit the control flow. A handful of question-answer pairs in `benchmark_questions.md` serve as a performance benchmark.

Out of the box, the agent gets most benchmark questions wrong as crucial information about the data's ambiguities lives in `docs/DATA_GUIDE.md`. This full dataset reference covers a mid-size retail logistics operation across order management, fulfillment/shipping, and warehouse/inventory.

The context is too large to simply dump into the system prompt. The heart of the problem is deciding what the agent retrieves, when, and how much so that documented knowledge reaches it at runtime. **Craft a scalable solution that minimizes turn-burn (wasteful tool calls caused by missing context) while optimizing accuracy and latency.** This is deliberately open-ended, and many approaches are reasonable.

You'll mainly work in `/agent/prompts`, where the system prompt and tool definitions live. You can view the database schema in `/database/schema.sql`.

To run or test your program, use `./start.sh`. This sets up the virtual environment, builds the SQLite database, and starts the agent as a terminal chat. The chat is stateless—conversation history does not grow from question to question.