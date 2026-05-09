#!/usr/bin/env bash
# Restart the drone_management dashboard + mock drone in a tmux session.
#
# Usage from any directory:
#   bash scripts/restart.sh              # kill + recreate tmux only
#   bash scripts/restart.sh --pull       # git pull, then restart
#   bash scripts/restart.sh --fresh      # post-pod-restart: apt + tmux + alembic + restart
#   bash scripts/restart.sh --dns        # rewrite /etc/resolv.conf to public DNS first
#   bash scripts/restart.sh --fresh --pull --dns   # combine as needed

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PULL=0
FRESH=0
FIX_DNS=0
for arg in "$@"; do
  case "$arg" in
    --pull) PULL=1 ;;
    --fresh) FRESH=1 ;;
    --dns) FIX_DNS=1 ;;
    -h|--help)
      sed -n '2,10p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "unknown flag: $arg" >&2
      echo "use --help for usage" >&2
      exit 2
      ;;
  esac
done

if [ "$FIX_DNS" -eq 1 ]; then
  echo "[dns] writing public DNS to /etc/resolv.conf"
  printf "nameserver 8.8.8.8\nnameserver 1.1.1.1\n" > /etc/resolv.conf
fi

if [ "$FRESH" -eq 1 ]; then
  echo "[fresh] apt-get update + install tmux"
  apt-get update -qq
  apt-get install -y tmux >/dev/null
fi

if [ "$PULL" -eq 1 ]; then
  echo "[pull] git pull"
  git pull --ff-only
fi

if [ ! -d ".venv" ]; then
  echo "error: .venv not found at $ROOT/.venv. run 'python3 -m venv .venv && pip install -e \".[dev]\"' first." >&2
  exit 3
fi

if [ "$FRESH" -eq 1 ]; then
  echo "[fresh] alembic upgrade head"
  # shellcheck disable=SC1091
  source .venv/bin/activate
  alembic upgrade head
  deactivate
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "error: tmux not installed. rerun with --fresh." >&2
  exit 4
fi

echo "[tmux] killing existing drone session if any"
tmux kill-session -t drone 2>/dev/null || true

echo "[tmux] starting new drone session"
tmux new -s drone -d
tmux send-keys -t drone "cd $ROOT && source .venv/bin/activate && uvicorn app.main:app --host 0.0.0.0 --port 8000" C-m
tmux split-window -t drone -h
tmux send-keys -t drone "cd $ROOT && source .venv/bin/activate && python -m mock_drone --target 127.0.0.1:14550 --listen 0.0.0.0:14551" C-m

echo "[wait] 4s for uvicorn + mock drone to come up"
sleep 4

echo "[check] /api/config response:"
if curl -fsS http://127.0.0.1:8000/api/config; then
  echo
  echo "[ok] dashboard is up. attach with: tmux attach -t drone"
else
  echo
  echo "[warn] /api/config did not respond. inspect with: tmux attach -t drone"
  exit 5
fi
