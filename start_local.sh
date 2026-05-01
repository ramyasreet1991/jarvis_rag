#!/bin/bash
# ── Jarvis RAG — Local Start (Mac M2) ────────────────────────────────────────
# Run:  bash start_local.sh
# Assumes setup_local.sh has already been run.
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; exit 1; }

echo ""
echo "========================================"
echo "  Jarvis RAG — Starting Locally"
echo "========================================"

# ── Check venv ────────────────────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    fail "No .venv found. Run: bash setup_local.sh first"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ── Check .env ────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    warn ".env not found — copying from .env.local"
    cp .env.local .env
fi

# ── Ollama ────────────────────────────────────────────────────────────────────
if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "  Starting Ollama..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    sleep 4
    ok "Ollama started (PID $OLLAMA_PID)"
else
    ok "Ollama already running"
fi

# Confirm required models
for model in mistral:7b nomic-embed-text; do
    if ollama list 2>/dev/null | grep -q "^${model}"; then
        ok "Model ready: $model"
    else
        warn "Model not found: $model  →  pulling now..."
        ollama pull "$model"
    fi
done

# ── Detect device ─────────────────────────────────────────────────────────────
DEVICE=$(python3 -c "
import torch
if torch.backends.mps.is_available(): print('mps')
elif torch.cuda.is_available(): print('cuda')
else: print('cpu')
" 2>/dev/null || echo "cpu")
ok "Compute device: $DEVICE"

# ── Start API server ──────────────────────────────────────────────────────────
PORT=${APP_PORT:-8000}
echo ""
echo "  Starting API server on http://localhost:$PORT"
echo "  API key: jarvis-local-key  (set APP_API_KEY in .env to change)"
echo ""
echo "  Press Ctrl+C to stop."
echo "========================================"
echo ""

python3 -m uvicorn api_server:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 1 \
    --reload \
    --reload-exclude "data/*" \
    --reload-exclude "logs/*" \
    --reload-exclude "output/*"
