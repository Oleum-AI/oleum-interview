# Instructions

Your task is to build a **SQL-analyst agent**: a agent that takes an analyst's natural-language question, explores a live SQLite database, and returns a correct, grounded answer.

You're given a barebones agent with one `run_sql` tool. Build it out however you see fit i.e. add tools, change prompts, edit the control flow, whatever you need. We'll also give you a handful of question/answer pairs to use as your benchmarks.

You're working with one database about a small retail chain — 12 tables: categories, suppliers, products, stores, warehouses, employees, inventory, customers, and sales/purchase orders with their line items.

The schema is discoverable at runtime, but crucial information about ambiguities lives in `docs/DATA_GUIDE.md`, the full reference for the dataset and small enough to hand to the model as context.

To run / test your program, run command `./start.sh`This spins up the venv and starts the agent as a chat in your terminal. Note the chat is stateless, so conversation history does not grow question-to-question.