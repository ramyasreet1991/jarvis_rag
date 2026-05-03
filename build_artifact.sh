#!/bin/bash
# ── Jarvis RAG — Build artifact.zip for RunPod deployment ────────────────────
# Run after any code changes:
#   bash build_artifact.sh
#
# Packages all source code + RunPod scripts into artifact.zip
# Excludes: local dev files, caches, secrets, test files
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ARTIFACT="artifact.zip"

echo "══════════════════════════════════════════════"
echo "  Jarvis RAG — Building $ARTIFACT"
echo "══════════════════════════════════════════════"

# ── Remove old artifact ───────────────────────────────────────────────────────
rm -f "$ARTIFACT"

# ── Files to include ──────────────────────────────────────────────────────────
SOURCE_FILES=(
    # Core pipeline
    api_server.py
    rag_engine.py
    config.py
    content_extractor.py
    content_generator.py
    source_vetter.py
    airflow_rag_dag.py
    batch_processor.py
    __init__.py
    setup.py

    # Dependencies
    requirements.txt

    # Config
    sources_config.json

    # RunPod deployment
    env.runpod
    setup_runpod.sh
    start_runpod.sh
    RUNPOD_README.md

    # Docs
    docs/
)

# ── Validate all files exist before zipping ───────────────────────────────────
echo ""
echo "▶ Validating files..."
MISSING=0
for f in "${SOURCE_FILES[@]}"; do
    if [ ! -e "$f" ]; then
        echo "  ❌ Missing: $f"
        MISSING=$((MISSING + 1))
    fi
done

if [ "$MISSING" -gt 0 ]; then
    echo ""
    echo "❌ Aborting — $MISSING file(s) missing. Fix above and retry."
    exit 1
fi
echo "  ✅ All files present"

# ── Build zip ─────────────────────────────────────────────────────────────────
echo ""
echo "▶ Building $ARTIFACT..."
zip -r "$ARTIFACT" "${SOURCE_FILES[@]}" \
    --exclude "*.pyc" \
    --exclude "*__pycache__*" \
    --exclude "*.DS_Store" \
    --exclude "*.env" \
    --exclude "*.log" \
    --exclude "*test_*" \
    --exclude "*_test.py"

# ── Summary ───────────────────────────────────────────────────────────────────
FILE_COUNT=$(unzip -l "$ARTIFACT" | tail -1 | awk '{print $2}')
SIZE=$(ls -lh "$ARTIFACT" | awk '{print $5}')

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ $ARTIFACT built successfully"
echo "     Files : $FILE_COUNT"
echo "     Size  : $SIZE"
echo ""
echo "  Deploy on RunPod:"
echo "    1. Upload $ARTIFACT to /workspace"
echo "    2. unzip $ARTIFACT -d /workspace/jarvis-rag"
echo "    3. cd /workspace/jarvis-rag && bash setup_runpod.sh"
echo "    4. bash start_runpod.sh"
echo "══════════════════════════════════════════════"
