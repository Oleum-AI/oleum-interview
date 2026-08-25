# Instructions

# Part 2

We are simply extending the previous task: build a **SQL-analyst agent** that takes an analyst's  
natural-language question, explores the database, and returns a correct, grounded answer.

You now have a larger database and more documentation (in `/docs`), spanning several business domains (order management, fulfillment/shipping, warehouse/inventory) of a mid-size retail logistics operation. **Craft a scalable solution: minimize turn-burn (wasteful tool calls caused by missing context) while optimizing accuracy and latency as best as possible.**

This is deliberately open-ended, and there are many reasonable ways to approach it. The context is now too large to simply dump into the system prompt. Deciding *what* the agent retrieves, *when*, and *how much* is the heart of the problem, design that however you think is best.

To launch the agent, run `./start.sh`.