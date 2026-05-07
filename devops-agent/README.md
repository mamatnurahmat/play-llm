# DevOps Agent — GitOps · Kubernetes · CI/CD

Agent berbasis LangGraph + LiteLLM yang bisa menjawab pertanyaan seputar GitOps, Kubernetes, dan CI/CD.

## Arsitektur

```
┌─────────────────────────────────────────────┐
│              docker-compose                  │
│                                             │
│  ┌──────┐    ┌──────────────────────┐       │
│  │  UI  │───▶│  API (FastAPI)       │       │
│  │nginx │    │  LangGraph Agent     │       │
│  │:3000 │    │  LiteLLM Provider    │       │
│  └──────┘    │  :8000               │       │
│              └──────────┬───────────┘       │
│                         │                   │
│              ┌──────────▼───────────┐       │
│              │  Redis               │       │
│              │  :6379               │       │
│              └──────────────────────┘       │
└─────────────────────────────────────────────┘
```

## Tools yang tersedia

| Tool | Fungsi |
|------|--------|
| `explain_gitops_concept` | Flux, ArgoCD, reconciliation, drift, pull/push |
| `explain_kubernetes_resource` | Pod, Deployment, Service, Ingress, HPA, RBAC, dll |
| `explain_cicd_pattern` | GitHub Actions, Jenkins, Tekton, Helm, canary, blue-green |
| `get_kubectl_commands` | Debug, logs, exec, scale, rollout, port-forward, dll |

## Cara Menjalankan

### 1. Clone dan setup

```bash
git clone <repo>
cd devops-agent
cp .env.example .env
```

### 2. Isi API key di `.env`

```env
# Pilih salah satu provider
LITELLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
```

### 3. Jalankan

```bash
docker compose up -d
```

### 4. Akses

| Service | URL |
|---------|-----|
| Chat UI | http://localhost:3000 |
| API Docs | http://localhost:8000/docs |
| API Health | http://localhost:8000/health |

## Provider yang didukung (via LiteLLM)

```env
# OpenAI
LITELLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# Anthropic Claude
LITELLM_MODEL=claude-3-5-haiku-20241022
ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
LITELLM_MODEL=gemini/gemini-1.5-flash
GOOGLE_API_KEY=AIza...

# Ollama (local, gratis!)
LITELLM_MODEL=ollama/llama3.2
OLLAMA_API_BASE=http://host.docker.internal:11434
```

## API Endpoints

### `POST /chat`

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Apa perbedaan ArgoCD dan Flux?"}'
```

Response:
```json
{
  "response": "ArgoCD dan Flux keduanya adalah GitOps tools...",
  "tool_calls_used": ["explain_gitops_concept"]
}
```

### `POST /chat/stream`

```bash
curl -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Jelaskan cara debug pod di Kubernetes"}' \
  --no-buffer
```

## Struktur Project

```
devops-agent/
├── agent/
│   ├── __init__.py     # exports devops_agent
│   ├── state.py        # AgentState TypedDict
│   ├── tools.py        # 4 DevOps knowledge tools
│   ├── nodes.py        # call_model, call_tools, should_continue
│   └── graph.py        # LangGraph StateGraph
├── api/
│   ├── main.py         # FastAPI app
│   └── requirements.txt
├── ui/
│   ├── index.html      # Chat UI
│   └── nginx.conf      # Nginx config
├── Dockerfile.api
├── docker-compose.yml
├── litellm_config.yaml # Optional LiteLLM proxy config
├── .env.example
└── README.md
```

## Commands berguna

```bash
# Lihat logs
docker compose logs -f api

# Restart API saja
docker compose restart api

# Stop semua
docker compose down

# Rebuild setelah perubahan kode
docker compose up -d --build api
```
