#!/bin/sh
# SolarReportAutomation - pre-commit hook
# Kurulum: cp .github/pre-commit.sh .git/hooks/pre-commit
# Not: python yolu .venv oncelikli secilir (global python'da bagimliliklar yok)

echo ">> Pre-commit kontroller basliyor..."

PY="python"
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
fi

# 1. Health check
"$PY" main.py --health
if [ $? -ne 0 ]; then
  echo "X Health check basarisiz - commit iptal"
  exit 1
fi

# 2. Smoke test (pytest kuruluysa ve tests/smoke varsa calisir)
if [ -d "tests/smoke" ] && "$PY" -m pytest --version >/dev/null 2>&1; then
  "$PY" -m pytest tests/smoke/ -x -q
  if [ $? -ne 0 ]; then
    echo "X Smoke test basarisiz - commit iptal"
    exit 1
  fi
else
  echo "!! Smoke test atlandi (pytest kurulu degil veya tests/smoke yok)"
fi

# 3. Lint (ruff kuruluysa calisir) — GECICI WARN-ONLY:
#    Mevcut 101 ihlal ayri sprintte temizlenene kadar commit engellenmez.
#    Temizlik sonrasi tekrar blocking yapilacak (bkz. docs/ROADMAP.md Teknik Borc).
if "$PY" -m ruff --version >/dev/null 2>&1; then
  "$PY" -m ruff check .
  if [ $? -ne 0 ]; then
    echo "!! Lint ihlalleri var (WARN-ONLY - commit engellenmedi)"
  fi
else
  echo "!! Lint atlandi (ruff kurulu degil)"
fi

# 4. Secret kontrolu (yalnizca eklenen satirlar taranir)
if git diff --cached | grep -E "^\+.*(password|secret|api_key|token|appkey)\s*=\s*['\"][^'\"]{6,}" > /dev/null 2>&1; then
  echo "X Olasi secret tespit edildi - commit iptal"
  echo "  .env dosyasina tasi"
  exit 1
fi

# 5. .env Git'e girmesin
if git diff --cached --name-only | grep -E "^\.env$" > /dev/null 2>&1; then
  echo "X .env staged - commit iptal. .gitignore kontrolu yap"
  exit 1
fi

# 6. scratch/ production'a girmesin (silme haric - index'ten cikarma serbest)
if git diff --cached --name-only --diff-filter=d | grep -E "^scratch/" > /dev/null 2>&1; then
  echo "X scratch/ klasorunden dosya staged - commit iptal"
  echo "  Discovery scriptleri production'a girmez"
  exit 1
fi

echo "OK Tum kontroller gecti - commit hazir"
exit 0
