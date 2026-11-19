<p align="center">
  <img src="assets/banner.svg" alt="Shimaclips: an AI assistant for Twitch clips" width="100%">
</p>

<p align="center">
  <img alt="Ollama" src="https://img.shields.io/badge/Ollama-local%20LLM-000000?logo=ollama&logoColor=white">
  <img alt="Llama 3.1" src="https://img.shields.io/badge/llama3.1-8B-0467DF">
  <img alt="faster-whisper" src="https://img.shields.io/badge/faster--whisper-speech%20to%20text-4B5563">
  <img alt="RAG" src="https://img.shields.io/badge/RAG-hybrid%20search-7c3aed">
  <img alt="Next.js 16" src="https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white">
  <img alt="React 19" src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black">
  <img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white">
  <img alt="Tailwind CSS 4" src="https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/Python-3-3776AB?logo=python&logoColor=white">
  <img alt="SQLite" src="https://img.shields.io/badge/SQLite-cache-003B57?logo=sqlite&logoColor=white">
  <img alt="Twitch Helix API" src="https://img.shields.io/badge/Twitch-Helix%20API-9146FF?logo=twitch&logoColor=white">
  <img alt="yt-dlp" src="https://img.shields.io/badge/yt--dlp-downloads-FF0000?logo=youtube&logoColor=white">
  <img alt="Local first" src="https://img.shields.io/badge/runs-locally-7c3aed">
</p>

# Shimaclips

An AI chat assistant for Twitch clips. Ask in plain English and it finds, counts and shows a streamer's clips, tells you who a streamer is, and answers general Twitch questions with cited sources. It runs on local models on your own computer, and also has a calendar view for browsing and downloading clips by month.

Things you can ask:
- "Top 10 clips for each month of 2026 for jasontheween" gives a rewind, with a button to download them all.
- "How many clips did shroud get in 2025?" and "How many views did jasontheween average this month?" are answered from the database, never from the model's memory.
- "Who is stableronaldo?" shows their Twitch profile and their most viewed clips.
- "Find clips where he talks about boxing" searches what was said in the clips. A streamer who has not been transcribed yet is transcribed automatically, with a progress bar.
- "What are 7TV emotes?" is answered from the web, with the sources listed.

## Ask about clips (AI)
The home page is a chat box. Ask in plain English and get an answer with clickable, cited clips. It runs fully locally and costs nothing per question. The calendar view lives at `/browse` and is reachable from the small streamer lookup under the chat box.

A sidebar on the left lists your past chats (Recents). Click one to reopen it exactly as you left it and keep asking, start a new one with "New chat" or by clicking the logo, and delete one with the x that appears on hover. Chats are stored only on your computer, in the same SQLite database as the clip cache (`backend/shimaclips.db`, gitignored), so they survive restarts and browser changes. The sidebar can be collapsed, and "Manual Streamer Search" in it opens a streamer lookup that takes you to that streamer's calendar view.

You do not need to pick a streamer first. Name one in the question ("top 10 clips for each month of 2026 for jasontheween") and it is detected and checked against Twitch. If the name is not a real channel, it suggests the closest matches. After the first answer the streamer is remembered for follow-up questions.

What it can do:
- **Structured** ("How many clips this month?", "Top 10 clips last week", "Top 10 clips for each month of 2026"): a local model only picks a tool and its arguments. Our code resolves dates ("this month", "last 7 days", "March 2025") and runs a read-only, validated query, so numbers come from the database and never from the model. The monthly view can download all its clips in one batch.
- **Semantic** ("Find clips where he talks about boxing"): hybrid search over clip transcripts. Embeddings (`nomic-embed-text`) and keyword search (SQLite FTS5) are combined with reciprocal rank fusion. A local model (`llama3.1:8b`) answers using only the retrieved clips and cites them.
- **Mixed** ("When did he do his island stream?"): the same search, plus the dates of the cited clips computed in code. A clip date is when the clip was made, not necessarily when the stream happened.
- **Off-topic questions** ("who won the NBA") are refused by a topic guard that runs first.
- **General Twitch questions** ("what are 7TV emotes", "did X win a streamer award") are answered from the web, with the sources listed under the answer. See Web access below. If a streamer is named, their most viewed clips from our system follow the answer. When the sources do not say, it answers "I could not verify it" instead of guessing.
- **Abstention:** if the rarest word in a topic question appears nowhere in the library and the best match is not strong, it says so instead of guessing.

Limits to keep in mind:
- Counts and top lists work for any streamer (loaded on demand from Twitch; a period that is not fully loaded is reported as "at least N"). Topic search covers only transcribed clips. For a new streamer, the first topic question starts transcribing automatically (see Automatic transcription below). jasontheween was transcribed by hand: the top clips by views from each of the busiest days of 2026 plus a few from every other day (about 2,400 clips).
- Transcripts come from audio only (faster-whisper `small.en`), so chat messages and on-screen text are invisible, and names or slang can be misheard.
- One streamer per question. Suggestions for a mistyped name are ranked by how closely they match what was typed, because Twitch search cannot rank by popularity.
- The local 8B model can word answers badly or skip a tool call. Safety nets cover this (a topic-search fallback and a known-streamer check), and the cited clips and dates are the reliable part.

Automatic transcription: asking a topic question about a streamer with no transcripts starts transcribing them in the background, with a progress bar in the chat. It covers the top clips of the last 12 months, up to 1,000 clips (about 20 to 25 minutes on an RTX 3060), and re-indexes every 50 clips, so topic search works on the part that is done while the rest continues. Nothing is transcribed until a question needs it. One job runs at a time. Set `SHIMACLIPS_TRANSCRIBE=0` to turn this off. Without an NVIDIA GPU it falls back to the CPU, which is much slower.

Web access: general Twitch questions are answered from a web search (`ddgs`, which queries DuckDuckGo) and the text of the top three pages, summarised by the local model, which may only use those sources and must cite them. What leaves your computer: the text of the question, sent to the search engine, and ordinary page requests to the sites found. Answers are cached for 24 hours, so a repeated question makes no network request. Safeguards: page text is treated as untrusted data (the model is told never to follow instructions inside it, has no tools, and its output is shown as plain text); fetches only go to public http or https addresses on ports 80 or 443 (private, local and link-local addresses are refused, including via redirects) with size and time limits; only the first three pages are read. Search is unreliable at times, so it retries, and if it still fails the answer says so. Set `SHIMACLIPS_WEB=0` to turn web access off.

Build the index (needs Ollama running with `ollama pull nomic-embed-text` and `ollama pull llama3.1:8b`, and an NVIDIA GPU for fast transcription):
1. Transcribe: `cd backend && LD_LIBRARY_PATH=$(.venv/bin/python -c "import nvidia.cublas.lib as a,nvidia.cudnn.lib as b;print(a.__path__[0]+':'+b.__path__[0])") .venv/bin/python -m ask.build_transcripts 3000` (resumable; edit the streamer and date in `ask/build_transcripts.py`).
2. Index: `.venv/bin/python -m ask.build_index`

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

## Calendar view
The calendar lives at `/browse`. Open it with "Manual Streamer Search" in the sidebar, or by clicking a streamer link under an answer. The home page is the chat described above.

1. Search for a streamer. Matches appear with their profile pictures so you can pick the right channel.
2. A heatmap shows clip density by year, month and week. Cells that are still loading show an approximate count like `1,000+` and are already clickable once some of their clips are loaded.
3. Older years show approximate cells; the current and previous year load exactly.
4. Click a month or a day to see its top clips.
5. Reels show the top clips for this month, this year and most viewed of all time. They are fetched live from Twitch, so they appear within seconds even for very popular streamers. The all-time reel can be filtered by year, and reels can be sorted by most viewed or newest (newest needs an exactly loaded period).
6. Hover a clip card for about 400 ms (or focus it with the keyboard) to play a muted video preview from the Twitch clip embed. Sweeping the pointer across cards starts nothing.
7. Select clips across different periods and download them in one batch.

Exact per-day counts need a full crawl, and Twitch only returns about 1,000 clips per query, so the first load of a very popular streamer can take a long time (the app splits busy periods into days and hours). Everything is cached in `backend/shimaclips.db` (gitignored), so later visits are fast and only recent clips are refetched.

## Watchlist
A short list of streamers is kept preloaded in the background while the app is running. It lives in the local database (not in the repo) and is seeded once with a starting list. The crawler only runs while the backend is running, always yields to a streamer you open yourself, and resumes where it left off. Use the watchlist panel in the app to add, pause or remove streamers, and the "Keep this streamer up to date" toggle in the header to add or remove the open streamer. The same actions are available through the `/api/watchlist` endpoints. Crawling happens only while `./run.sh` (or the backend) is running.

## Setup
1. Create a free app at https://dev.twitch.tv/console (OAuth redirect `http://localhost`, category Other) and copy the client ID and secret.
2. `cp backend/.env.example backend/.env` and fill in both values.
3. Backend deps: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
4. Frontend deps: `cd frontend && npm install`
5. For the AI features, install Ollama (https://ollama.com), then run `ollama pull llama3.1:8b` and `ollama pull nomic-embed-text`, and install `ffmpeg` (`sudo apt install ffmpeg` on Ubuntu or WSL). An NVIDIA GPU makes transcription fast. Without one it falls back to the CPU, which is much slower. Web answers need an internet connection.

## Run
One command: `./run.sh`, then open http://localhost:3000 (the ask page; the calendar is at http://localhost:3000/browse). Ctrl+C stops both servers.

Or in two terminals:
- Backend: `cd backend && .venv/bin/uvicorn main:app --reload --timeout-graceful-shutdown 3`
- Frontend: `cd frontend && npm run dev`

`--timeout-graceful-shutdown 3` is needed with `--reload`, otherwise open event streams (SSE) keep the old process from shutting down on reload.

Set `SHIMACLIPS_CRAWLER=0` to start the backend without the background watchlist crawler.

## Tests
- Backend: `cd backend && .venv/bin/pytest`
- Frontend: `cd frontend && npm run test`
