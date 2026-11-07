# Shimaclips

Browse a streamer's Twitch clips on a calendar and download the best ones.

## How it works
1. Enter a streamer's name.
2. A heatmap shows clip density by year, month and week.
3. Click a month or a day to see its top clips.
4. Reels show the top clips for this month, this year and most viewed of all time.
5. Select clips across different periods and download them in one batch.

The first load of a very popular streamer can take a few minutes. Later visits are fast because clips are cached in `backend/shimaclips.db`, which is gitignored.

## Setup
1. Create a free app at https://dev.twitch.tv/console (OAuth redirect `http://localhost`, category Other) and copy the client ID and secret.
2. `cp backend/.env.example backend/.env` and fill in both values.
3. Backend deps: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
4. Frontend deps: `cd frontend && npm install`

## Run
One command: `./run.sh`, then open http://localhost:3000. Ctrl+C stops both servers.

Or in two terminals:
- Backend: `cd backend && .venv/bin/uvicorn main:app --reload`
- Frontend: `cd frontend && npm run dev`

## Tests
- Backend: `cd backend && .venv/bin/pytest`
- Frontend: `cd frontend && npm run test`
