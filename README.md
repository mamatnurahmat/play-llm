# LiteLLM Gateway + GitOps AI Agent

> Platform API Gateway untuk Large Language Model (LLM) berbasis [LiteLLM](https://github.com/BerriAI/litellm), dilengkapi dengan AI Agent otonom untuk otomasi manajemen repository Git.

---

## 📋 Daftar Isi

- [Ringkasan](#-ringkasan)
- [Arsitektur Sistem](#-arsitektur-sistem)
- [Struktur Project](#-struktur-project)
- [Quick Start](#-quick-start)
- [Konfigurasi](#-konfigurasi)
- [Dashboard Admin](#-dashboard-admin)
- [Contoh Penggunaan API](#-contoh-penggunaan-api)
- [GitOps AI Agent](#-gitops-ai-agent)
- [Menghentikan Gateway](#-menghentikan-gateway)

---

## 📖 Ringkasan

Project ini terdiri dari dua komponen utama:

| Komponen | Port | Fungsi |
|----------|------|--------|
| **LiteLLM Gateway** | `:4000` | Proxy API OpenAI-compatible yang merutekan request ke model Gemini / Claude |
| **GitOps AI Agent** | `:8888` | AI Agent otonom untuk clone, branching, PR, dan update image YAML |
| **PostgreSQL** | `:5432` | Database untuk LiteLLM (logging, API key management) |

---

## 🏗 Arsitektur Sistem

```
                    ┌─────────────────────────────────┐
                    │           User / CI/CD           │
                    └─────┬────────────────────┬───────┘
                          │                    │
                   curl/SDK                POST /api/run
                   :4000                   :8888
                          │                    │
              ┌───────────▼──────┐  ┌──────────▼──────────┐
              │  LiteLLM Gateway │  │  GitOps AI Agent     │
              │  (OpenAI Proxy)  │◄─│  (FastAPI + LLM      │
              │                  │  │   function calling)   │
              └────────┬─────────┘  └──────────────────────┘
                       │
            ┌──────────┼──────────┐
            ▼                     ▼
    ┌──────────────┐     ┌──────────────┐
    │ Google Gemini│     │  Anthropic   │
    │     API      │     │  Claude API  │
    └──────────────┘     └──────────────┘
```

---

## 📂 Struktur Project

```
litellm-gateway/
├── docker-compose.yml         # Stack: LiteLLM + PostgreSQL (+ Agent opsional)
├── Dockerfile.agent           # Image untuk agent (python:3.11-alpine + git + gh)
├── litellm_config.yaml        # Konfigurasi model LiteLLM
├── requirements.txt           # Dependensi Python agent
├── run_server.sh              # Helper: venv + run agent server
├── .env.example               # Template environment variables
├── .env                       # Kredensial (TIDAK di-commit)
├── .gitignore
├── README.md                  # Panduan ini
├── README_AGENT_GIT.md        # Panduan lengkap AI Agent
├── tools/
│   └── agent_git.py           # Source code AI Agent
└── data/                      # Hasil clone repository (volume mount)
```

---

## 🚀 Quick Start

### 1. Clone project & konfigurasi

```bash
git clone <repo-url> litellm-gateway
cd litellm-gateway
cp .env.example .env
```

### 2. Edit `.env`

```env
# Wajib
LITELLM_MASTER_KEY=sk-master-key-rahasia
GEMINI_API_KEY=your-gemini-api-key

# Database (bisa pakai default)
POSTGRES_USER=litellm
POSTGRES_PASSWORD=litellm123
POSTGRES_DB=litellm_db
```

### 3. Jalankan Gateway

```bash
docker compose up -d
```

### 4. Verifikasi

```bash
# Cek status container
docker compose ps

# Cek log LiteLLM
docker compose logs -f litellm

# Test API
curl http://localhost:4000/health
```

---

## 🔐 Konfigurasi

### Environment Variables

| Variable | Wajib | Deskripsi |
|----------|-------|-----------|
| `LITELLM_MASTER_KEY` | ✅ | Bearer token / API key untuk mengakses gateway |
| `GEMINI_API_KEY` | ✅ | API Key dari Google AI Studio |
| `ANTHROPIC_API_KEY` | ❌ | API Key dari Anthropic Console |
| `POSTGRES_USER` | ❌ | Username database (default: `litellm`) |
| `POSTGRES_PASSWORD` | ❌ | Password database |
| `POSTGRES_DB` | ❌ | Nama database (default: `litellm_db`) |

### Model Configuration (`litellm_config.yaml`)

File ini mendefinisikan model mana saja yang tersedia melalui gateway. Secara default sudah dikonfigurasi untuk:
- **Gemini 1.5 Pro** → `gemini-1.5-pro`
- **Claude 3.5 Sonnet** → `claude-3-5-sonnet` (uncomment di `.env`)

---

## 🌐 Dashboard Admin

LiteLLM menyediakan Dashboard UI untuk manajemen API Key, monitoring pengeluaran, dan log API calls.

- **URL**: [http://localhost:4000/ui](http://localhost:4000/ui)
- **Login**: Masukkan value `LITELLM_MASTER_KEY` dari `.env`

---

## 🧪 Contoh Penggunaan API

Setelah gateway berjalan di `http://localhost:4000`, semua model dapat diakses via format standar OpenAI.

### cURL

```bash
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-master-key-rahasia" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-1.5-pro",
    "messages": [
      {"role": "user", "content": "Halo, kamu model apa?"}
    ]
  }'
```

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-master-key-rahasia",
    base_url="http://localhost:4000/v1"
)

response = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "Hai Gemini!"}]
)
print(response.choices[0].message.content)
```

---

## 🤖 GitOps AI Agent

Project ini juga dilengkapi **GitOps AI Agent** (`tools/agent_git.py`) — sebuah AI Agent otonom yang dapat:

| Fitur | Deskripsi |
|-------|-----------|
| **Clone** | Clone repository + analisa struktur + laporan commit |
| **Create Branch** | Buat branch baru dari existing, push ke remote |
| **Pull Request** | Buat PR via `gh` CLI, opsional auto-delete branch |
| **Update Image** | Replace baris `image:` di file YAML, commit & push |

### Quick Run (Lokal)

```bash
# Setup venv
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Mode Interaktif
python tools/agent_git.py

# Mode Web API Server
python tools/agent_git.py server
# → Swagger UI: http://localhost:8888/docs
```

### Quick Run (Docker)

```bash
# Uncomment service agent_git di docker-compose.yml lalu:
docker compose up -d --build agent_git

# Swagger UI: http://localhost:8888/docs
```

> 📖 **Dokumentasi lengkap**: Lihat [README_AGENT_GIT.md](README_AGENT_GIT.md) untuk detail arsitektur, tools reference, API spec, dan troubleshooting.

---

## 🛑 Menghentikan Gateway

```bash
# Stop semua container
docker compose down

# Stop + hapus data database (reset total)
docker compose down -v
```

---

## 📜 Lisensi

Internal use — Qoin Digital Indonesia.
