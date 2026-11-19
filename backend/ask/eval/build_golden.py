import json
import random
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent
DB = HERE.parent.parent / "shimaclips.db"

CASES = [
    ("q01", "semantic", "Find clips where he talks about boxing", r"\bbox(?:ing|er|ers)?\b"),
    ("q02", "semantic", "Find clips about resident evil", r"resident evil"),
    ("q03", "semantic", "Find clips where he goes fishing", r"\bfish(?:ing)?\b"),
    ("q04", "semantic", "What happened on the island stream?", r"\bisland\b"),
    ("q05", "semantic", "Find clips about someone's birthday", r"birthday"),
    ("q06", "semantic", "Find clips where he is on a facetime call", r"facetim"),
    ("q07", "semantic", "Find clips about New York", r"new york"),
    ("q08", "semantic", "Find clips where he talks about Japan", r"\b(?:japan|tokyo)\b"),
    ("q09", "semantic", "Find clips with Lacy", r"\blacy\b"),
    ("q10", "semantic", "Who is burger?", r"\bburger\b"),
    ("m01", "mixed", "When did he do his island stream?", r"\bisland\b"),
    ("m02", "mixed", "When was the World Cup mentioned?", r"world cup"),
    ("a01", "abstain", "Find clips where he talks about chess", r"\bchess\b"),
    ("a02", "abstain", "Find clips where he plays poker", r"\bpoker\b"),
    ("a03", "abstain", "Find clips about his trip to Florida", r"\bflorida\b"),
]


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    rows = conn.execute(
        "SELECT t.clip_id, k.title, k.created_at, t.text FROM transcripts t JOIN clips k ON k.id = t.clip_id"
    ).fetchall()
    golden = json.loads((HERE / "golden.json").read_text())
    golden["semantic"], golden["mixed"], golden["abstain"] = [], [], []
    rng = random.Random(7)
    for qid, kind, question, pattern in CASES:
        rx = re.compile(pattern, re.I)
        rel = [r for r in rows if rx.search(r[1]) or rx.search(r[3])]
        entry = {"id": qid, "question": question, "pattern": pattern, "relevant": [r[0] for r in rel],
                 "dates": sorted(r[2][:10] for r in rel)}
        golden[kind].append(entry)
        print(f"{qid} {question!r}: {len(rel)} relevant")
        for r in rng.sample(rel, min(2, len(rel))):
            m = rx.search(r[3]) or rx.search(r[1])
            src = r[3] if rx.search(r[3]) else r[1]
            a = max(0, m.start() - 70)
            print("    ", r[2][:10], "|", r[1][:40], "|", "..." + " ".join(src[a:m.end() + 70].split()) + "...")
    (HERE / "golden.json").write_text(json.dumps(golden, indent=2))


if __name__ == "__main__":
    main()
