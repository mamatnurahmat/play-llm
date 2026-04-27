# ============================================================
# ManTools — Build, Install & Release
# ============================================================
#
#   make install       Install lokal (editable / development)
#   make build         Build wheel + sdist
#   make release       Upload ke PyPI production
#   make test-release  Upload ke TestPyPI
#   make clean         Bersihkan artifact
#   make check         Pre-flight check agent
#   make server        Jalankan FastAPI server
#   make help          Tampilkan bantuan
#
# ============================================================

VENV       := .venv
PYTHON     := $(VENV)/bin/python
PIP        := $(VENV)/bin/pip
PACKAGE    := mantools
VERSION    := $(shell grep 'version' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/')

.PHONY: help install install-dev build clean release test-release check server lint uninstall

help: ## Tampilkan daftar perintah
	@echo ""
	@echo "  ManTools v$(VERSION)"
	@echo "  =========================="
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ---- Virtual Environment ----

venv: $(VENV)/bin/activate ## Buat .venv jika belum ada

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	@echo "✅ Virtual environment siap di $(VENV)/"

# ---- Install ----

install: venv ## Install package di lokal (editable mode)
	$(PIP) install -e ".[server]"
	$(PIP) install build twine
	@echo ""
	@echo "✅ Terinstall! Jalankan: $(PYTHON) -m agents.cli check"

install-dev: venv ## Install dengan semua dev dependencies
	$(PIP) install -e ".[dev,server]"
	$(PIP) install build twine
	@echo ""
	@echo "✅ Dev install selesai!"

uninstall: ## Hapus package dari lokal
	$(PIP) uninstall -y $(PACKAGE)
	@echo "✅ $(PACKAGE) dihapus"

# ---- Build ----

clean: ## Bersihkan build artifacts
	rm -rf dist/ build/ *.egg-info agents/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "✅ Clean"

build: venv clean ## Build sdist + wheel ke dist/
	$(PYTHON) -m build
	@echo ""
	@echo "✅ Build selesai!"
	@ls -lh dist/

# ---- Release ----

test-release: build ## Upload ke TestPyPI (untuk testing)
	$(PYTHON) -m twine upload --repository testpypi dist/*
	@echo ""
	@echo "✅ Upload ke TestPyPI selesai!"
	@echo "   Test install: pip install -i https://test.pypi.org/simple/ $(PACKAGE)"

release: build ## Upload ke PyPI production
	@echo "⚠️  Upload $(PACKAGE) v$(VERSION) ke PyPI PRODUCTION? [y/N]"
	@read ans && [ "$$ans" = "y" ] || (echo "Dibatalkan."; exit 1)
	$(PYTHON) -m twine upload dist/*
	@echo ""
	@echo "🎉 $(PACKAGE) v$(VERSION) published ke PyPI!"
	@echo "   Install: pip install $(PACKAGE)"

# ---- Development ----

check: ## Jalankan pre-flight check
	$(PYTHON) -m agents.cli check

config: ## Tampilkan current config
	$(PYTHON) -m agents.cli config

config-init: ## Setup wizard interaktif
	$(PYTHON) -m agents.cli config init

server: ## Jalankan FastAPI server (:8888)
	$(PYTHON) -m agents.cli server

lint: ## Cek syntax errors
	@$(PYTHON) -m py_compile agents/__init__.py
	@$(PYTHON) -m py_compile agents/config.py
	@$(PYTHON) -m py_compile agents/base_agent.py
	@$(PYTHON) -m py_compile agents/cli.py
	@$(PYTHON) -m py_compile agents/server.py
	@echo "✅ No syntax errors"
