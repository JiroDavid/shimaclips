# Shimaclips

Browse a streamer's Twitch clips on a calendar and download the best ones.

## How it works
1. Search for a streamer. Matches appear with their profile pictures so you can pick the right channel.
2. A heatmap shows clip density by year, month and week. Cells that are still loading show an approximate count like `1,000+` and are already clickable once some of their clips are loaded.
3. Year chips above the calendar choose which years to load. Toggling a year loads it in the background; older years show approximate cells first.
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
