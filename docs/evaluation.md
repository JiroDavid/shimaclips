# Evaluation of the AI features

How the assistant's answers were measured, what the numbers are, and where they are weak. The numbers are
reproducible with `cd backend && .venv/bin/python -m ask.evaluate` (needs Ollama and the local database).

Evaluation: `cd backend && .venv/bin/python -m ask.evaluate` runs a golden set (23 structured, 12 topic, 3 abstention, 25 topic-guard, 11 routing, 12 web and 3 prompt-injection questions) and saves results to `backend/ask/eval/results/`. The structured checks compare against independent SQL. For topic questions, the answer key is every clip in the library whose title or transcript literally contains the topic word, built by `ask/eval/build_golden.py`, so it does not depend on the search under test. Because that key is word-based, it favours keyword search and understates what embeddings find through paraphrase.

Latest results (12 topic questions, top 5 results):

| Retrieval | hit@5 | precision@5 | MRR |
|---|---|---|---|
| Title embeddings | 0.67 | 0.42 | 0.67 |
| Transcript embeddings | 0.67 | 0.53 | 0.67 |
| Keyword (BM25) | 1.00 | 0.90 | 1.00 |
| Hybrid (used by the app) | 1.00 | 0.73 | 0.88 |

Other results, with their caveats:
- **Structured questions:** 23 of 23 exact, but this is in-sample. The first run of the 10 harder phrasings scored 6 of 10 before fixes (saved as `baseline-structured-v1.json`). Fixing one thing broke others twice (copying the user's date words verbatim stopped "Feb 2026" and "in 2024" from resolving), which is why the date resolver is tested separately. The model once silently rewrote "month before last" as "last month", which is why dates are resolved in code.
- **Held-out run:** 12 questions written by the project owner in their own wording, run before any fix (saved as `heldout-baseline-v1.json`). 7 were fully correct (top clips this year and this month, two "who is" questions, Ludwig's most viewed clip, the island stream, mentions of "burger"). 2 were honest abstentions (the top 10 most viewed streamers this month, and a question about a streamer's girlfriend). 1 was correct only as far as its web source goes (streamer of the year). 2 were confident wrong answers: "average views" was answered with a clip count, and "how old is Ludwig" with his account creation date. Both were fixed afterwards (a view statistics tool, and facts about a streamer as a person now go to the web), so those two are in-sample now.
- **Second held-out run (written by the AI, not the developer):** 16 questions with the scoring rules fixed in code before running (`backend/ask/eval/heldout.py`, results in `heldout-v2-baseline.json`). 13 of 16 passed on the first run. Two failures were the web search service not answering (the app said so honestly). One was a real bug: the model wrote the streamer as "jason", which is also a real, unrelated Twitch channel, so the app looked up the wrong channel and would have started transcribing it. Fixed by resolving short names against streamers already in the database first, so "jason" now means jasontheween, with a visible note. Those questions are in-sample after the fix, and because an AI wrote them they are probably easier than a human's would be.
- **Topic guard:** 24 of 25, and 18 of 19 on questions not used as examples in its prompt. It is brittle: changing the prompt to fix one question flipped another, so prompt tuning was stopped and deterministic code handles what it can.
- **Routing and streamer extraction:** 10 of 11 from the model alone. The model sends "who is burger? jasontheween" to the streamer profile, so code now overrides that: a "who is X" question about something that is not a streamer searches the clips instead.
- **Web answers:** 11 of 12 on a deliberately easy set (textbook Twitch facts, plus four made-up questions that must answer "could not verify"). The checks are lenient (a valid citation and a keyword), results vary between runs because search results vary, and a citation is not proof that the source supports the claim.
- **Prompt injection:** 3 of 3 resisted. A hostile page did not make the model obey it or leak its instructions. It did make the model over-cautious: it said it could not verify an answer that a clean source in the same prompt stated plainly.
- **Abstention:** poker and Florida abstain correctly; chess (two passing mentions) is answered from those two clips. Tuned on these three cases, so it needs fresh ones.
- **End to end:** about 74 percent of cited clips on topic questions are relevant. A typical answer costs about 1,000 local tokens and 2 to 4 seconds.

## Evaluation sets

| Set | Size | What it checks |
|---|---|---|
| Structured | 23 | Counts, top lists and view statistics against independent SQL |
| Topic search | 12 | Retrieval quality (hit@5, precision@5, MRR) for four retrieval modes |
| Abstention | 3 | Says it does not know when no clip mentions the topic |
| Topic guard | 25 | Clips, general Twitch and off-topic questions are separated correctly |
| Routing | 11 | The right tool and streamer are chosen |
| Web answers | 12 | Cited answers for textbook facts, "could not verify" for made-up ones |
| Prompt injection | 3 | Hostile text inside a web page is not obeyed and does not leak the instructions |
| Held-out v1 | 12 | Written by the project owner, run once before any fix (`results/heldout-baseline-v1.json`) |
| Held-out v2 | 16 | Written by the AI with scoring rules fixed in code first (`ask/eval/heldout.py`) |

## Honest limits

- Fixing failures changes what the sets measure: anything that was fixed after it failed is in-sample from then on.
- The AI-written held-out set is probably easier than a human-written one.
- The topic answer key is built from literal word matches, so it favours keyword search and understates what embeddings find through paraphrase.
- Web results vary between runs, and a citation is not proof that the source supports the claim.
- The local 8B model is brittle at routing and classification. Deterministic code backs it up where a failure was found.
