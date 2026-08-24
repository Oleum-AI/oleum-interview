import os
import sqlite3

SEED = 42

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# Defaults to part2.db so Part 1's data.db stays intact. connection.py reads
# the same DB_PATH env var, so `export DB_PATH=.../part2.db` repoints the agent.
DB_PATH = os.environ.get("DB_PATH", os.path.join(ROOT, "part2.db"))
SCHEMA = os.path.join(HERE, "part2_schema.sql")


def build():
    # TODO: generate the large, multi-subsystem dataset + field guidance.
    raise NotImplementedError("Part 2 data generation not written yet.")


if __name__ == "__main__":
    build()
