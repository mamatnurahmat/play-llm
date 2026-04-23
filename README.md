# Panduan Setup LiteLLM Gateway

Ini adalah panduan komprehensif untuk membangun dan menjalankan **LiteLLM Gateway** menggunakan Docker Compose dengan database PostgreSQL. Gateway ini sudah dikonfigurasi untuk menggunakan model dari **Google Gemini** dan **Anthropic (Claude)**.

## 📋 Struktur Direktori

```text
litellm-gateway/
├── docker-compose.yml     # Konfigurasi layanan Docker (LiteLLM + PostgreSQL)
├── litellm_config.yaml    # Konfigurasi model (Gemini & Anthropic)
├── .env.example           # Contoh file environment variables
├── .gitignore             # File untuk mengabaikan secret (.env) dan .venv di Git
├── agent_git.py           # Script AI Agent untuk mengelola Git Repository
├── run_agent.sh           # Bash script otomatis untuk menjalankan agent
├── README.md              # Panduan LiteLLM Gateway
└── README_AGENT_GIT.md    # Panduan khusus untuk Agent Git
```

---

## 🛠️ Langkah-langkah Setup

### 1. Salin file `.env`
Buat file `.env` berdasarkan template `.env.example`. Buka terminal dan jalankan:
```bash
cd litellm-gateway
cp .env.example .env
```

### 2. Konfigurasi Kredensial
Buka file `.env` dan isi dengan kredensial API Key Anda:
- `LITELLM_MASTER_KEY`: Ganti dengan key rahasia pilihan Anda. Ini akan digunakan sebagai Bearer Token/API Key untuk mengakses LiteLLM gateway Anda.
- `GEMINI_API_KEY`: Masukkan API Key dari Google AI Studio.
- `ANTHROPIC_API_KEY`: Masukkan API Key dari Anthropic Console.
- Database settings bisa dibiarkan default kecuali jika Anda ingin menyesuaikan user/password.

### 3. Menjalankan Gateway
Jalankan LiteLLM beserta databasenya menggunakan Docker Compose:
```bash
docker compose up -d
```
> *Catatan: Proses pertama kali akan mengunduh image Docker LiteLLM dan PostgreSQL. Silakan tunggu hingga selesai.*

Untuk melihat log apakah gateway sudah berjalan dengan baik:
```bash
docker compose logs -f litellm
```

---

## 🌐 Dashboard Admin

LiteLLM menyediakan Dashboard UI untuk manajemen API Key tambahan, memonitor *spend* (pengeluaran), dan melihat log panggilan API.

- **URL Dashboard**: [http://localhost:4000/ui](http://localhost:4000/ui)
- Pada saat pertama kali dibuka, Anda akan diminta memasukkan API Key. Masukkan value dari `LITELLM_MASTER_KEY` yang ada di `.env` Anda.

## 🤖 Git Manager AI Agent

Saya juga telah menyiapkan `agent_git.py`, sebuah skrip yang dapat berfungsi layaknya asisten otonom untuk mengkloning dan memeriksa *repository* GitHub yang terhubung langsung ke **LiteLLM Gateway** Anda.

Untuk detail cara instalasi (menggunakan *virtual environment* Python) dan cara menjalankannya, silakan baca **[README_AGENT_GIT.md](README_AGENT_GIT.md)**.

---

## 🧪 Contoh Penggunaan (Test API)

Setelah gateway berjalan di `http://localhost:4000`, aplikasi ini bertindak layaknya OpenAI API (OpenAI-compatible endpoint). Anda bisa mengakses model Gemini atau Anthropic dengan format standar OpenAI.

### Menggunakan `cURL`

**Test Model Gemini 1.5 Pro:**
```bash
curl --location 'http://localhost:4000/v1/chat/completions' \
--header 'Authorization: Bearer sk-master-key-rahasia' \
--header 'Content-Type: application/json' \
--data '{
    "model": "gemini-1.5-pro",
    "messages": [
        {
            "role": "user",
            "content": "Halo, kamu model apa?"
        }
    ]
}'
```

**Test Model Claude 3.5 Sonnet:**
```bash
curl --location 'http://localhost:4000/v1/chat/completions' \
--header 'Authorization: Bearer sk-master-key-rahasia' \
--header 'Content-Type: application/json' \
--data '{
    "model": "claude-3-5-sonnet",
    "messages": [
        {
            "role": "user",
            "content": "Tuliskan puisi pendek tentang AI."
        }
    ]
}'
```

### Menggunakan Python (OpenAI SDK)

Karena LiteLLM adalah proxy OpenAI-compatible, Anda bisa menggunakan package `openai` di Python:

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-master-key-rahasia",    # LITELLM_MASTER_KEY Anda
    base_url="http://localhost:4000/v1" # URL LiteLLM Gateway
)

# Panggil Gemini
response_gemini = client.chat.completions.create(
    model="gemini-1.5-pro",
    messages=[{"role": "user", "content": "Hai Gemini!"}]
)
print("Gemini:", response_gemini.choices[0].message.content)

# Panggil Anthropic (Claude)
response_claude = client.chat.completions.create(
    model="claude-3-5-sonnet",
    messages=[{"role": "user", "content": "Hai Claude!"}]
)
print("Claude:", response_claude.choices[0].message.content)
```

---

## 🛑 Menghentikan Gateway

Untuk mematikan gateway:
```bash
docker compose down
```

Untuk mematikan gateway sekaligus menghapus data PostgreSQL (Reset Total):
```bash
docker compose down -v
```
