<p align="center">
  <img src="assets/logo.svg" alt="Shimaclips" width="480">
</p>

<p align="center">
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

Browse a streamer's Twitch clips on a calendar and download the best ones.

## How it works
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

## Ask about clips (AI)
Ask a question about a streamer's clips in plain English and get an answer with clickable, cited clips. It runs fully locally and costs nothing per question.

Three kinds of question are handled differently:
- **Structured** ("How many clips this month?", "Top 10 clips last week"): a local model only picks a tool and its arguments. Our code resolves dates ("this month", "last 7 days", "March 2025") and runs a read-only, validated query, so numbers always come from the database and never from the model.
- **Semantic** ("Find clips where he talks about boxing"): hybrid search over clip transcripts. Embeddings (`nomic-embed-text`) and keyword search (SQLite FTS5) are combined with reciprocal rank fusion. A local model (`llama3.1:8b`) answers using only the retrieved clips and cites them.
- **Mixed** ("When did he do his island stream?"): the same search, plus the dates of the cited clips computed in code. A clip date is when the clip was made, not necessarily when the stream happened.

When nothing matches, it says so. If the rarest word in the question appears nowhere in the library and the best match is not strong, it abstains and explains why instead of guessing.

Limits to keep in mind:
- Only a subset is transcribed: for jasontheween, the top clips by views from each of the busiest days of 2026, plus a few from every other day (about 2,400 clips). Counts and top lists use the whole database, but topic search covers only the transcribed clips.
- Transcripts come from audio only (faster-whisper `small.en`), so chat messages and on-screen text are invisible, and names or slang can be misheard.
- The local 8B model can word answers badly. The cited clips and the dates are the reliable part.

Build the index (needs Ollama running with `ollama pull nomic-embed-text` and `ollama pull llama3.1:8b`, and an NVIDIA GPU for fast transcription):
1. Transcribe: `cd backend && LD_LIBRARY_PATH=$(.venv/bin/python -c "import nvidia.cublas.lib as a,nvidia.cudnn.lib as b;print(a.__path__[0]+':'+b.__path__[0])") .venv/bin/python -m ask.build_transcripts 3000` (resumable; edit the streamer and date in `ask/build_transcripts.py`).
2. Index: `.venv/bin/python -m ask.build_index`

Evaluation: `cd backend && .venv/bin/python -m ask.evaluate` runs a golden set (22 structured, 10 semantic, 2 mixed, 3 abstention questions) and saves results to `backend/ask/eval/results/`. The structured checks compare against independent SQL. For the topic questions, the answer key is every clip in the library whose title or transcript literally contains the topic word, built by `ask/eval/build_golden.py`, so it does not depend on the search under test. Because that key is word-based, it favours keyword search and understates what embeddings find through paraphrase.

Latest results (12 topic questions, top 5 results):

| Retrieval | hit@5 | precision@5 | MRR |
|---|---|---|---|
| Title embeddings | 0.67 | 0.42 | 0.67 |
| Transcript embeddings | 0.67 | 0.53 | 0.67 |
| Keyword (BM25) | 1.00 | 0.90 | 1.00 |
| Hybrid (used by the app) | 1.00 | 0.73 | 0.88 |

Structured questions: 22 of 22 exact, but the first run of the 10 harder phrasings scored 6 of 10 before fixes (saved as `baseline-structured-v1.json`), so treat 22 of 22 as in-sample. The model once silently rewrote "month before last" as "last month", which is why dates are resolved in code and the prompt requires the user's exact date words. Abstention: 2 of 2 on topics with no mentions (poker, Florida); a topic with two passing mentions (chess) is answered from those two clips. In the end-to-end answers, 74 percent of cited clips on topic questions are relevant. A typical answer costs about 1,000 local tokens and 2 seconds.

## Setup
1. Create a free app at https://dev.twitch.tv/console (OAuth redirect `http://localhost`, category Other) and copy the client ID and secret.
2. `cp backend/.env.example backend/.env` and fill in both values.
3. Backend deps: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
4. Frontend deps: `cd frontend && npm install`

## Run
One command: `./run.sh`, then open http://localhost:3000. Ctrl+C stops both servers.

Or in two terminals:
- Backend: `cd backend && .venv/bin/uvicorn main:app --reload --timeout-graceful-shutdown 3`
- Frontend: `cd frontend && npm run dev`

`--timeout-graceful-shutdown 3` is needed with `--reload`, otherwise open event streams (SSE) keep the old process from shutting down on reload.

Set `SHIMACLIPS_CRAWLER=0` to start the backend without the background watchlist crawler.

## Tests
- Backend: `cd backend && .venv/bin/pytest`
- Frontend: `cd frontend && npm run test`
