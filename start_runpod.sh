#!/bin/bash
# ── Jarvis RAG — RunPod Start Script ─────────────────────────────────────────
# Run after setup_runpod.sh has been executed once.
#   bash start_runpod.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# ── Verify .env exists ────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "❌ .env not found. Run setup_runpod.sh first."
    exit 1
fi

# ── Point Ollama at network volume ────────────────────────────────────────────
export OLLAMA_MODELS=/workspace/ollama/models
mkdir -p "$OLLAMA_MODELS"

# ── Ensure Ollama is running ──────────────────────────────────────────────────
if ! pgrep -x ollama &>/dev/null; then
    echo "▶ Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 5
    echo "  ✅ Ollama started"
fi

# ── Start Qdrant server (port 6333 — Web UI at /dashboard) ───────────────────
if ! pgrep -x qdrant &>/dev/null; then
    echo "▶ Starting Qdrant server..."
    mkdir -p /workspace/data/qdrant_db /workspace/logs
    nohup qdrant --config-path "$PROJECT_DIR/qdrant_config.yaml" \
        > /workspace/logs/qdrant.log 2>&1 &
    # Wait until Qdrant HTTP is ready
    for i in $(seq 1 15); do
        if curl -sf http://localhost:6333/healthz &>/dev/null; then
            echo "  ✅ Qdrant ready  → http://localhost:6333/dashboard"
            break
        fi
        sleep 1
    done
else
    echo "  ✅ Qdrant already running"
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

# ── Start ingestion scheduler (every 4 hours) ─────────────────────────────────
pkill -f run_scheduler.py 2>/dev/null || true
mkdir -p /workspace/logs
nohup python run_scheduler.py \
    --interval-hours 4 \
    --days 1 \
    > /workspace/logs/scheduler.log 2>&1 &
SCHED_PID=$!
echo "  ✅ Scheduler started (PID $SCHED_PID, every 4h)"

echo ""
echo "══════════════════════════════════════════════"
echo "  Starting Jarvis RAG API on port $PORT"
echo ""
echo "  API     → http://localhost:$PORT/docs"
echo "  Health  → http://localhost:$PORT/health"
echo "  Qdrant  → http://localhost:6333/dashboard"
echo ""
echo "  RunPod Web UI access:"
echo "    Expose port 6333 → click HTTP Service link + /dashboard"
echo "  SSH tunnel:"
echo "    ssh -L 6333:localhost:6333 root@<pod-ip>"
echo "    then → http://localhost:6333/dashboard"
echo ""
echo "  Scheduler: PID $SCHED_PID (every 4h)"
echo "  Logs:   /workspace/logs/"
echo "══════════════════════════════════════════════"
echo ""

python -m uvicorn api_server:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --workers 1 \
    --log-level info
