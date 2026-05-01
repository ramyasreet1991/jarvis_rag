# Jarvis RAG — Dockerfile for RunPod RTX 4090
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Prevent interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y     python3.11 python3-pip python3.11-venv     wget curl git ffmpeg     libsndfile1     && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1
RUN update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# Install Ollama
RUN curl -fsSL https://ollama.ai/install.sh | sh

# Set working directory
WORKDIR /workspace

# Copy requirements first (for layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download models (bakes into image for faster cold starts)
RUN ollama serve &     sleep 5 &&     ollama pull llama3.1:8b &&     ollama pull nomic-embed-text &&     ollama pull mistral:7b-instruct &&     pkill ollama || true

# Download cross-encoder model
RUN python3 -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Copy application code
COPY . /workspace/

# Create directories
RUN mkdir -p /workspace/data /workspace/docs /workspace/output /workspace/logs /workspace/backups /workspace/checkpoints

# Expose ports
EXPOSE 8000 11434

# Start script
COPY start.sh /workspace/start.sh
RUN chmod +x /workspace/start.sh

CMD ["/workspace/start.sh"]
