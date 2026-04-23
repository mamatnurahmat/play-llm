# GitOps AI Agent — `agent_git.py`

> Skrip AI Agent otonom berbasis Python yang mengelola repository Git melalui perintah natural language. Didukung oleh LLM (Gemini/Claude) via LiteLLM Gateway dengan protokol OpenAI-compatible.

---

## 📋 Daftar Isi

- [Ringkasan](#-ringkasan)
- [Arsitektur](#-arsitektur)
- [Fitur Utama](#-fitur-utama)
- [Prasyarat](#️-prasyarat)
- [Instalasi & Setup](#-instalasi--setup)
- [Mode Operasi](#-mode-operasi)
- [Cara Penggunaan](#-cara-penggunaan)
- [Web API Reference](#-web-api-reference)
- [Tools Reference](#-tools-reference)
- [Environment Variables](#-environment-variables)
- [Struktur Project](#-struktur-project)
- [Cara Kerja Agent Loop](#-cara-kerja-agent-loop)
- [Troubleshooting](#️-troubleshooting)

---

## 📖 Ringkasan

`agent_git.py` adalah AI Agent yang menerima instruksi tingkat tinggi (misal: *"clone repo X"*) lalu **secara otonom menentukan langkah eksekusi**, memanggil *tools* yang tersedia, dan menghasilkan laporan terstruktur — **tanpa intervensi manual** per-langkah.

Agent ini terhubung ke **LiteLLM Gateway** (`localhost:4000`) menggunakan SDK `openai` (AsyncOpenAI), sehingga backend LLM (Gemini, Claude, dll.) dapat dipertukarkan tanpa mengubah kode agent.

---

## 🏗 Arsitektur

```
┌──────────────────────────────────────────────────┐
│                   User / CI/CD                    │
│         (CLI / curl / Swagger UI / Webhook)       │
└──────────┬───────────────────────────┬───────────┘
           │ Interactive CLI            │ POST /api/run
           ▼                            ▼
┌──────────────────────────────────────────────────┐
│              agent_git.py                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  │
│  │ CLI Mode   │  │ Init Mode  │  │ Server Mode│  │
│  │ (Direct)   │  │ (Interact) │  │ (FastAPI)  │  │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘  │
│         └───────────┬───────────────────┘         │
│                     ▼                              │
│         ┌─────────────────────┐                    │
│         │  run_git_agent()    │ ◄── Agent Loop     │
│         │  (async, max 15     │     LLM ↔ Tools    │
│         │   turns)            │                    │
│         └────────┬────────────┘                    │
│                  │                                  │
│    ┌─────────────┼──────────────┐                  │
│    ▼             ▼              ▼                  │
│ ┌──────┐  ┌──────────┐  ┌──────────────┐          │
│ │13 Git│  │ OpenAI   │  │ Schema Auto  │          │
│ │Tools │  │ Client   │  │ Converter    │          │
│ │(local│  │(Async)   │  │(inspect →    │          │
│ │ exec)│  │          │  │ JSON Schema) │          │
│ └──┬───┘  └────┬─────┘  └─────────────┘          │
└────┼───────────┼──────────────────────────────────┘
     │           │
     ▼           ▼
 git / gh    LiteLLM Gateway (:4000)
 (subprocess)    │
                 ▼
           Gemini / Claude API
```

### Technology Stack

| Layer | Teknologi | Fungsi |
|-------|-----------|--------|
| **LLM Client** | `openai` (AsyncOpenAI) | Komunikasi dengan LiteLLM via protokol OpenAI |
| **Web API** | `fastapi` + `uvicorn` | REST API server dengan Swagger docs |
| **Config** | `python-dotenv` | Load `.env` file |
| **CLI Tools** | `git`, `gh` (GitHub CLI) | Operasi git lokal dan remote |
| **Stdlib** | `subprocess`, `asyncio`, `inspect`, `json`, `re`, `os` | Core runtime |

---

## ✨ Fitur Utama

| # | Aksi | Deskripsi | Input |
|---|------|-----------|-------|
| 1 | **Clone** | Clone repo + analisa struktur + 5 commit terakhir | `repo_name`, `ref` |
| 2 | **Create Branch** | Buat branch baru dari branch existing, push ke remote | `existing_branch`, `new_branch` |
| 3 | **Pull Request** | Buat PR via `gh` CLI, opsional delete-after-merge | `source_branch`, `dest_branch` |
| 4 | **Update Image** | Replace baris `image:` di file YAML, commit & push | `yaml_file`, `new_image`, `ref` |

---

## 🛠️ Prasyarat

| Komponen | Versi Min. | Catatan |
|----------|-----------|---------|
| Python | 3.10+ | Untuk menjalankan agent |
| Git | 2.x | Operasi clone, commit, push |
| GitHub CLI (`gh`) | 2.x | Clone via SSH, buat PR (opsional tapi direkomendasikan) |
| Docker & Docker Compose | - | Untuk mode Docker (opsional) |
| LiteLLM Gateway | - | Harus running di `localhost:4000` atau URL yang dikonfigurasi |

---

## 📦 Instalasi & Setup

### Langkah 1: Buat Virtual Environment

```bash
cd litellm-gateway

# Buat venv
python3 -m venv .venv

# Aktifkan
source .venv/bin/activate

# Install dependensi
pip install -r requirements.txt
```

**Isi `requirements.txt`:**
```
openai
python-dotenv
fastapi
uvicorn
```

### Langkah 2: Konfigurasi `.env`

```bash
cp .env.example .env
```

Edit `.env` dan sesuaikan:
```env
# WAJIB
LITELLM_MASTER_KEY=sk-master-key-rahasia
GEMINI_API_KEY=your-gemini-api-key

# OPSIONAL (sudah ada default)
LITELLM_BASE_URL=http://localhost:4000/v1
MODEL_NAME=gemini-1.5-pro
GIT_ORG=Qoin-Digital-Indonesia
GITHUB_TOKEN=ghp_xxxx
```

### Langkah 3: Pastikan LiteLLM Gateway Running

```bash
docker compose up -d litellm db
```

---

## 🎯 Mode Operasi

Agent mendukung **3 mode** yang dipilih berdasarkan argumen pertama:

```
python tools/agent_git.py                → Mode Interaktif (menu pilihan)
python tools/agent_git.py init           → Mode Interaktif (sama)
python tools/agent_git.py server         → Mode Web API Server (port 8888)
python tools/agent_git.py <repo> [ref]   → Mode Direct CLI (langsung clone)
```

| Mode | Trigger | Cocok Untuk |
|------|---------|-------------|
| **Interaktif** | tanpa arg / `init` | Eksplorasi manual, debugging |
| **Web API** | `server` | Integrasi CI/CD, webhook, automasi |
| **Direct CLI** | `<repo_name> [branch]` | One-liner cepat, scripting |

---

## 🚀 Cara Penggunaan

### Mode 1: Interaktif CLI

```bash
python tools/agent_git.py
# atau
python tools/agent_git.py init
```

Output di terminal:
```
🚀 Memulai mode interaktif...

Pilih Aksi:
1. Clone / Analyze Repository
2. Create Branch
3. Create Pull Request
4. Update Image in YAML
Masukkan pilihan (1/2/3/4) [1]: _
```

Agent akan memandu Anda memasukkan parameter yang dibutuhkan sesuai aksi yang dipilih.

### Mode 2: Direct CLI

```bash
# Clone branch utama (main)
python tools/agent_git.py gitops-k8s

# Clone branch spesifik
python tools/agent_git.py gitops-k8s develop

# Clone tag spesifik
python tools/agent_git.py crypner-be-digitoken-module v1.2.3
```

### Mode 3: Web API Server

```bash
# Jalankan langsung
python tools/agent_git.py server

# Atau gunakan helper script
./run_server.sh
```

Server akan berjalan di `http://localhost:8888`:
- **Swagger UI**: http://localhost:8888/docs
- **ReDoc**: http://localhost:8888/redoc

---

## 🌐 Web API Reference

### `POST /api/run`

Endpoint utama untuk mengirim instruksi ke AI Agent.

#### Request Body

```json
{
  "action": "string (wajib)",
  "repo_name": "string (wajib)",
  "org": "string (opsional, default dari env GIT_ORG)",
  "action_kwargs": {}
}
```

#### Contoh Payload per Aksi

**1. Clone Repository**
```bash
curl -X POST http://localhost:8888/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "action": "clone",
    "repo_name": "gitops-k8s",
    "action_kwargs": { "ref": "main" }
  }'
```

**2. Create Branch**
```bash
curl -X POST http://localhost:8888/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "action": "create-branch",
    "repo_name": "gitops-k8s",
    "action_kwargs": {
      "existing_branch": "main",
      "new_branch": "feature/update-api"
    }
  }'
```

**3. Pull Request**
```bash
curl -X POST http://localhost:8888/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "action": "pull-request",
    "repo_name": "gitops-k8s",
    "action_kwargs": {
      "source_branch": "feature/update-api",
      "dest_branch": "main",
      "delete_after_merge": true
    }
  }'
```

**4. Update Image**
```bash
curl -X POST http://localhost:8888/api/run \
  -H "Content-Type: application/json" \
  -d '{
    "action": "update-image",
    "repo_name": "gitops-k8s",
    "action_kwargs": {
      "ref": "main",
      "yaml_file": "k8s/deployment.yaml",
      "new_image": "myregistry/myapp:v2.0.1"
    }
  }'
```

#### Response

```json
{
  "status": "success",
  "report": "Laporan teks lengkap dari AI Agent..."
}
```

---

## 🔧 Tools Reference

Agent memiliki **13 tools** yang dapat dipanggil secara otonom oleh LLM:

### Read-Only Tools (Safe)

| Tool | Deskripsi |
|------|-----------|
| `git_status` | Branch aktif, file changes, commit terakhir |
| `git_log` | N commit terakhir (max 20) |
| `git_branch_list` | Daftar semua branch (lokal + remote) |
| `git_tag_list` | Daftar semua tag (sorted descending) |
| `list_directory` | List file/folder di path tertentu |
| `read_file` | Baca isi file |
| `run_shell_command` | Eksekusi shell command (**whitelist only**: `ls`, `cat`, `head`, `tail`, `wc`, `find`, `tree`, `git log/diff/show/branch/tag/remote`) |

### Write Tools (Modifikasi State)

| Tool | Deskripsi |
|------|-----------|
| `git_clone` | Clone via `git clone --branch --single-branch` |
| `git_clone_gh` | Clone via `gh repo clone` (SSH/HTTPS otomatis) |
| `git_create_branch` | Fetch → checkout existing → buat branch baru → push |
| `git_create_pull_request` | Buat PR via `gh pr create` |
| `update_yaml_image` | Regex replace baris `image:` di file YAML |
| `git_commit_and_push` | `git add . && commit -m "..." && push` |

### Auto Schema Converter

Tools **tidak perlu didefinisikan manual** dalam format JSON Schema. Fungsi `get_openai_tools()` secara otomatis mengkonversi fungsi Python biasa menjadi skema OpenAI function calling melalui `inspect.signature()`:

```
Python function → inspect → JSON Schema → OpenAI tools format
```

---

## 🔑 Environment Variables

| Variable | Wajib | Default | Deskripsi |
|----------|-------|---------|-----------|
| `LITELLM_MASTER_KEY` | ✅ | `sk-master-key-rahasia` | API key untuk autentikasi ke LiteLLM Gateway |
| `LITELLM_BASE_URL` | ❌ | `http://localhost:4000/v1` | URL endpoint LiteLLM Gateway |
| `MODEL_NAME` | ❌ | `gemini-1.5-pro` | Model LLM yang digunakan |
| `GIT_ORG` | ❌ | `Qoin-Digital-Indonesia` | Organisasi GitHub default |
| `GITHUB_TOKEN` | ❌ | - | Token autentikasi untuk GitHub CLI |

---

## 📂 Struktur Project

```
litellm-gateway/
├── docker-compose.yml         # Stack: LiteLLM + PostgreSQL + Agent
├── Dockerfile.agent           # Image agent (python:3.11-alpine + git + gh)
├── litellm_config.yaml        # Konfigurasi model LiteLLM (Gemini, Claude)
├── requirements.txt           # Dependensi Python
├── run_server.sh              # Helper script: venv + run server
├── .env.example               # Template environment variables
├── .env                       # Environment variables (TIDAK di-commit)
├── .gitignore
├── README.md                  # Panduan LiteLLM Gateway
├── README_AGENT_GIT.md        # Panduan Agent Git (file ini)
├── tools/
│   └── agent_git.py           # Source code utama AI Agent (816 baris)
└── data/                      # Hasil clone repository (volume mount)
```

---

## ⚙️ Cara Kerja Agent Loop

Saat agent menerima instruksi, berikut alur internal yang terjadi:

```
1. Bangun SYSTEM PROMPT berdasarkan action yang dipilih
   ↓
2. Kirim messages[] ke LLM via AsyncOpenAI
   ↓
3. LLM merespons dengan tool_calls? ──────────────┐
   │                                                │
   │ YA                                             │ TIDAK
   ▼                                                ▼
4. Eksekusi tool secara lokal (subprocess)      6. Final answer
   ↓                                               diterima
5. Kirim tool result balik ke LLM               ↓
   ↓                                            7. Tampilkan laporan
   └──────── kembali ke langkah 2 ◄────┘           / Return JSON
```

- **Max turns**: 15 iterasi (mencegah infinite loop)
- **LLM call**: Asinkron (`AsyncOpenAI`)
- **Tool execution**: Sinkron (`subprocess.run` dengan timeout)
- **Output limit**: stdout 2000 char, stderr 500 char per tool

---

## ⚠️ Troubleshooting

| Masalah | Penyebab | Solusi |
|---------|----------|--------|
| `ModuleNotFoundError: No module named 'openai'` | Library belum terpasang | `pip install -r requirements.txt` |
| `Connection refused` / Timeout | LiteLLM Gateway tidak running | `docker compose up -d litellm db` |
| `Error 403` / `Unauthorized` | `LITELLM_MASTER_KEY` salah | Samakan key di `.env` dengan konfigurasi LiteLLM |
| Clone gagal (`gh` error) | Tidak ada akses ke repo private | `gh auth login` atau set `GITHUB_TOKEN` |
| Clone gagal (`git` error) | Branch/tag tidak ditemukan | Periksa nama branch/tag yang benar |
| Agent loop tidak berhenti | Model tidak memberikan final answer | Max 15 turns sudah di-set sebagai safety net |
| `uvicorn` tidak ditemukan | Dependensi belum di-install | `pip install fastapi uvicorn` |

---

## 🐳 Deployment via Docker Compose

Untuk menjalankan agent sebagai container bersama LiteLLM:

1. Uncomment service `agent_git` di `docker-compose.yml`
2. Jalankan:
   ```bash
   docker compose up -d --build
   ```
3. Akses Swagger UI di http://localhost:8888/docs
4. Atau gunakan CLI interaktif di dalam container:
   ```bash
   docker compose exec -it agent_git python /app/tools/agent_git.py init
   ```

---

## 📜 Lisensi

Internal use — Qoin Digital Indonesia.
