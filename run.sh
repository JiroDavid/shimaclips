#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "backend/.venv not found. Run: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "frontend/node_modules not found. Run: cd frontend && npm install" >&2
  exit 1
fi
if [ ! -f "$ROOT/backend/.env" ]; then
  echo "Warning: backend/.env is missing. Copy backend/.env.example to backend/.env and fill in your Twitch credentials." >&2
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - EXIT INT TERM
  for pid in $BACKEND_PID $FRONTEND_PID; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  for pid in $BACKEND_PID $FRONTEND_PID; do
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 -- "-$pid" 2>/dev/null || break
      sleep 0.3
    done
    kill -KILL -- "-$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

(cd "$ROOT/backend" && exec setsid .venv/bin/uvicorn main:app --port "$BACKEND_PORT") &
BACKEND_PID=$!
(cd "$ROOT/frontend" && exec setsid npm run dev -- -p "$FRONTEND_PORT") &
FRONTEND_PID=$!

echo "Shimaclips is running at http://localhost:$FRONTEND_PORT (Ctrl+C to stop)"

wait -n || true
