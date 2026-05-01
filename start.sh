#!/bin/bash
# Jarvis RAG — Start script for RunPod RTX 4090

echo "🚀 Starting Jarvis RAG on RunPod RTX 4090..."

# Start Ollama in background
echo "   🧠 Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama
sleep 5

# Verify models
echo "   📦 Verifying models..."
ollama list

# Check GPU
python3 -c "import torch; print(f'   ✅ GPU: {torch.cuda.get_device_name(0)}')" 2>/dev/null || echo "   ⚠️ No GPU detected"

# Run initial ingestion if docs exist
if [ -d "/workspace/docs" ] && [ "$(ls -A /workspace/docs)" ]; then
    echo "   📥 Running initial ingestion..."
    python3 batch_processor.py --mode daily --no-generate
fi

# Start API server
echo "   🌐 Starting API server on port 8000..."
python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1

# Cleanup on exit
trap "kill $OLLAMA_PID" EXIT
