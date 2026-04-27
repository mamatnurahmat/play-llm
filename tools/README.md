# ManTools — GitOps AI Agent

> Autonomous Git operations powered by LLM. Supports GitHub, GitLab, Bitbucket.

## Install

```bash
pip install mantools
```

With server support (FastAPI):
```bash
pip install mantools[server]
```

## Quick Start

```bash
# Set up your .env
cp .env.sample .env
# Edit .env with your SCM + LLM credentials

# Pre-flight check
mantools check

# Clone a repository
mantools my-repo main

# Interactive mode (menu)
mantools
```

## LLM Modes

ManTools supports two modes for connecting to LLMs:

### Mode 1: Via LiteLLM Gateway (default)
```env
LITELLM_BASE_URL=http://localhost:4000/v1
LITELLM_MASTER_KEY=sk-master-key
MODEL_NAME=gemini-1.5-pro
```

### Mode 2: Direct to Provider (no gateway needed)
```env
# Gemini
LLM_PROVIDER=gemini
GEMINI_API_KEY=AIza...
MODEL_NAME=gemini-2.5-flash

# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4o

# Ollama (local)
LLM_PROVIDER=ollama
MODEL_NAME=qwen2.5-coder:14b
```

## Available Actions

| Action | Description |
|--------|-------------|
| `clone` | Clone & analyze repository |
| `create-branch` | Create branch via API |
| `pull-request` | Create PR/MR via API |
| `update-image` | Update YAML image & push |
| `quick-pr` | All-in-one: branch → update → PR |

## REST API

```bash
mantools server
# → http://localhost:8888/docs (Swagger UI)
```

## Development

```bash
pip install -e ".[dev,server]"
make check    # pre-flight
make build    # build dist
make upload   # publish to PyPI
```

## License

MIT
