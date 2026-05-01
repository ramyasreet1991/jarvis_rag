#!/bin/bash
# ── Jarvis RAG — Local Mac M2 Setup ──────────────────────────────────────────
# Run once:  bash setup_local.sh
# Tested on: macOS + Apple Silicon (M1/M2/M3) + Python 3.13
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC} $*"; }
warn() { echo -e "${YELLOW}  !${NC} $*"; }
fail() { echo -e "${RED}  ✗${NC} $*"; exit 1; }

echo ""
echo "========================================"
echo "  Jarvis RAG — Local Setup (Mac M2)"
echo "========================================"

# ── 1. Python version check ───────────────────────────────────────────────────
PYTHON=${PYTHON:-python3.13}
if ! command -v "$PYTHON" &>/dev/null; then
    fail "$PYTHON not found. Install via: brew install python@3.13"
fi
PY_VER=$("$PYTHON" --version 2>&1 | awk '{print $2}')
ok "Python $PY_VER"

# ── 2. Ollama check ───────────────────────────────────────────────────────────
if ! command -v ollama &>/dev/null; then
    fail "Ollama not found. Install: brew install ollama   then   ollama serve"
fi

if ! curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; then
    warn "Ollama is not running. Starting it..."
    ollama serve &>/dev/null &
    sleep 4
fi
ok "Ollama is running"

# ── 3. Pull required Ollama models ───────────────────────────────────────────
REQUIRED_MODELS=("mistral:7b" "nomic-embed-text")

for model in "${REQUIRED_MODELS[@]}"; do
    if ollama list 2>/dev/null | grep -q "^${model}"; then
        ok "Model already pulled: $model"
    else
        echo "  Pulling $model (this may take a few minutes)..."
        ollama pull "$model"
        ok "Pulled: $model"
    fi
done

# ── 4. Create virtual environment ────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment (.venv)..."
    "$PYTHON" -m venv .venv
    ok "Virtual environment created"
else
    ok "Virtual environment already exists"
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ── 5. Upgrade pip ────────────────────────────────────────────────────────────
pip install --upgrade pip --quiet
ok "pip up to date: $(pip --version | awk '{print $2}')"

# ── 6. Install dependencies ───────────────────────────────────────────────────
echo "  Installing requirements-local.txt..."
pip install -r requirements-local.txt --quiet
ok "Dependencies installed"

# ── 7. Verify PyTorch MPS ─────────────────────────────────────────────────────
python3 -c "
import torch
device = 'mps' if torch.backends.mps.is_available() else 'cpu'
print(f'  PyTorch {torch.__version__} | device: {device}')
"
ok "PyTorch OK"

# ── 8. Verify ChromaDB ───────────────────────────────────────────────────────
python3 -c "import chromadb; print(f'  ChromaDB {chromadb.__version__}')" && ok "ChromaDB OK"

# ── 9. Copy .env.local → .env ────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    cp .env.local .env
    ok "Copied .env.local → .env"
else
    warn ".env already exists — not overwriting. Review .env.local for any new variables."
fi

# ── 10. Create local directories ─────────────────────────────────────────────
for dir in data/chroma_db docs output logs backups checkpoints; do
    mkdir -p "$dir"
done
ok "Local directories created"

echo ""
echo "========================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env if you want to add API keys"
echo "    2. Run:  bash start_local.sh"
echo "    3. Test: curl http://localhost:8000/health"
echo "========================================"
