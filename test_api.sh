#!/bin/bash
# ── Jarvis RAG — API Test Commands ───────────────────────────────────────────
# Usage: bash test_api.sh
# Set HOST to your RunPod public URL or localhost
# ─────────────────────────────────────────────────────────────────────────────

HOST="${HOST:-http://localhost:8000}"
API_KEY="${API_KEY:-jarvis-runpod-key}"
H_AUTH="X-API-Key: $API_KEY"
H_JSON="Content-Type: application/json"

echo "══════════════════════════════════════════════"
echo "  Jarvis RAG API Tests"
echo "  Host: $HOST"
echo "══════════════════════════════════════════════"

# ── 1. Health (no auth) ───────────────────────────────────────────────────────
echo ""
echo "▶ 1. Health check"
curl -s "$HOST/health" | python3 -m json.tool

# ── 2. KB Stats ───────────────────────────────────────────────────────────────
echo ""
echo "▶ 2. Knowledge base stats"
curl -s "$HOST/stats" -H "$H_AUTH" | python3 -m json.tool

# ── 3. List verified sources ──────────────────────────────────────────────────
echo ""
echo "▶ 3. List Tier 1 sources (credibility >= 0.90)"
curl -s "$HOST/sources?min_credibility=0.90" -H "$H_AUTH" | python3 -m json.tool

# ── 4. Ingest — RSS article (HackerNews) ─────────────────────────────────────
echo ""
echo "▶ 4. Ingest RSS article (HackerNews)"
curl -s -X POST "$HOST/ingest" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "source_type": "rss",
    "content_list": [{
      "title": "Llama 4 Released: Meta Open Sources Its Most Capable Model",
      "content": "Meta has released Llama 4, a family of open source AI models that outperform GPT-4o and Claude 3.5 Sonnet on several benchmarks. The release includes Llama 4 Scout with 17B active parameters, Llama 4 Maverick with 17B active parameters using mixture-of-experts, and Llama 4 Behemoth with 288B active parameters still in training. The models feature a 10M token context window and native multimodal capabilities. Llama 4 Scout achieves state-of-the-art results among sub-100B models on coding, math, and reasoning tasks. The weights are freely downloadable for commercial use under Meta'\''s community license.",
      "url": "https://news.ycombinator.com/item?id=43612345",
      "source_name": "HackerNews",
      "source_tier": "tier_1",
      "source_type": "news",
      "credibility_score": 1.0,
      "published": "2025-04-05T10:00:00",
      "categories": ["ai", "llm", "open-source"]
    }]
  }' | python3 -m json.tool

# ── 5. Ingest — Cloud blog (AWS) ──────────────────────────────────────────────
echo ""
echo "▶ 5. Ingest cloud blog (AWS)"
curl -s -X POST "$HOST/ingest" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "source_type": "blog",
    "content_list": [{
      "title": "Introducing Amazon Bedrock: Enterprise AI Made Simple",
      "content": "Amazon Bedrock is a fully managed service that offers a choice of high-performing foundation models from leading AI companies including AI21 Labs, Anthropic, Cohere, Meta, Mistral AI, Stability AI, and Amazon. Bedrock provides a unified API to access these models without managing infrastructure. Key features include model customization through fine-tuning and continued pre-training, Retrieval Augmented Generation via Knowledge Bases, AI Agents for multi-step task automation, and Guardrails for responsible AI. Bedrock integrates natively with AWS services like S3, Lambda, and SageMaker. Pricing is pay-per-token with no upfront commitments. Enterprise customers use Bedrock for document processing, code generation, customer service automation, and content creation at scale.",
      "url": "https://aws.amazon.com/blogs/aws/amazon-bedrock-enterprise-ai/",
      "source_name": "AWS News Blog",
      "source_tier": "tier_1",
      "source_type": "blog",
      "credibility_score": 0.95,
      "published": "2025-03-15T08:00:00",
      "categories": ["aws", "cloud", "ai", "llm"]
    }]
  }' | python3 -m json.tool

# ── 6. Ingest — YouTube transcript (Fireship) ────────────────────────────────
echo ""
echo "▶ 6. Ingest YouTube transcript (Fireship - Kubernetes)"
curl -s -X POST "$HOST/ingest" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "source_type": "youtube",
    "content_list": [{
      "title": "Kubernetes Explained in 100 Seconds",
      "content": "Kubernetes is an open-source container orchestration system for automating deployment, scaling, and management of containerized applications. Originally designed by Google and now maintained by the Cloud Native Computing Foundation. At its core Kubernetes manages a cluster of machines called nodes. The control plane is the brain of the operation containing the API server, scheduler, and controller manager. Worker nodes run your actual application workloads inside pods. A pod is the smallest deployable unit in Kubernetes and can contain one or more containers. Deployments manage the desired state of your pods providing rolling updates and rollbacks. Services provide stable networking by exposing pods via a DNS name. ConfigMaps and Secrets manage configuration and sensitive data. The Kubernetes ecosystem includes Helm for package management, Istio for service mesh, and Prometheus for monitoring. In 2025 over 96 percent of organizations run Kubernetes in production making it the de-facto standard for container orchestration.",
      "url": "https://www.youtube.com/watch?v=PziYflu8cB8",
      "source_name": "Fireship",
      "source_tier": "tier_1",
      "source_type": "youtube",
      "credibility_score": 0.95,
      "published": "2025-01-20T12:00:00",
      "categories": ["kubernetes", "devops", "containers"]
    }]
  }' | python3 -m json.tool

# ── 7. Ingest — Research paper (arXiv) ───────────────────────────────────────
echo ""
echo "▶ 7. Ingest research paper (arXiv)"
curl -s -X POST "$HOST/ingest" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "source_type": "research",
    "content_list": [{
      "title": "Attention Is All You Need — Transformer Architecture",
      "content": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The Transformer is a model architecture eschewing recurrence and instead relying entirely on an attention mechanism to draw global dependencies between input and output. The Transformer allows for significantly more parallelization and can reach a new state of the art in translation quality after being trained for as little as twelve hours on eight P100 GPUs. The model employs multi-head self-attention which allows the model to jointly attend to information from different representation subspaces at different positions. Positional encoding is added to the input embeddings to give the model information about the relative or absolute position of the tokens. The Transformer architecture became the foundation for BERT, GPT, T5, and virtually all modern large language models. Key insight: attention mechanisms can replace recurrent layers entirely while achieving superior performance on sequence-to-sequence tasks.",
      "url": "https://arxiv.org/abs/1706.03762",
      "source_name": "arXiv",
      "source_tier": "tier_1",
      "source_type": "research",
      "credibility_score": 0.95,
      "published": "2017-06-12T00:00:00",
      "categories": ["ai", "ml", "transformers", "attention"]
    }]
  }' | python3 -m json.tool

# ── 8. Ingest — Podcast (Lex Fridman) ────────────────────────────────────────
echo ""
echo "▶ 8. Ingest podcast excerpt (Lex Fridman)"
curl -s -X POST "$HOST/ingest" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "source_type": "podcast",
    "content_list": [{
      "title": "Sam Altman on AGI, GPT-5, and the Future of OpenAI",
      "content": "In this episode Sam Altman discusses the trajectory toward artificial general intelligence. He believes AGI could arrive within this decade and defines it as AI that can do the work of a brilliant human PhD across most domains. OpenAI is focused on making AGI safe and beneficial. Sam describes the iterative deployment strategy where each model generation teaches us about alignment before the next more capable system. He discusses the compute scaling laws that have driven progress and why he believes reasoning improvements are the next frontier beyond pure scale. On the business side Sam explains why OpenAI transitioned from pure non-profit to a capped-profit model to attract the capital needed to compete in foundation model training. He addresses concerns about concentration of power and explains OpenAI board governance post the 2023 leadership crisis. On products Sam is excited about multimodal capabilities voice mode and the potential for AI agents to handle complex multi-step tasks autonomously.",
      "url": "https://lexfridman.com/sam-altman-3/",
      "source_name": "Lex Fridman Podcast",
      "source_tier": "tier_2",
      "source_type": "podcast",
      "credibility_score": 0.85,
      "published": "2025-02-10T00:00:00",
      "categories": ["ai", "agi", "openai", "llm"]
    }]
  }' | python3 -m json.tool

# ── 9. Check stats after ingestion ───────────────────────────────────────────
echo ""
echo "▶ 9. Stats after ingestion"
curl -s "$HOST/stats" -H "$H_AUTH" | python3 -m json.tool

# ── 10. Query — General AI question ──────────────────────────────────────────
echo ""
echo "▶ 10. Query: What is Kubernetes used for?"
curl -s -X POST "$HOST/query" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "question": "What is Kubernetes used for and why is it popular?",
    "top_k": 3,
    "min_credibility": 0.80
  }' | python3 -m json.tool

# ── 11. Query — Filtered by source type ──────────────────────────────────────
echo ""
echo "▶ 11. Query filtered by YouTube sources only"
curl -s -X POST "$HOST/query" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "question": "How does attention mechanism work in transformers?",
    "top_k": 3,
    "source_type": "research",
    "min_credibility": 0.90
  }' | python3 -m json.tool

# ── 12. Generate — YouTube Shorts ────────────────────────────────────────────
echo ""
echo "▶ 12. Generate YouTube Shorts script"
curl -s -X POST "$HOST/generate" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "topic": "Why Kubernetes dominates container orchestration in 2025",
    "content_type": "youtube_shorts",
    "tone": "technical",
    "top_k": 3
  }' | python3 -m json.tool

# ── 13. Generate — Twitter thread ────────────────────────────────────────────
echo ""
echo "▶ 13. Generate Twitter thread"
curl -s -X POST "$HOST/generate" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "topic": "The rise of open source AI models in 2025",
    "content_type": "twitter_thread",
    "tone": "informative",
    "top_k": 3
  }' | python3 -m json.tool

# ── 14. Generate — Blog post ──────────────────────────────────────────────────
echo ""
echo "▶ 14. Generate blog post"
curl -s -X POST "$HOST/generate" \
  -H "$H_AUTH" -H "$H_JSON" \
  -d '{
    "topic": "AGI timeline predictions and what they mean for developers",
    "content_type": "blog_post",
    "tone": "technical",
    "target_length": "medium",
    "top_k": 5
  }' | python3 -m json.tool

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ All tests complete"
echo "══════════════════════════════════════════════"
