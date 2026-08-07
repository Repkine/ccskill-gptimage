#!/bin/bash
#
# ccskill-gptimage - Installer (issue #020)
#
# После clone → cd → ./install.sh инструмент доступен из любого проекта
# и человеку, и Claude Code.
#
#   1. проверка python3 (>= 3.10)
#   2. создание venv и установка зависимостей (идемпотентно)
#   3. symlink ~/.local/bin/ccskill-gptimage — команда появляется в PATH
#   4. symlink ~/.claude/skills/ccskill-gptimage — регистрация скилла на уровне пользователя
#   5. диагностика доступности backend (Codex CLI / OPENAI_API_KEY)
#
# Usage: ./install.sh
#
# Переменные окружения:
#   CCSKILL_GPTIMAGE_INSTALL_SKIP_DEPS=1  пропустить pip install (для тестов)
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Вычисляем каталог репозитория от собственного расположения (в том числе через symlink)
SCRIPT_PATH="$0"
while [ -L "$SCRIPT_PATH" ]; do
    LINK_TARGET=$(readlink "$SCRIPT_PATH")
    case "$LINK_TARGET" in
        /*) SCRIPT_PATH="$LINK_TARGET" ;;
        *)  SCRIPT_PATH="$(dirname "$SCRIPT_PATH")/$LINK_TARGET" ;;
    esac
done
REPO_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"

echo "================================================"
echo "  ccskill-gptimage - Installer"
echo "================================================"
echo ""
echo "Master: $REPO_DIR"
echo ""

# ========================================
# 1. Проверка python3 (>= 3.10)
# ========================================

echo "Step 1: Checking prerequisites..."

# Ищем Python 3.10+. В macOS системный python3 — это 3.9, поэтому сначала
# пробуем команды с номером версии в имени.
_py_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

VENV_PYTHON="$REPO_DIR/venv/bin/python"

PYTHON_BIN=""
if [ -x "$VENV_PYTHON" ] && _py_ok "$VENV_PYTHON"; then
    # Если существующий venv рабочий, берём его — версия системного Python не важна
    PYTHON_BIN="$VENV_PYTHON"
else
    for cand in python3.13 python3.12 python3.11 python3.10 python3; do
        if command -v "$cand" &> /dev/null && _py_ok "$cand"; then
            PYTHON_BIN="$cand"
            break
        fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${RED}Error: Python 3.10+ is required but was not found${NC}"
    echo "Install it first (e.g. brew install python@3.13): https://www.python.org/"
    exit 1
fi

echo -e "${GREEN}✓ Python found: $PYTHON_BIN ($("$PYTHON_BIN" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))'))${NC}"
echo ""

# ========================================
# 2. Создание venv и установка зависимостей (идемпотентно)
# ========================================

echo "Step 2: Setting up Python environment..."

if [ ! -x "$VENV_PYTHON" ]; then
    "$PYTHON_BIN" -m venv "$REPO_DIR/venv"
    echo -e "${GREEN}✓ venv created${NC}"
else
    echo -e "${GREEN}✓ venv already exists${NC}"
fi

if [ "${CCSKILL_GPTIMAGE_INSTALL_SKIP_DEPS:-}" = "1" ]; then
    echo -e "${YELLOW}(dependencies skipped: CCSKILL_GPTIMAGE_INSTALL_SKIP_DEPS=1)${NC}"
else
    "$VENV_PYTHON" -m pip install --quiet --disable-pip-version-check -r "$REPO_DIR/requirements.txt"
    echo -e "${GREEN}✓ Dependencies installed${NC}"
fi
echo ""

# ========================================
# 3. Установка symlink в ~/.local/bin
# ========================================

echo "Step 3: Installing 'ccskill-gptimage' command..."

BIN_DIR="$HOME/.local/bin"
BIN_LINK="$BIN_DIR/ccskill-gptimage"
DISPATCHER="$REPO_DIR/ccskill-gptimage"

mkdir -p "$BIN_DIR"

if [ -L "$BIN_LINK" ] || [ ! -e "$BIN_LINK" ]; then
    ln -sf "$DISPATCHER" "$BIN_LINK"
    echo -e "${GREEN}✓ Command installed: $BIN_LINK${NC}"
else
    echo -e "${RED}Error: $BIN_LINK exists and is not a symlink${NC}"
    echo "Remove it manually and re-run ./install.sh"
    exit 1
fi

# Проверка PATH
if echo "$PATH" | tr ':' '\n' | grep -qx "$BIN_DIR"; then
    echo -e "${GREEN}✓ $BIN_DIR is in PATH${NC}"
else
    echo ""
    echo -e "${YELLOW}$BIN_DIR is not in your PATH.${NC}"
    SHELL_NAME=$(basename "${SHELL:-sh}")
    case "$SHELL_NAME" in
        zsh)  RC_FILE="~/.zshrc" ;;
        bash) RC_FILE="~/.bashrc" ;;
        *)    RC_FILE="your shell config" ;;
    esac
    echo "Add this to $RC_FILE and reload your shell:"
    echo ""
    echo -e "  ${BLUE}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi
echo ""

# ========================================
# 4. Регистрация скилла на уровне пользователя (~/.claude/skills)
# ========================================

echo "Step 4: Registering user-level skill for Claude Code..."

SKILL_SRC="$REPO_DIR/.claude/skills/ccskill-gptimage"
SKILL_PARENT="$HOME/.claude/skills"
SKILL_LINK="$SKILL_PARENT/ccskill-gptimage"

if [ ! -f "$SKILL_SRC/SKILL.md" ]; then
    echo -e "${RED}Error: skill source not found: $SKILL_SRC${NC}"
    exit 1
fi

mkdir -p "$SKILL_PARENT"

if [ -L "$SKILL_LINK" ]; then
    /bin/rm -f "$SKILL_LINK"
elif [ -d "$SKILL_LINK" ]; then
    if [ -f "$SKILL_LINK/SKILL.md" ]; then
        # Считаем это следом ручного копирования и заменяем на symlink
        /bin/rm -rf "$SKILL_LINK"
    else
        echo -e "${RED}Error: $SKILL_LINK exists but does not look like ccskill-gptimage (no SKILL.md).${NC}"
        echo "Remove it manually and re-run ./install.sh"
        exit 1
    fi
elif [ -e "$SKILL_LINK" ]; then
    echo -e "${RED}Error: $SKILL_LINK exists and is not a directory/symlink.${NC}"
    echo "Remove it manually and re-run ./install.sh"
    exit 1
fi

ln -s "$SKILL_SRC" "$SKILL_LINK"

if [ ! -f "$SKILL_LINK/SKILL.md" ]; then
    /bin/rm -f "$SKILL_LINK"
    echo -e "${RED}Error: symlink could not be resolved on this filesystem.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ User skill registered: $SKILL_LINK${NC}"
echo "  -> $SKILL_SRC"
echo "  (available in every Claude Code project; auto-updates via git pull)"
echo ""

# ========================================
# 5. Диагностика доступности backend — только по факту наличия.
#    Содержимое секретных файлов не читается (issue #021)
# ========================================

echo "Step 5: Checking image-generation backends (presence-based; secrets not read)..."

# Codex: решение по наличию CLI и файла сессии входа. Сам токен не читается
CODEX_OK=false
if command -v codex &> /dev/null && [ -f "$HOME/.codex/auth.json" ]; then
    CODEX_OK=true
fi

# API: решение по наличию переменной окружения и файла .env. Содержимое .env не читается
API_OK=false
if [ -n "${OPENAI_API_KEY:-}" ]; then
    API_OK=true
elif [ -f "$REPO_DIR/.env" ]; then
    API_OK=true
fi

if [ "$CODEX_OK" = true ]; then
    echo -e "${GREEN}✓ Codex CLI backend: likely (codex CLI + login session present)${NC}"
else
    echo -e "${YELLOW}- Codex CLI backend not available${NC} (brew install codex && codex login)"
fi

if [ "$API_OK" = true ]; then
    echo -e "${GREEN}✓ OpenAI API backend: likely (OPENAI_API_KEY set or .env present)${NC}"
else
    echo -e "${YELLOW}- OpenAI API backend not configured${NC} (cp .env.example .env, then set OPENAI_API_KEY)"
fi

if [ "$CODEX_OK" != true ] && [ "$API_OK" != true ]; then
    echo ""
    echo -e "${YELLOW}Warning: No backend is available yet.${NC}"
    echo "Set up at least one backend before generating images — see README.md (Requirements)."
fi
echo ""

# ========================================
# Готово
# ========================================

echo "================================================"
echo -e "${GREEN}  Installation Complete!${NC}"
echo "================================================"
echo ""
echo "Try it from any directory:"
echo ""
echo -e "  ${BLUE}ccskill-gptimage generate \"a minimalist fox logo, flat vector\"${NC}"
echo ""
echo "Or in any Claude Code project, just ask:"
echo ""
echo "  \"Generate an image of ... with ChatGPT Images\""
echo ""
echo "To update later:  cd $REPO_DIR && git pull"
echo "To uninstall:     ccskill-gptimage uninstall"
echo ""
