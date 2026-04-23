# Panduan Menjalankan Git Manager AI Agent

`agent_git.py` adalah skrip asisten AI berbasis Python yang bertugas secara otonom untuk mengelola repository Git. Agent ini akan melakukan *clone* sebuah repository (menggunakan `gh` CLI atau `git` biasa), mengecek status *branch*, membaca struktur file, dan menyajikan laporan dari 5 riwayat *commit* terakhir secara otomatis.

Agent ini dirancang untuk terhubung ke **LiteLLM Gateway** (secara default di `http://localhost:4000/v1`) menggunakan format API standard dari OpenAI.

---

## 🛠️ Prasyarat (Prerequisites)

Sebelum menjalankan skrip ini, pastikan sistem Anda memenuhi beberapa syarat berikut:

1. **Python 3.x** telah terpasang di sistem.
2. **Git** dan **GitHub CLI (`gh`)** sudah terpasang dan Anda sudah melakukan login (jika mengakses repository private).
3. Package Python `openai` dan `python-dotenv` sudah di-install.
4. **LiteLLM Gateway** sedang berjalan di `localhost:4000` (sesuai panduan utama di `README.md`).

### Install Dependensi Python (Mode Virtual Environment / venv)

Sangat disarankan untuk menggunakan Python Virtual Environment (`venv`) agar *packages* tidak bercampur dengan sistem utama Anda.

Buka terminal di dalam folder proyek ini dan jalankan:

```bash
# 1. Buat virtual environment bernama '.venv'
python -m venv .venv

# 2. Aktifkan virtual environment
source .venv/bin/activate

# 3. Install dependensi
pip install openai python-dotenv
```

*(Catatan: Anda harus selalu menjalankan `source .venv/bin/activate` setiap kali membuka terminal baru sebelum menjalankan skrip).*

---

## 🔐 Konfigurasi Environment Variable (.env)

Skrip ini membaca kredensial dan preferensi dari file `.env`. Pastikan Anda sudah menyalin `.env.example` menjadi `.env` dan memiliki konfigurasi minimum sebagai berikut:

```env
# Kunci Master LiteLLM Gateway
LITELLM_MASTER_KEY=sk-master-key-rahasia

# (Opsional) URL Base LiteLLM - Default: http://localhost:4000/v1
LITELLM_BASE_URL=http://localhost:4000/v1

# (Opsional) Nama Model yang digunakan - Default: gemini-1.5-pro
MODEL_NAME=gemini-1.5-pro

# (Opsional) Nama Organisasi Git Default - Default: Qoin-Digital-Indonesia
GIT_ORG=Qoin-Digital-Indonesia
```

---

## 🚀 Cara Menjalankan Skrip

Ada dua cara untuk menjalankan skrip ini:

### Cara 1: Menggunakan Script Otomatis (Direkomendasikan)
Saya telah menyediakan skrip `run_agent.sh` yang otomatis akan membuat *virtual environment*, mengaktifkannya, memasang dependensi, dan langsung menjalankan *agent*.

```bash
# Beri hak akses eksekusi terlebih dahulu (hanya perlu sekali)
chmod +x run_agent.sh

# Jalankan scriptnya
./run_agent.sh <nama_repository> [nama_branch_atau_tag]
```

### Cara 2: Menjalankan Secara Manual
Pastikan virtual environment sudah aktif (terlihat tulisan `(.venv)` di prompt terminal Anda).

```bash
python agent_git.py <nama_repository> [nama_branch_atau_tag]
```

### Contoh Penggunaan:

1. **Clone dengan branch utama (main) secara default:**
   ```bash
   python agent_git.py gitops-k8s
   ```
   > Agent akan mencoba melakukan clone pada branch `main` dari repositori `Qoin-Digital-Indonesia/gitops-k8s`.

2. **Clone branch spesifik (misal: develop):**
   ```bash
   python agent_git.py gitops-k8s develop
   ```

3. **Clone dengan Tag versi spesifik:**
   ```bash
   python agent_git.py crypner-be-digitoken-module v1.2.3
   ```

---

## ⚙️ Cara Kerja Agent

Saat Anda menjalankan skrip, berikut adalah tahapan logis yang akan dieksekusi secara otonom oleh AI:

1. **Menerima Instruksi:** AI menerima perintah untuk melakukan *clone* sebuah *repository* tertentu.
2. **Pengecekan Folder (`list_directory`):** AI memanggil *tool* Python secara lokal untuk melihat apakah folder dengan nama *repository* tersebut sudah ada di komputer Anda.
3. **Eksekusi Clone (`git_clone_gh` / `git_clone`):** Jika belum ada, AI akan mengeksekusi perintah untuk melakukan *clone* menggunakan GitHub CLI (`gh`). Jika `gh` gagal/tidak tersedia, AI secara cerdas akan menggantinya dengan menggunakan perintah `git clone` biasa (HTTPS).
4. **Inspeksi (`git_status`, `git_log`):** AI akan melihat *commit history*, daftar *branch/tag*, dan struktur file dari *repository* tersebut.
5. **Membuat Laporan:** AI akan merangkum seluruh hasil observasinya menjadi sebuah laporan ringkas dan terstruktur dan menampilkannya di terminal Anda.

---

## ⚠️ Troubleshooting (Masalah Umum)

- **`ModuleNotFoundError: No module named 'openai'`**
  - Penyebab: Library `openai` belum terpasang.
  - Solusi: Jalankan `pip install openai`

- **Agent Berhenti atau Timeout / Error 403 / Error API**
  - Penyebab: Koneksi ke LiteLLM Gateway bermasalah, atau `LITELLM_MASTER_KEY` salah.
  - Solusi: Pastikan `docker compose up -d` sudah jalan dan `LITELLM_MASTER_KEY` sama persis dengan yang ada di server LiteLLM.

- **Clone Gagal (Error `gh` atau `git`)**
  - Penyebab: Repository tidak ditemukan atau Anda tidak punya akses ke organisasi (private repo).
  - Solusi: Pastikan nama repo dan *branch* sudah benar. Coba jalankan `gh auth login` untuk merefresh akses Anda ke GitHub.
