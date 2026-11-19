import json
import sqlite3
from pathlib import Path

from ask.keyword import keyword_search, fuse
from ask.retrieve import search

HERE = Path(__file__).parent
DB = HERE.parent.parent / "shimaclips.db"

QUESTIONS = [
    ("q01", "semantic", "Find clips where he talks about boxing"),
    ("q02", "semantic", "Find clips about resident evil"),
    ("q03", "semantic", "Find clips where he goes fishing"),
    ("q04", "semantic", "What happened on the island stream?"),
    ("q05", "semantic", "Find clips about someone's birthday"),
    ("q06", "semantic", "Find clips where he is on a facetime call"),
    ("q07", "semantic", "Find clips about New York"),
    ("q08", "semantic", "Find clips where he talks about Japan"),
    ("q09", "semantic", "Find clips with Lacy"),
    ("q10", "semantic", "Who is burger?"),
    ("m01", "mixed", "When did he do his island stream?"),
    ("m02", "mixed", "When was the World Cup mentioned?"),
    ("a01", "abstain", "Find clips where he talks about chess"),
    ("a02", "abstain", "Find clips where he plays poker"),
    ("a03", "abstain", "Find clips about his trip to Florida"),
]


def candidates(conn, question, n):
    emb = search(conn, question, kind="transcript", k=n)
    kw = keyword_search(conn, question, k=n)
    return fuse([emb, kw], k=n)


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    lines = [
        "# Answer key sheet",
        "",
        "For each question, change `[ ]` to `[x]` on every clip that REALLY matches the question.",
        "Leave `[ ]` if it does not match. Read the quote and, if unsure, open the link.",
        "For the three a-questions the right answer is 'I don't know', so tick only a clip that truly matches.",
        "",
    ]
    for qid, kind, q in QUESTIONS:
        n = 6 if kind == "abstain" else 10
        lines += [f"## {qid} ({kind}): {q}", ""]
        for h in candidates(conn, q, n):
            r = conn.execute(
                "SELECT k.title, k.url, k.created_at, t.text FROM clips k JOIN transcripts t ON t.clip_id = k.id WHERE k.id = ?",
                (h.clip_id,),
            ).fetchone()
            title, url, created, text = r
            snippet = " ".join(text.split())[:240]
            lines += [f"- [ ] `{h.clip_id}` {created[:10]} | {title}", f"  - {url}", f"  - \"{snippet}\"", ""]
    out = HERE / "labelling.md"
    out.write_text("\n".join(lines))
    print("wrote", out, len(lines), "lines")


if __name__ == "__main__":
    main()
