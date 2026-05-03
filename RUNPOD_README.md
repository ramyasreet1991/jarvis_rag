# Jarvis RAG — RunPod RTX 4090 Deployment Guide

## Prerequisites
- RunPod instance with **RTX 4090** (24 GB VRAM)
- Pod template: **RunPod PyTorch 2.x** (has CUDA + Python 3.10+ pre-installed)
- Exposed port: **8000**

---

## Quick Start (3 steps)

### 1. Copy project to RunPod
Upload the project files or clone from GitHub into `/workspace/jarvis-RAG`:
```bash
cd /workspace
git clone https://github.com/ramyasreet1991/jarvis_rag.git jarvis-RAG
cd jarvis-RAG
```

### 2. Run setup (one-time)
```bash
bash setup_runpod.sh
```
This will:
- Install all Python dependencies
- Copy `env.runpod` → `.env`
- Create data directories under `/workspace/`
- Install and start Ollama
- Pull `qwen2.5:32b` LLM (~18 GB)
- Pre-download `BAAI/bge-large-en-v1.5` embeddings (~1 GB)
- Pre-download `BAAI/bge-reranker-large` reranker (~1 GB)
- Verify GPU is detected

### 3. Start the API
```bash
bash start_runpod.sh
```
Or manually:
```bash
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --workers 1
```

---

## Environment Configuration

All settings are in `.env` (copied from `env.runpod`). Key values:

| Variable | Default (RunPod) | Description |
|---|---|---|
| `LOCAL_LLM_MODEL` | `qwen2.5:32b` | Main LLM (~18 GB VRAM) |
| `LOCAL_LLM_CTX` | `8192` | Context window (tokens) |
| `USE_HF_EMBED` | `true` | Direct CUDA embeddings (bypass Ollama) |
| `LOCAL_EMBED_MODEL` | `BAAI/bge-large-en-v1.5` | Embedding model (1024-dim) |
| `LOCAL_RERANK_MODEL` | `BAAI/bge-reranker-large` | Reranker model |
| `BATCH_SIZE` | `64` | Embedding batch size |
| `CHUNK_SIZE` | `1024` | Text chunk size |
| `APP_API_KEY` | `jarvis-runpod-key` | API authentication key |

To change the LLM model, edit `.env` and restart:
```bash
# Example: switch to a lighter model for faster responses
LOCAL_LLM_MODEL=llama3.1:8b
LOCAL_LLM_CTX=4096
```

---

## VRAM Budget (RTX 4090 — 24 GB)

| Component | Model | VRAM |
|---|---|---|
| LLM | qwen2.5:32b (Q4) | ~18 GB |
| Embeddings | bge-large-en-v1.5 | ~1 GB |
| Reranker | bge-reranker-large | ~1 GB |
| KV Cache + buffers | — | ~4 GB |
| **Total** | | **~24 GB** |

**Alternative LLMs that fit in 24 GB:**
```
llama3.1:8b         ~5 GB   (fast, good for testing)
mistral:7b          ~4 GB   (fast, general purpose)
deepseek-r1:14b     ~8 GB   (strong reasoning)
qwen2.5:32b         ~18 GB  (recommended — best quality/fit)
```

---

## API Endpoints

Base URL: `https://<pod-id>-8000.proxy.runpod.net`

| Endpoint | Auth | Description |
|---|---|---|
| `GET /health` | None | Health + GPU status |
| `GET /stats` | API Key | Knowledge base stats |
| `POST /query` | API Key | Query KB, get cited answer |
| `POST /generate` | API Key | Generate content from KB |
| `POST /ingest` | API Key | Add content to KB |
| `GET /sources` | API Key | List vetted sources |

All authenticated endpoints require header: `X-API-Key: jarvis-runpod-key`

### Example: Health check
```bash
curl https://<pod-id>-8000.proxy.runpod.net/health
```

### Example: Query
```bash
curl -X POST https://<pod-id>-8000.proxy.runpod.net/query \
  -H "X-API-Key: jarvis-runpod-key" \
  -H "Content-Type: application/json" \
  -d '{"question": "What are the latest AI agent frameworks?", "top_k": 5}'
```

### Example: Generate YouTube Shorts script
```bash
curl -X POST https://<pod-id>-8000.proxy.runpod.net/generate \
  -H "X-API-Key: jarvis-runpod-key" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "AI agents in 2025",
    "content_type": "youtube_shorts",
    "tone": "technical"
  }'
```

---

## Troubleshooting

**Ollama not responding:**
```bash
pkill ollama; ollama serve &>/dev/null & sleep 3
ollama list
```

**Out of VRAM:**
```bash
# Switch to a smaller model
sed -i 's/qwen2.5:32b/llama3.1:8b/' .env
ollama pull llama3.1:8b
# Restart the API
```

**Slow first request:**
Normal — models load into VRAM on the first request. Subsequent requests are fast.

**Port not accessible:**
Ensure port 8000 is exposed in your RunPod pod settings under **"Expose HTTP Ports"**.
