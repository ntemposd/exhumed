#!/usr/bin/env bash
# EXHUMED - Setup Script (Unix/macOS)
set -euo pipefail

echo "=================================================="
echo " EXHUMED - Setup (Unix/macOS)"
echo "=================================================="
echo ""

if ! command -v python >/dev/null 2>&1; then
  echo "ERROR: Python 3.9+ is required and was not found in PATH."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required for the Next.js frontend and was not found in PATH."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment in .venv ..."
  python -m venv .venv
else
  echo "Reusing existing .venv environment."
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "Upgrading pip tooling ..."
python -m pip install --upgrade pip setuptools wheel

echo "Installing backend dependencies ..."
pip install -r backend/requirements.txt

echo "Installing Next.js frontend dependencies ..."
(
  cd frontend
  npm install
)

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Update it with your real credentials."
else
  echo ".env already exists."
fi

echo ""
echo "Setup complete."
echo ""
echo "Start backend:"
echo "  ./.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"
echo "Start frontend (new terminal):"
echo "  cd frontend && npm run dev"
echo ""
