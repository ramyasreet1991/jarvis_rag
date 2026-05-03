#!/bin/bash
# ── Jarvis RAG — RunPod Start Script ─────────────────────────────────────────
# Run after setup_runpod.sh has been executed once.
#   bash start_runpod.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

PROJECT_DIR="/workspace/jarvis-RAG"
cd "$PROJECT_DIR" || { echo "❌ Project not found at $PROJECT_DIR"; exit 1; }

# ── Verify .env exists ────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "❌ .env not found. Run setup_runpod.sh first."
    exit 1
fi

# ── Ensure Ollama is running ──────────────────────────────────────────────────
if ! pgrep -x ollama &>/dev/null; then
    echo "▶ Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 5
    echo "  ✅ Ollama started"
fi

# ── Check GPU ─────────────────────────────────────────────────────────────────
python3 -c "
import torch
if torch.cuda.is_available():
    name = torch.cuda.get_device_name(0)
    vram_total = torch.cuda.get_device_properties(0).total_memory / 1e9
    vram_free  = (torch.cuda.get_device_properties(0).total_memory
                  - torch.cuda.memory_allocated(0)) / 1e9
    print(f'  GPU: {name}  |  VRAM: {vram_free:.1f}/{vram_total:.1f} GB free')
else:
    print('  ⚠️  No CUDA GPU — running on CPU (slow)')
"

# ── Start API ─────────────────────────────────────────────────────────────────
PORT=$(grep "^APP_PORT=" .env | cut -d= -f2)
PORT="${PORT:-8000}"

echo ""
echo "══════════════════════════════════════════════"
echo "  Starting Jarvis RAG API on port $PORT"
echo "  Docs:   http://localhost:$PORT/docs"
echo "  Health: http://localhost:$PORT/health"
echo "══════════════════════════════════════════════"
echo ""

python -m uvicorn api_server:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 1 \
    --log-level info
