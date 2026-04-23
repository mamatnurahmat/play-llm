#!/bin/bash

# Pastikan eksekusi selalu berasal dari direktori script ini berada
cd "$(dirname "$0")"

VENV_DIR=".venv"

echo "=========================================="
echo "🚀 Memulai Git Agent Server"
echo "=========================================="

# Cek apakah virtual environment sudah ada
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Membuat Virtual Environment ($VENV_DIR)..."
    python3 -m venv $VENV_DIR
fi

# Aktifkan virtual environment
echo "🔄 Mengaktifkan Virtual Environment..."
source $VENV_DIR/bin/activate

# Install dependensi (khususnya openai, fastapi, uvicorn)
if [ -f "requirements.txt" ]; then
    echo "📦 Menginstall dependensi dari requirements.txt..."
    pip install -r requirements.txt
else
    echo "⚠️ File requirements.txt tidak ditemukan. Melewati proses installasi."
fi

# Jalankan server
echo "🎯 Menjalankan Web API Server di port 8888..."
python tools/agent_git.py server
