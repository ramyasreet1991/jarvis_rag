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
FOLDER="jarvis-rag"          # folder created on extraction
STAGING="/tmp/${FOLDER}"     # temp staging area

echo "══════════════════════════════════════════════"
echo "  Jarvis RAG — Building $ARTIFACT"
echo "══════════════════════════════════════════════"

# ── Remove old artifact and staging ──────────────────────────────────────────
rm -f "$ARTIFACT"
rm -rf "$STAGING"

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
    test_api.sh
    RUNPOD_README.md

    # Docs
    docs/
)

# ── Validate all files exist before staging ───────────────────────────────────
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

# ── Copy files into staging folder ────────────────────────────────────────────
echo ""
echo "▶ Staging into $FOLDER/..."
mkdir -p "$STAGING"
for f in "${SOURCE_FILES[@]}"; do
    if [ -d "$f" ]; then
        cp -r "$f" "$STAGING/"
    else
        cp "$f" "$STAGING/"
    fi
done

# Strip unwanted files from staging
find "$STAGING" -name "*.pyc" -delete
find "$STAGING" -name ".DS_Store" -delete
find "$STAGING" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
find "$STAGING" -name "*.log" -delete
find "$STAGING" -name ".env" -delete

echo "  ✅ Staged"

# ── Zip from /tmp so the folder is the root inside the zip ───────────────────
echo ""
echo "▶ Building $ARTIFACT..."
cd /tmp
zip -r "$SCRIPT_DIR/$ARTIFACT" "$FOLDER/" --quiet
cd "$SCRIPT_DIR"

# ── Cleanup staging ───────────────────────────────────────────────────────────
rm -rf "$STAGING"

# ── Summary ───────────────────────────────────────────────────────────────────
FILE_COUNT=$(unzip -l "$ARTIFACT" | tail -1 | awk '{print $2}')
SIZE=$(ls -lh "$ARTIFACT" | awk '{print $5}')

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ $ARTIFACT built successfully"
echo "     Folder : $FOLDER/"
echo "     Files  : $FILE_COUNT"
echo "     Size   : $SIZE"
echo ""
echo "  Deploy on RunPod:"
echo "    1. Upload $ARTIFACT to /workspace"
echo "    2. unzip $ARTIFACT          # creates /workspace/$FOLDER/"
echo "    3. cd $FOLDER && bash setup_runpod.sh"
echo "    4. bash start_runpod.sh"
echo "══════════════════════════════════════════════"
