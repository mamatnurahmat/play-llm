#!/bin/bash
# Script untuk menjalankan Agent Git dalam Python Virtual Environment (venv)

# 1. Pastikan kita berada di folder yang sama dengan script
cd "$(dirname "$0")"

# 2. Cek apakah virtual environment (.venv) sudah ada, jika belum buat baru
if [ ! -d ".venv" ]; then
    echo "⚙️ Membuat Python Virtual Environment (.venv)..."
    python3 -m venv .venv
fi

# 3. Aktifkan virtual environment
echo "🔄 Mengaktifkan virtual environment..."
source .venv/bin/activate

# 4. Install dependensi jika belum ada
echo "📦 Menginstall/Mengecek dependensi..."
pip install -q openai python-dotenv

# 5. Jalankan agent dengan argumen yang diberikan
echo "🚀 Menjalankan Agent Git..."
python agent_git.py "$@"
