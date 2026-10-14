# Shimaclips

Download a streamer's top Twitch clips for a specific month or date range.

## Setup
1. Create a free app at https://dev.twitch.tv/console (OAuth redirect `http://localhost`, category Other) and copy the client ID and secret.
2. `cp backend/.env.example backend/.env` and fill in both values.
3. Backend: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/uvicorn main:app --reload`
4. Frontend: `cd frontend && npm install && npm run dev`, then open http://localhost:3000

## Tests
`cd backend && .venv/bin/pytest`
