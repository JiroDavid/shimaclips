import sqlite3

from ask.embed import build_vectors
from ask.keyword import rebuild

DB = "shimaclips.db"


def main() -> None:
    conn = sqlite3.connect(DB, timeout=120)
    print("embedded", build_vectors(conn), "new clips")
    print("keyword index rows", rebuild(conn))


if __name__ == "__main__":
    main()
