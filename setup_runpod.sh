#!/bin/bash
# ── Jarvis RAG — RunPod RTX 4090 Setup ───────────────────────────────────────
# Run once after copying the project to /workspace:
#   bash setup_runpod.sh
# ─────────────────────────────────────────────────────────────────────────────
set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "══════════════════════════════════════════════"
echo "  Jarvis RAG — RunPod Setup"
echo "══════════════════════════════════════════════"

# ── 1. Python deps ────────────────────────────────────────────────────────────
echo ""
echo "▶ Installing Python dependencies..."
pip install -q --upgrade pip setuptools wheel   # setuptools required by openai-whisper build
pip install -r requirements.txt
echo "  ✅ Dependencies installed"

# ── 2. .env ───────────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp env.runpod .env
    echo "  ✅ .env created from env.runpod"
else
    echo "  ⚠️  .env already exists — skipping (delete it to reset)"
fi

# ── 3. Directories ────────────────────────────────────────────────────────────
echo ""
echo "▶ Creating data directories..."
mkdir -p /workspace/data/chroma_db \
         /workspace/output \
         /workspace/logs \
         /workspace/backups
echo "  ✅ Directories ready"

# ── 4. System dependencies ───────────────────────────────────────────────────
echo ""
echo "▶ Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq zstd curl wget pciutils lshw
echo "  ✅ System dependencies ready"

# ── 5. Ollama ─────────────────────────────────────────────────────────────────
echo ""
echo "▶ Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    echo "  Installing Ollama..."
    curl -fsSL https://ollama.ai/install.sh | sh
fi

if ! pgrep -x ollama &>/dev/null; then
    echo "  Starting Ollama..."
    ollama serve &>/dev/null &
    sleep 5
fi
echo "  ✅ Ollama running"

# ── 6. Pull LLM model ─────────────────────────────────────────────────────────
LLM_MODEL=$(grep "^LOCAL_LLM_MODEL=" .env | cut -d= -f2 | tr -d '"')
LLM_MODEL="${LLM_MODEL:-qwen2.5:32b}"

echo ""
echo "▶ Pulling LLM: $LLM_MODEL (this may take a few minutes)..."
ollama pull "$LLM_MODEL"
echo "  ✅ $LLM_MODEL ready"

# ── 7. HuggingFace embedding model (pre-download) ────────────────────────────
EMBED_MODEL=$(grep "^LOCAL_EMBED_MODEL=" .env | cut -d= -f2 | tr -d '"')
EMBED_MODEL="${EMBED_MODEL:-BAAI/bge-large-en-v1.5}"

echo ""
echo "▶ Pre-downloading embedding model: $EMBED_MODEL..."
python3 -c "
from sentence_transformers import SentenceTransformer
print('  Downloading $EMBED_MODEL...')
model = SentenceTransformer('$EMBED_MODEL')
print('  ✅ Embedding model cached')
"

# ── 8. HuggingFace reranker model (pre-download) ─────────────────────────────
RERANK_MODEL=$(grep "^LOCAL_RERANK_MODEL=" .env | cut -d= -f2 | tr -d '"')
RERANK_MODEL="${RERANK_MODEL:-BAAI/bge-reranker-large}"

echo ""
echo "▶ Pre-downloading reranker model: $RERANK_MODEL..."
python3 -c "
from sentence_transformers import CrossEncoder
print('  Downloading $RERANK_MODEL...')
model = CrossEncoder('$RERANK_MODEL', device='cuda')
print('  ✅ Reranker model cached')
"

# ── 9. Verify GPU ─────────────────────────────────────────────────────────────
echo ""
echo "▶ Verifying GPU..."
python3 -c "
import torch
if torch.cuda.is_available():
    name = torch.cuda.get_device_name(0)
    vram = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f'  ✅ GPU: {name} ({vram:.1f} GB VRAM)')
else:
    print('  ⚠️  No CUDA GPU detected — check RunPod GPU selection')
"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ Setup complete!"
echo ""
echo "  Start the API:"
echo "  python -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1"
echo ""
echo "  Health check:"
echo "  curl http://localhost:8000/health"
echo "══════════════════════════════════════════════"
