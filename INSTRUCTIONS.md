# Instructions

Your task is to build a **SQL-analyst agent**: an agent that takes an analyst's natural-language question, explores a live SQLite database, and returns a correct, grounded answer.

# PART 1
You're given a barebones agent skeleton with one `run_sql` tool. Build it out however you see fit; Add tools, change prompts, edit the control flow, etc. We'll also give you a handful of question/answer pairs to use as a performance benchmark.

For part 1, you're working with one database about a small retail chain — 12 tables: categories, suppliers, products, stores, warehouses, employees, inventory, customers, and sales/purchase orders with their line items.

Crucial information about ambiguities lives in `docs/DATA_GUIDE.md`, the full reference for the dataset.

To run / test your program, launch command `./start.sh`. This spins up the venv, runs the sqlite make script, and starts the agent as a chat in your terminal. Note the chat is stateless, so conversation history does not grow question-to-question.