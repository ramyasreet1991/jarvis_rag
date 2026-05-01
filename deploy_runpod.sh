#!/bin/bash
# Jarvis RAG — RunPod Deployment Script
# One-command setup for RTX 4090 Community/Secure Cloud

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo "                    JARVIS RAG — RUNPOD DEPLOYMENT"
echo "═══════════════════════════════════════════════════════════════════════════════"
echo -e "${NC}"

# Configuration
TEMPLATE_NAME="jarvis-rag-rtx4090"
GPU_TYPE="RTX 4090"
IMAGE="runpod/pytorch:2.2.0-py3.10-cuda12.1-devel-ubuntu22.04"

# Check RunPod CLI
if ! command -v runpodctl &> /dev/null; then
    echo -e "${YELLOW}⚠️  RunPod CLI not found. Installing...${NC}"
    pip install runpod
fi

# Check API key
if [ -z "$RUNPOD_API_KEY" ]; then
    echo -e "${RED}❌ RUNPOD_API_KEY not set${NC}"
    echo "   Get your key from: https://runpod.io/console/user/settings"
    exit 1
fi

echo -e "${GREEN}✅ RunPod API key detected${NC}"

# Deploy pod
echo -e "${BLUE}🚀 Deploying pod with ${GPU_TYPE}...${NC}"

POD_ID=$(runpodctl create pod     --name "$TEMPLATE_NAME"     --gpuType "$GPU_TYPE"     --image "$IMAGE"     --containerDiskSize 50     --volumeSize 100     --env "PYTHONUNBUFFERED=1"     --env "CUDA_VISIBLE_DEVICES=0"     --ports "8000/http,11434/http"     --networkVolumeId ""     2>/dev/null || echo "")

if [ -z "$POD_ID" ]; then
    echo -e "${RED}❌ Failed to create pod${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Pod created: $POD_ID${NC}"

# Wait for pod to be running
echo -e "${BLUE}⏳ Waiting for pod to be ready...${NC}"
for i in {1..30}; do
    STATUS=$(runpodctl get pod "$POD_ID" --output json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('desiredStatus',''))" 2>/dev/null || echo "")
    if [ "$STATUS" = "RUNNING" ]; then
        echo -e "${GREEN}✅ Pod is running!${NC}"
        break
    fi
    echo -n "."
    sleep 10
done

# Get connection details
POD_INFO=$(runpodctl get pod "$POD_ID" --output json 2>/dev/null)
HOSTNAME=$(echo "$POD_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('runtime',{}).get('host',''))" 2>/dev/null || echo "")
PORT=$(echo "$POD_INFO" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('runtime',{}).get('ports',[])[0].get('ip',''))" 2>/dev/null || echo "")

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  🎉 DEPLOYMENT SUCCESSFUL${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Pod ID:${NC}     $POD_ID"
echo -e "  ${BLUE}GPU:${NC}        $GPU_TYPE"
echo -e "  ${BLUE}API URL:${NC}    http://$HOSTNAME:8000"
echo -e "  ${BLUE}Ollama:${NC}     http://$HOSTNAME:11434"
echo ""
echo -e "  ${YELLOW}Next steps:${NC}"
echo -e "  1. SSH into pod: ${GREEN}runpodctl ssh $POD_ID${NC}"
echo -e "  2. Clone repo:   ${GREEN}git clone <your-repo> /workspace/jarvis-rag${NC}"
echo -e "  3. Setup env:    ${GREEN}cd /workspace/jarvis-rag && cp .env.example .env${NC}"
echo -e "  4. Pull models:  ${GREEN}ollama pull llama3.1:8b && ollama pull nomic-embed-text${NC}"
echo -e "  5. Run batch:    ${GREEN}python3 batch_processor.py --mode daily${NC}"
echo ""
echo -e "  ${YELLOW}Cost:${NC} ~$0.34-0.59/hr (Community/Secure Cloud)"
echo -e "  ${YELLOW}Storage:${NC} 100GB persistent volume"
echo ""

# Save pod info
echo "$POD_INFO" > /tmp/jarvis_pod_info.json
echo -e "  ${BLUE}Pod info saved to:${NC} /tmp/jarvis_pod_info.json"
