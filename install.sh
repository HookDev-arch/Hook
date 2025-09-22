#!/bin/bash
set -e

LOG="Hook-install.log"
SUDO_CMD=""

# Цвета для красоты
GREEN="\033[0;32m"
RED="\033[1;31m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
NC="\033[0m" # reset

# Логирование
log() { echo -e "${BLUE}$1${NC}"; echo "$1" >>"$LOG"; }
ok() { echo -e "${GREEN}$1${NC}"; echo "$1" >>"$LOG"; }
err() { echo -e "${RED}$1${NC}" >&2; echo "$1" >>"$LOG"; }

# Проверяем sudo
if command -v sudo >/dev/null && [ "$(id -u)" -ne 0 ]; then
    SUDO_CMD="sudo"
fi

clear
echo -e "\n${BLUE}🚀 Starting Hook 3.1 Installation...${NC}\n"
rm -f "$LOG" && touch "$LOG"

# Определяем ОС
if [ -f /etc/debian_version ]; then
    OS="debian"
    PKG_INSTALL="$SUDO_CMD apt install -y"
    UPDATE_CMD="$SUDO_CMD apt update"
elif [ -f /etc/arch-release ]; then
    OS="arch"
    PKG_INSTALL="$SUDO_CMD pacman -S --noconfirm --needed"
    UPDATE_CMD="$SUDO_CMD pacman -Sy"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    PKG_INSTALL="brew install"
    UPDATE_CMD="brew update"
else
    err "❌ Unsupported OS. Install manually: https://github.com/HookDev-arch/Hook"
    exit 1
fi

log "Detected OS: $OS"
eval "$UPDATE_CMD"

# Установка системных пакетов
log "📦 Installing system packages..."
case $OS in
    debian)
        $PKG_INSTALL python3 python3-pip python3-venv python3-dev git \
            libwebp-dev zlib1g-dev libjpeg-dev libopenjp2-7 \
            ffmpeg imagemagick libffi-dev libcairo2 build-essential \
            libtiff-dev
        ;;
    arch)
        $PKG_INSTALL python python-pip python-virtualenv git \
            libwebp libjpeg libtiff openjpeg2 ffmpeg imagemagick \
            libffi cairo base-devel
        ;;
    macos)
        $PKG_INSTALL git python webp jpeg libtiff openjpeg ffmpeg imagemagick cairo libffi
        ;;
esac
ok "✔ System packages installed!"

# Проверка python/pip
if ! command -v python3 >/dev/null; then
    err "Python3 not found!"
    exit 2
fi
$SUDO_CMD python3 -m pip install --upgrade pip setuptools wheel >>"$LOG" 2>&1

# Клонирование репозитория
log "🔄 Cloning Hook repository..."
rm -rf Hook
git clone https://github.com/HookDev-arch/Hook >>"$LOG" 2>&1
cd Hook || { err "❌ Clone failed"; exit 3; }
ok "✔ Repo cloned!"

# Установка Python зависимостей
log "🐍 Installing Python dependencies..."
$SUDO_CMD python3 -m pip install -r requirements.txt --upgrade --no-warn-script-location  --disable-pip-version-check >>"$LOG" 2>&1 || {
    err "❌ Requirements installation failed!"
    exit 4
}
ok "✔ Python dependencies installed!"

touch .setup_complete

# Запуск Hook
echo -e "\n${GREEN}🚀 Starting Hook...${NC}\n"
$SUDO_CMD python3 -m hook --root "$@" || {
    err "❌ Hook failed to start."
    exit 5
}
